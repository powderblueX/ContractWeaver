"""Coverage regression tests with injected providers; no live credentials or costs."""

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

import httpx

from app.agents.coverage_recovery import review_coverage
from app.agents.coverage_repair import repair_coverage
from app.agents.response_diagnostics import response_diagnostics
from app.config import Settings
from app.domain.contract_workflow import (
    CoverageGap,
    CoverageResult,
    ExtractionResult,
    ReviewedField,
    ReviewResult,
)
from app.model_client import ChatModel, ModelUnavailable

LINES = [{"line_number": index, "text": "箱号QH-01至QH-20；不再收取场地费。"} for index in range(1, 5)]
SPECS = [{"name": "其他", "context": "其他约定"}]


class CoverageRecoveryTests(IsolatedAsyncioTestCase):
    """Exercise focused recovery, partial retention and evidence-safe bounded repair."""

    async def test_reasoning_budget_recovery_is_bounded_and_can_be_disabled(self):
        """Increase only the output allowance once without changing thinking settings."""
        for ceiling, expected in [(32768, [8192, 32768]), (0, [8192])]:
            calls = []

            def respond(request):
                """Always truncate after reported reasoning to test the terminal bound."""
                payload = json.loads(request.content)
                calls.append(payload["max_tokens"])
                self.assertEqual(payload["thinking"], {"type": "enabled"})
                return httpx.Response(200, json={"usage": {"completion_tokens": payload["max_tokens"],
                    "completion_tokens_details": {"reasoning_tokens": payload["max_tokens"]}},
                    "choices": [{"finish_reason": "length", "message": {"content": ""}}]})

            settings = Settings(_env_file=None, llm_api_key="fixture", llm_model="fixture",
                                llm_base_url="https://example.org", llm_thinking_mode="enabled",
                                llm_recovery_max_tokens=ceiling)
            async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
                with self.assertRaises(ModelUnavailable) as raised:
                    await ChatModel(settings, client).generate_structured("check", {}, CoverageResult)
            self.assertFalse(raised.exception.allow_batch_split)
            self.assertEqual(calls, expected)

    async def test_split_keeps_full_context_and_retains_successful_sibling(self):
        """Splitting must not hide later negations or discard successful gap reports."""
        calls = []

        async def review(source, specs, fields, focus_line_numbers=None):
            """Simulate a truncation followed by one successful reporting range."""
            self.assertEqual(source, LINES)
            self.assertEqual(specs, SPECS)
            calls.append(focus_line_numbers)
            if focus_line_numbers is None:
                raise ModelUnavailable("cutoff", code="output_truncated")
            if 4 in focus_line_numbers:
                raise ModelUnavailable("provider unavailable")
            return CoverageResult(gaps=[CoverageGap(summary="遗漏箱号", evidence={"line_number": 1, "quote": "箱号QH-01至QH-20"}, suggestion="核对其他约定")])

        with self.assertRaises(ModelUnavailable) as raised:
            await review_coverage(SimpleNamespace(review=review), LINES, SPECS, [])
        self.assertEqual(calls, [None, [1, 2], [3, 4]])
        self.assertEqual(len(raised.exception.partial_coverage_gaps), 1)

    async def test_reasoning_exhaustion_does_not_split_coverage(self):
        """A reasoning-limited response must not start a wasteful retry tree."""
        error = ModelUnavailable("reasoning cutoff", code="output_truncated")
        error.allow_batch_split = False
        agent = SimpleNamespace(review=AsyncMock(side_effect=error))
        with self.assertRaises(ModelUnavailable):
            await review_coverage(agent, LINES, SPECS, [])
        self.assertEqual(agent.review.await_count, 1)

    async def test_coverage_repair_requires_evidence_and_fresh_review(self):
        """Accepted repair is a candidate, while failed reviews keep the original."""
        fields = [ReviewedField(name="其他", value="旧候选")]
        gap = CoverageGap(summary="遗漏箱号和不另收费", evidence={"line_number": 1, "quote": LINES[0]["text"]},
                          suggestion="补充其他约定", target_fields=["其他"])
        team = SimpleNamespace(extraction=SimpleNamespace(repair=AsyncMock(return_value=ExtractionResult(fields=[
            {"field_name": "其他", "value": LINES[0]["text"], "status": "found", "evidence": [gap.evidence]}]))),
            review=SimpleNamespace(review=AsyncMock(side_effect=ModelUnavailable("cutoff"))))
        changed, warnings = await repair_coverage(team, LINES, SPECS, fields, [gap])
        self.assertFalse(changed)
        self.assertTrue(warnings)
        self.assertEqual(fields[0].value, "旧候选")
        team.review.review.side_effect = None
        team.review.review.return_value = ReviewResult()
        changed, warnings = await repair_coverage(team, LINES, SPECS, fields, [gap])
        self.assertTrue(changed)
        self.assertEqual(fields[0].status.value, "extracted")
        self.assertIn("QH-01至QH-20", fields[0].value)
        self.assertIn("不再收取场地费", fields[0].value)

    async def test_coverage_cannot_edit_approved_fields_or_use_fabricated_evidence(self):
        """Human approvals and ungrounded gap suggestions are excluded before requests."""
        team = SimpleNamespace(extraction=SimpleNamespace(repair=AsyncMock()))
        gap = CoverageGap(summary="补充", evidence={"line_number": 1, "quote": "不存在"}, suggestion="补充", target_fields=["其他"])
        fields = [ReviewedField(name="其他", value="人工值", status="confirmed")]
        self.assertEqual(await repair_coverage(team, LINES, SPECS, fields, [gap]), (False, []))
        gap.evidence.quote = LINES[0]["text"]
        self.assertEqual(await repair_coverage(team, LINES, SPECS, fields, [gap]), (False, []))
        fields[0].status = "missing"
        gap.evidence.quote = "不存在"
        self.assertEqual(await repair_coverage(team, LINES, SPECS, fields, [gap]), (False, []))
        team.extraction.repair.assert_not_awaited()


class ResponseDiagnosticsTests(TestCase):
    """Only numeric diagnostics leave the provider response boundary."""

    def test_usage_detects_hidden_reasoning_and_contains_no_raw_text(self):
        """Gateway may strip reasoning_content but preserve its token count."""
        data = response_diagnostics({"finish_reason": "length", "message": {"content": "{"}},
                                    {"completion_tokens": 8192, "completion_tokens_details": {"reasoning_tokens": 8100}}, 8192)
        self.assertTrue(data["reasoning_dominated"])
        self.assertEqual(data["answer_chars"], 1)
        self.assertNotIn("content", data)

    def test_absent_usage_is_unknown_not_proof_of_reasoning_exhaustion(self):
        """Do not infer provider behavior from missing counters."""
        data = response_diagnostics({"message": {"content": "partial"}}, None, 8192)
        self.assertNotIn("reasoning_tokens", data)
        self.assertFalse(data["reasoning_dominated"])
