"""Regressions from a real custody export: one business blank, one typed field."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from docx import Document
from docx.enum.text import WD_TAB_ALIGNMENT
from docx.shared import Inches

from app.agents.contract_coverage import ContractCoverageAgent
from app.agents.field_mapping import model_fields
from app.documents.slot_constraints import validate_slot_values
from app.documents.word_text import paragraph_text
from app.domain.contract_workflow import CoverageResult, ReviewedField
from app.domain.errors import InvalidContractInput
from app.model_client import ModelUnavailable
from app.services.contract_templates import ContractTemplateCatalog


class CoverageAgentTests(IsolatedAsyncioTestCase):
    """测试夹具或替身：CoverageAgentTests，用于隔离验证本模块行为。"""

    async def test_over_budget_payload_is_not_silently_truncated_or_sent(self):
        """Verify over budget payload is not silently truncated or sent."""
        model = AsyncMock()
        agent = ContractCoverageAgent(model, max_context_chars=10)
        with self.assertRaises(ModelUnavailable):
            await agent.review([{"line_number": 1, "text": "完整记录不得静默截断"}], [], [])
        model.generate_structured.assert_not_awaited()

    async def test_coverage_sees_all_fields_and_existing_values_in_one_pass(self):
        """Verify coverage sees all fields and existing values in one pass."""
        model = AsyncMock()
        model.generate_structured.return_value = CoverageResult()
        fields = [{"name": "名称", "context": "物品：{名称}"}, {"name": "其他", "context": "其他：{其他}"}]
        await ContractCoverageAgent(model).review(
            [{"line_number": 1, "text": "箱号QH-01，交接共同清点"}],
            fields,
            [ReviewedField(name="名称", value="模型")],
        )
        payload = model.generate_structured.call_args.args[1]
        self.assertEqual(len(payload["contract_fields"]), 2)
        self.assertEqual(payload["contract_fields"][0]["value"], "模型")
        self.assertEqual(payload["contract_fields"][1]["value"], "")


class CustodyMappingTests(TestCase):
    """测试夹具或替身：CustodyMappingTests，用于隔离验证本模块行为。"""

    def setUp(self):
        """准备隔离测试资源，避免访问生产数据库和真实模型。"""
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.resources = Path(__file__).resolve().parents[1] / "resources" / "contracts"
        self.catalog = ContractTemplateCatalog(self.resources, Path(self.temporary.name))
        self.template = next(
            item for item in self.catalog.list_templates(query="保管合同") if "0801" in item["name"]
        )
        self.details = self.catalog.describe_template(self.template["id"])

    def test_tab_definitions_are_not_document_content(self):
        """Verify tab definitions are not document content."""
        document = Document()
        paragraph = document.add_paragraph("保管人：\t")
        paragraph.paragraph_format.tab_stops.add_tab_stop(Inches(2), WD_TAB_ALIGNMENT.LEFT)
        self.assertEqual(paragraph_text(paragraph), "保管人：\t")

    def test_real_template_has_no_duplicate_label_blanks_or_heading_inputs(self):
        """Verify real template has no duplicate label blanks or heading inputs."""
        fields = self.details["fields"]
        for label in ("保管物名称", "性质", "数量", "价值", "保管场所", "保管方法"):
            self.assertEqual(sum(field["display_name"] == label for field in fields), 1, label)
        self.assertFalse(any(field["display_name"] == "条款间空白" for field in fields))
        self.assertEqual(sum(field.get("value_type") == "choice" for field in fields), 5)
        self.assertEqual(sum(field.get("value_type") == "date_part" for field in fields), 9)
        self.assertEqual(sum(field.get("value_type") == "money_upper" for field in fields), 1)

    def test_model_sees_one_active_slot_and_explicit_date_components(self):
        """Verify model sees one active slot and explicit date components."""
        fields = [field for field in self.details["fields"] if field.get("value_type") == "date_part"]
        _, payload = model_fields(fields)
        for field in payload:
            self.assertEqual(field["context"].count("[当前填写处]"), 1)
            self.assertIn(field["component"], "年月日")
            self.assertNotIn("·位置", field["context"])

    def test_dates_options_and_uppercase_units_reject_malformed_values(self):
        """Verify dates options and uppercase units reject malformed values."""
        for field in self.details["fields"]:
            kind = field.get("value_type")
            bad = (
                "2026年11月1日至2027年1月31日"
                if kind == "date_part"
                else "未确定"
                if kind == "choice"
                else "叁仟元整"
                if kind == "money_upper"
                else None
            )
            if bad:
                with self.assertRaises(InvalidContractInput):
                    self.catalog.preview_contract(self.template["id"], {field["name"]: bad})
                with self.assertRaises(InvalidContractInput):
                    self.catalog.generate_contract(self.template["id"], {field["name"]: bad})
        fields = [field for field in self.details["fields"] if "开始日期" in field["display_name"]]
        values = {
            field["name"]: {"年": "2026", "月": "2", "日": "31"}[field["component"]] for field in fields
        }
        with self.assertRaises(InvalidContractInput):
            validate_slot_values(fields, values)

    def test_reviewed_custody_facts_render_once_and_fixed_text_is_preserved(self):
        """Verify reviewed custody facts render once and fixed text is preserved."""
        values = {}
        known = {
            "保管人": "安澜保管测试有限公司",
            "寄存人": "青禾文创测试有限公司",
            "保管物名称": "展览用树脂模型，箱号QH-01至QH-20",
            "性质": "已封箱，非易燃易爆品",
            "数量": "20箱，每箱1件，共20件",
            "价值": "人民币100000元（申报价值，不代表赔偿上限）",
            "保管场所": "示例市演示路18号安澜保管中心2层B室",
            "保管方法": "室内干燥环境分区存放，防潮防晒、离地，不得擅自开箱、使用或出借",
            "保管费的支付方式与时间": "2026年11月1日、2026年12月15日各支付1500元，通过银行转账支付",
            "其他约定事项": "未经寄存人书面同意不得转交第三人；交接清点箱号、数量、外包装并出具保管凭证；期满取回时核对箱号、数量及外包装。实际交接清单和照片待交接后补充。",
        }
        for field in self.details["fields"]:
            label = field["display_name"]
            if label in known:
                values[field["name"]] = known[label]
            elif "保管期限自" in label:
                date = (
                    {"年": "2027", "月": "1", "日": "31"}
                    if "结束日期" in label
                    else {"年": "2026", "月": "11", "日": "1"}
                )
                values[field["name"]] = date[field["component"]]
            elif field.get("value_type") == "money_upper":
                values[field["name"]] = "叁仟"
            elif field.get("value_type") == "choice" and "有货币" in label:
                values[field["name"]] = "否"
        omitted = [field["name"] for field in self.details["fields"] if field["name"] not in values]
        original = self.catalog.get_template(self.template["id"]).path.read_bytes()
        preview = self.catalog.preview_contract(self.template["id"], values, omitted)
        compact = "".join(preview["text"].split())
        self.assertIn("保管期限自2026年11月1日至2027年1月31日", compact)
        self.assertIn("第十条保管费（大写）叁仟元", compact)
        self.assertIn("保管物（否）有货币", compact)
        self.assertIn("第九条保管人（是/否）允许保管人", compact)  # Source typo is not silently rewritten.
        self.assertEqual(compact.count("展览用树脂模型"), 1)
        self.assertEqual(compact.count("示例市演示路18号"), 1)
        for text in ("QH-01", "不代表赔偿上限", "各支付1500元", "保管凭证", "期满取回"):
            self.assertIn(text, compact)
        artifact = self.catalog.generate_contract(self.template["id"], values, omitted)
        output = Document(Path(self.temporary.name) / artifact["filename"])
        self.assertIn("叁仟", "".join(paragraph_text(p) for p in output.paragraphs))
        self.assertEqual(self.catalog.get_template(self.template["id"]).path.read_bytes(), original)
