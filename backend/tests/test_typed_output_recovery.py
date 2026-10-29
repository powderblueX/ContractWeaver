"""Typed-output regressions using a local mock provider, never live model keys."""

import json
from unittest import IsolatedAsyncioTestCase, TestCase

import httpx
from pydantic import ValidationError

from app.agents.field_extraction import FieldExtractionAgent
from app.agents.field_mapping import batch_schema
from app.config import Settings
from app.domain.contract_workflow import ExtractedField, ExtractionResult, ReviewFinding, ReviewResult
from app.model_client import ChatModel, ModelUnavailable


class BatchContractTests(TestCase):
    """Schema distinguishes omitted output records from explicitly missing facts."""

    def test_missing_and_duplicate_records_fail_but_explicit_missing_is_valid(self):
        """Require every ID once, while permitting a well-formed empty factual value."""
        schema = batch_schema(ExtractionResult, ExtractedField, "fields", {"f001": "甲", "f002": "乙"})
        first = {"field_name": "f001", "value": "", "status": "missing"}
        for records in ([], [first], [first, first]):
            with self.assertRaises(ValidationError):
                schema.model_validate({"fields": records})
        result = schema.model_validate({"fields": [first, {**first, "field_name": "f002"}]})
        self.assertEqual(len(result.fields), 2)

    def test_review_is_sparse_and_allows_multiple_findings_for_one_field(self):
        """Extraction completeness must not force reviewers to invent findings."""
        schema = batch_schema(ReviewResult, ReviewFinding, "findings", {"f001": "甲"})
        self.assertEqual(schema.model_validate({"findings": []}).findings, [])
        issue = {"field_name": "f001", "severity": "warning", "issue": "核对依据"}
        self.assertEqual(len(schema.model_validate({"findings": [issue, issue]}).findings), 2)


class StructuredRepairTests(IsolatedAsyncioTestCase):
    """Exercise actual HTTP serialization and bounded schema repair."""

    async def test_incomplete_valid_json_receives_targeted_feedback_then_recovers(self):
        """A syntactically valid omission is retried instead of silently accepted."""
        requests = []

        def respond(request):
            """Return a missing output record once, then a complete explicit missing value."""
            requests.append(json.loads(request.content))
            answer = {"fields": []} if len(requests) == 1 else {"fields": [{"field_name": "f001", "value": "", "status": "missing"}]}
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})

        settings = Settings(_env_file=None, llm_base_url="https://example.org", llm_model="fixture", llm_api_key="fixture")
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await FieldExtractionAgent(ChatModel(settings, client)).extract(
                [{"line_number": 1, "text": "签署日期未确定"}], [{"name": "签署日", "context": "日期{签署日}"}])
        self.assertEqual(result.fields[0].status, "missing")
        self.assertEqual(len(requests), 2)
        self.assertIn('"path":["fields"]', requests[1]["messages"][-1]["content"])
        self.assertIn("too_short", requests[1]["messages"][-1]["content"])

    async def test_huge_invalid_answer_is_not_repeated_and_retry_remains_bounded(self):
        """Preserve original context but do not multiply malformed provider output."""
        requests = []
        invalid = "INVALID_MARKER" * 1000

        def respond(request):
            """Return oversized non-JSON text on every attempt."""
            requests.append(json.loads(request.content))
            return httpx.Response(200, json={"choices": [{"message": {"content": invalid}}]})

        settings = Settings(_env_file=None, llm_base_url="https://example.org", llm_model="fixture", llm_api_key="fixture", structured_output_retries=1)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ModelUnavailable):
                await ChatModel(settings, client).generate_structured("check", {"source": "ORIGINAL_SOURCE"}, ReviewResult)
        self.assertEqual(len(requests), 2)
        serialized = json.dumps(requests[1])
        self.assertNotIn("INVALID_MARKER", serialized)
        self.assertIn("ORIGINAL_SOURCE", serialized)
