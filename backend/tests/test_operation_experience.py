"""HTTP telemetry and short model IDs are verified with a non-network transport."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from uuid import uuid4

import httpx
from docx import Document

from app.agents.field_extraction import FieldExtractionAgent
from app.agents.field_review import FieldReviewAgent
from app.config import Settings
from app.model_client import ChatModel
from app.observability import current_operation, operations
from app.services.contract_templates import ContractTemplateCatalog


class ReadablePreviewTests(TestCase):
    """测试夹具或替身：ReadablePreviewTests，用于隔离验证本模块行为。"""

    def test_empty_columns_are_preserved_under_their_original_headers(self):
        """Verify empty columns are preserved under their original headers."""
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "templates" / "Ministerial"
            folder.mkdir(parents=True)
            document = Document()
            table = document.add_table(rows=2, cols=3)
            for index, value in enumerate(("产品", "数量", "备注")):
                table.cell(0, index).text = value
            table.cell(1, 1).text = "{数量}"
            document.save(folder / "示例采购合同.docx")
            catalog = ContractTemplateCatalog(root, root / "generated")
            identifier = catalog.list_templates()[0]["id"]
            details = catalog.describe_template(identifier)
            omitted = [name for name in details["placeholders"] if name != "数量"]
            preview = catalog.preview_contract(identifier, {"数量": "10台"}, omitted)
            self.assertEqual(preview["blocks"][0]["rows"], [["产品", "数量", "备注"], ["", "10台", ""]])


class OperationExperienceTests(IsolatedAsyncioTestCase):
    """测试夹具或替身：OperationExperienceTests，用于隔离验证本模块行为。"""

    def settings(self):
        """创建不读取私有密钥的测试配置。"""
        return Settings(
            _env_file=None,
            llm_api_key="synthetic-test",
            llm_base_url="https://example.org",
            llm_model="test-model",
            structured_output_retries=1,
        )

    async def test_short_ids_restore_word_names_and_invalid_ids_get_bounded_repair(self):
        """Verify short ids restore word names and invalid ids get bounded repair."""
        requests = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            requests.append(json.loads(request.content))
            name = "错误的业务名称" if len(requests) == 1 else "f001"
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "fields": [
                                            {
                                                "field_name": name,
                                                "value": "80000元",
                                                "status": "found",
                                                "evidence": [{"line_number": 1, "quote": "80000元"}],
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        identifier = uuid4().hex
        operations.start(identifier, "extract", "test-model")
        token = current_operation.set(identifier)
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                model = ChatModel(self.settings(), client)
                result = await FieldExtractionAgent(model).extract(
                    [{"line_number": 1, "text": "最终总价80000元"}],
                    [
                        {
                            "name": "复杂的内部名称·位置145-7",
                            "display_name": "合同总价",
                            "context": "总价：{复杂的内部名称·位置145-7}",
                        }
                    ],
                )
            self.assertEqual(result.fields[0].field_name, "复杂的内部名称·位置145-7")
            self.assertEqual(len(requests), 2)
            inputs = json.loads(requests[0]["messages"][1]["content"])
            self.assertEqual(inputs["template_fields"][0]["name"], "f001")
            self.assertNotIn("·位置", json.dumps(inputs, ensure_ascii=False))
            snapshot = operations.snapshot(identifier)
            self.assertEqual(snapshot["requests_started"], 2)
            self.assertEqual(snapshot["responses_received"], 2)
            self.assertNotIn("synthetic-test", json.dumps(snapshot))
        finally:
            operations.finish("completed", "test")
            current_operation.reset(token)

    async def test_failed_http_request_is_counted_without_claiming_a_response_success(self):
        """Verify failed http request is counted without claiming a response success."""
        identifier = uuid4().hex
        operations.start(identifier, "analyze", "test-model")
        token = current_operation.set(identifier)
        try:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(lambda _: httpx.Response(401))
            ) as client:
                with self.assertRaisesRegex(RuntimeError, "认证"):
                    await ChatModel(self.settings(), client).complete([])
            snapshot = operations.snapshot(identifier)
            self.assertEqual(
                (snapshot["requests_started"], snapshot["responses_received"], snapshot["requests_failed"]),
                (1, 0, 1),
            )
        finally:
            operations.finish("failed", "test")
            current_operation.reset(token)

    async def test_review_can_report_multiple_findings_for_one_short_id(self):
        """Verify review can report multiple findings for one short id."""

        def respond(_):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "findings": [
                                            {
                                                "field_name": "f001",
                                                "issue": "金额待确认",
                                                "severity": "warning",
                                            },
                                            {
                                                "field_name": "f001",
                                                "issue": "存在报价冲突",
                                                "severity": "conflict",
                                            },
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await FieldReviewAgent(ChatModel(self.settings(), client)).review(
                [], [{"name": "金额·位置1", "context": "金额"}], [{"name": "金额·位置1", "value": "10"}]
            )
        self.assertEqual([finding.field_name for finding in result.findings], ["金额·位置1", "金额·位置1"])
