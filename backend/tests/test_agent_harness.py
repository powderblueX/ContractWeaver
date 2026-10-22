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
    async def test_model_selected_action_is_persisted_in_harness_trace(self):
        runtime = self.runtime()
        token = current_run.set(runtime)

        def respond(_):
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
        return ContractHarness(
            settings or self.settings, self.database, "workspace", 1, 1, "extract", lambda **_: None
        )

    async def test_reasoning_configuration_summary_usage_and_no_raw_cot_in_journal(self):
        settings = self.settings.model_copy(
            update={"llm_thinking_mode": "enabled", "llm_reasoning_effort": "high"}
        )
        runtime = self.runtime(settings)
        payloads = []

        def respond(request):
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
        settings = self.settings.model_copy(update={"harness_max_requests": 1})
        runtime = self.runtime(settings)
        requests = []

        def respond(request):
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
        runtime = self.runtime()
        with self.assertRaises(HarnessLimitExceeded):
            runtime.reserve_request(self.settings.harness_max_input_chars + 1)
        with self.assertRaises(HarnessLimitExceeded):
            await runtime.execute("export_contract", lambda: asyncio.sleep(0))
        self.assertEqual(runtime.snapshot["steps"], [])
        self.assertEqual(runtime.snapshot["model_requests"], 0)

    async def test_structured_retries_cannot_bypass_request_budget(self):
        settings = self.settings.model_copy(update={"harness_max_requests": 1})
        runtime = self.runtime(settings)
        requests = []

        def respond(request):
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
        self.assertEqual(records[1]["status"], "interrupted")

    async def test_history_is_bounded_and_deleted_with_workspace(self):
        for _ in range(23):
            runtime = self.runtime()
            runtime.finish("failed", "test failure")
        self.assertEqual(len(AgentRunRepository(self.database).list("workspace", 1)), 20)
        ContractWorkspaceRepository(self.database).delete("workspace", 1)
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM contract_agent_runs").fetchone()[0], 0)
