"""Offline harness checks with SQLite and a fake HTTP transport; no real keys."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch

import httpx

from app.agents.harness import ContractHarness, HarnessLimitExceeded, current_run
from app.agents.supervisor import SupervisorAgent
from app.config import Settings
from app.database import Database
from app.domain.contract_workflow import ContractWorkspace, ExtractionResult
from app.domain.errors import WorkspaceConflict
from app.model_client import ChatModel
from app.repositories.agent_runs import AgentRunRepository
from app.repositories.contract_workspaces import ContractWorkspaceRepository


class HarnessTests(IsolatedAsyncioTestCase):
    """测试夹具或替身：HarnessTests，用于隔离验证本模块行为。"""

    async def test_model_selected_action_is_persisted_in_harness_trace(self):
        """Verify model selected action is persisted in harness trace."""
        runtime = self.runtime()
        token = current_run.set(runtime)

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
                                        "action": "request_user",
                                        "decision_summary": "原文缺少账号，交用户补充",
                                        "questions": ["请提供账号，或确认暂留空。"],
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                await runtime.execute(
                    "plan_next_action",
                    lambda: SupervisorAgent(ChatModel(self.settings, client)).decide(
                        "field_review", [], {}, ["request_user", "handoff"]
                    ),
                )
        finally:
            current_run.reset(token)
        runtime.finish("completed", "交用户补充")
        saved = AgentRunRepository(self.database).list("workspace", 1)[0]
        self.assertEqual(saved["steps"][0]["chosen_action"], "request_user")
        self.assertEqual(saved["steps"][0]["status"], "completed")
        self.assertEqual(saved["requests_started"], 1)

    def setUp(self):
        """准备隔离测试资源，避免访问生产数据库和真实模型。"""
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Database(Path(self.temporary.name) / "test.db")
        self.database.initialize()
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO users(id,username,email,password_hash) VALUES(1,'test','test@example.org','not-a-password')"
            )
        ContractWorkspaceRepository(self.database).create(
            ContractWorkspace(
                id="workspace",
                title="test",
                source_text="fictional minutes",
                created_at="now",
                updated_at="now",
            ),
            1,
        )
        self.settings = Settings(
            _env_file=None,
            llm_base_url="https://model.example.org",
            llm_api_key="test-only-key",
            llm_model="fake-model",
        )

    def runtime(self, settings=None):
        """Exercise runtime within this isolated test scenario."""
        return ContractHarness(
            settings or self.settings, self.database, "workspace", 1, 1, "extract", lambda **_: None
        )

    async def test_reasoning_configuration_summary_usage_and_no_raw_cot_in_journal(self):
        """Verify reasoning configuration summary usage and no raw cot in journal."""
        settings = self.settings.model_copy(
            update={"llm_thinking_mode": "enabled", "llm_reasoning_effort": "high"}
        )
        runtime = self.runtime(settings)
        payloads = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            payloads.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "usage": {"total_tokens": 42},
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {"fields": [], "decision_summary": "暂无可填写字段，需用户补充。"}
                                ),
                                "reasoning_content": "PRIVATE_PROVIDER_REASONING",
                            }
                        }
                    ],
                },
            )

        token = current_run.set(runtime)
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                result = await runtime.execute(
                    "extract_fields",
                    lambda: ChatModel(settings, client).generate_structured("提取", {}, ExtractionResult),
                )
        finally:
            current_run.reset(token)
        runtime.finish("completed", "done")
        self.assertEqual(result.fields, [])
        self.assertEqual(payloads[0]["thinking"], {"type": "enabled"})
        self.assertEqual(payloads[0]["reasoning_effort"], "high")
        self.assertNotIn("temperature", payloads[0])
        persisted = AgentRunRepository(self.database).list("workspace", 1)[0]
        self.assertEqual(persisted["steps"][0]["decision_summary"], result.decision_summary)
        self.assertEqual(persisted["token_usage"]["total_tokens"], 42)
        self.assertEqual(persisted["model_requests"], 1)
        self.assertEqual(persisted["requests_started"], 1)
        self.assertEqual(persisted["responses_received"], 1)
        self.assertNotIn("PRIVATE_PROVIDER_REASONING", json.dumps(persisted))
        self.assertNotIn("test-only-key", json.dumps(persisted))
        self.assertEqual(AgentRunRepository(self.database).list("workspace", 2), [])

    async def test_request_budget_is_shared_by_parallel_steps_before_http(self):
        """Verify request budget is shared by parallel steps before http."""
        settings = self.settings.model_copy(update={"harness_max_requests": 1})
        runtime = self.runtime(settings)
        requests = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

        token = current_run.set(runtime)
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                model = ChatModel(settings, client)
                results = await asyncio.gather(
                    *(runtime.execute("extract_fields", lambda: model.complete([])) for _ in range(2)),
                    return_exceptions=True,
                )
        finally:
            current_run.reset(token)
        self.assertEqual(len(requests), 1)
        self.assertTrue(any(isinstance(result, HarnessLimitExceeded) for result in results))
        self.assertEqual(runtime.snapshot["model_requests"], 1)
        self.assertEqual(len(runtime.snapshot["steps"]), 2)

    async def test_input_and_tool_boundaries_do_not_execute_callback(self):
        """Verify input and tool boundaries do not execute callback."""
        runtime = self.runtime()
        with self.assertRaises(HarnessLimitExceeded):
            runtime.reserve_request(self.settings.harness_max_input_chars + 1)
        with self.assertRaises(HarnessLimitExceeded):
            await runtime.execute("export_contract", lambda: asyncio.sleep(0))
        self.assertEqual(runtime.snapshot["steps"], [])
        self.assertEqual(runtime.snapshot["model_requests"], 0)

    async def test_structured_retries_cannot_bypass_request_budget(self):
        """Verify structured retries cannot bypass request budget."""
        settings = self.settings.model_copy(update={"harness_max_requests": 1})
        runtime = self.runtime(settings)
        requests = []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            requests.append(request)
            return httpx.Response(200, json={"choices": [{"message": {"content": "invalid JSON"}}]})

        token = current_run.set(runtime)
        try:
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(HarnessLimitExceeded):
                    await runtime.execute(
                        "extract_fields",
                        lambda: ChatModel(settings, client).generate_structured("提取", {}, ExtractionResult),
                    )
        finally:
            current_run.reset(token)
        self.assertEqual(len(requests), 1)
        self.assertEqual(runtime.snapshot["steps"][0]["status"], "failed")

    async def test_step_budget_and_cancellation_are_observable(self):
        """Verify step budget and cancellation are observable."""
        runtime = self.runtime(self.settings.model_copy(update={"harness_max_steps": 2}))
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(0.01):
                await runtime.execute("extract_fields", lambda: asyncio.sleep(10))
        self.assertEqual(runtime.snapshot["steps"][0]["status"], "interrupted")
        await runtime.execute("extract_fields", lambda: asyncio.sleep(0))
        with self.assertRaises(HarnessLimitExceeded):
            await runtime.execute("review_fields", lambda: asyncio.sleep(0))
        runtime.finish("failed", "test deadline")
        self.assertEqual(AgentRunRepository(self.database).list("workspace", 1)[0]["status"], "failed")

    async def test_lease_rejects_duplicate_worker_and_recovers_after_deadline(self):
        """Verify lease rejects duplicate worker and recovers after deadline."""
        runtime = self.runtime()
        with self.assertRaises(WorkspaceConflict):
            self.runtime()
        with patch("app.repositories.agent_runs.time", return_value=10**12):
            self.assertEqual(
                AgentRunRepository(self.database).list("workspace", 1)[0]["status"], "interrupted"
            )
            replacement = self.runtime()
        replacement.finish("completed", "done")
        with self.assertRaises(WorkspaceConflict):
            runtime.ensure_active()
        runtime.finish("completed", "stale worker must not replace expired record")
        records = AgentRunRepository(self.database).list("workspace", 1)
        self.assertEqual(len(records), 2)
        by_id = {item["run_id"]: item for item in records}
        self.assertEqual(by_id[runtime.snapshot["run_id"]]["status"], "interrupted")
        self.assertEqual(by_id[replacement.snapshot["run_id"]]["status"], "completed")

    async def test_history_is_bounded_and_deleted_with_workspace(self):
        """Verify history is bounded and deleted with workspace."""
        for _ in range(23):
            runtime = self.runtime()
            runtime.finish("failed", "test failure")
        self.assertEqual(len(AgentRunRepository(self.database).list("workspace", 1)), 20)
        ContractWorkspaceRepository(self.database).delete("workspace", 1)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM contract_agent_runs").fetchone()[0], 0)
