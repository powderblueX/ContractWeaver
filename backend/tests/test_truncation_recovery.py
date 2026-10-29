"""Deterministic long-output recovery, partial preservation and bounded retries."""

from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from app.agents.field_coordinator import FieldCoordinator
from app.agents.harness import HarnessLimitExceeded
from app.config import Settings
from app.domain.contract_workflow import ExtractionResult, FieldStatus, ReviewResult, SupervisorDecision
from app.model_client import ModelUnavailable

SOURCE = [{"line_number": 1, "text": "双方最终确认8000元。"}]


class SizedTeam:
    """Simulate provider truncation by batch size without network calls or real keys."""

    def __init__(self, extract_limit=100, review_limit=100, bad_extract=None, budget_error=False, allow_split=True):
        """Record role requests and isolate each fake provider condition."""
        self.extract_limit, self.review_limit = extract_limit, review_limit
        self.bad_extract = set(bad_extract or [])
        self.budget_error = budget_error
        self.allow_split = allow_split
        self.extractions, self.reviews = [], []
        self.extraction = SimpleNamespace(extract=self.extract)
        self.review = SimpleNamespace(review=self.review_fields)
        self.supervisor = SimpleNamespace(decide=self.decide)

    async def extract(self, _source, specs):
        """Return complete validated evidence or the same length error as a provider."""
        self.extractions.append([item["name"] for item in specs])
        if self.budget_error:
            raise HarnessLimitExceeded("test request budget")
        if len(specs) > self.extract_limit:
            error = ModelUnavailable("模拟输出截断", code="output_truncated")
            error.allow_batch_split = self.allow_split
            raise error
        if any(item["name"] in self.bad_extract for item in specs):
            raise ModelUnavailable("模拟一个子批次失败", code="model_provider")
        return ExtractionResult(fields=[{"field_name": item["name"], "value": "8000元", "status": "found",
                                        "evidence": [{"line_number": 1, "quote": "8000元"}]} for item in specs])

    async def review_fields(self, _source, specs, _fields):
        """Truncate long reviews independently from successful extraction requests."""
        self.reviews.append([item["name"] for item in specs])
        if len(specs) > self.review_limit:
            raise ModelUnavailable("模拟复核截断", code="output_truncated")
        return ReviewResult()

    async def decide(self, *_args):
        """Hand candidates back to human review without approving any field."""
        return SupervisorDecision(action="handoff", decision_summary="候选等待人工确认")


class TruncationRecoveryTests(IsolatedAsyncioTestCase):
    """Exercise both successful recovery and exhaustion of the recovery bound."""

    def specs(self, count=4):
        """Build simple independent text fields with no synthetic type errors."""
        return [{"name": f"字段{index}", "context": "合同金额"} for index in range(count)]

    async def test_extraction_truncation_splits_and_restores_every_field(self):
        """A truncated parent request is replaced by smaller disjoint requests."""
        team = SizedTeam(extract_limit=2)
        result = await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(), 0)
        self.assertEqual([len(items) for items in team.extractions], [4, 2, 2])
        self.assertEqual(len(result.fields), 4)
        self.assertEqual(result.failures, [])
        self.assertFalse(any(item.status == FieldStatus.CONFIRMED for item in result.fields))

    async def test_review_truncation_does_not_repeat_extraction(self):
        """Review-only splitting preserves the already extracted proposals."""
        team = SizedTeam(review_limit=2)
        result = await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(), 0)
        self.assertEqual(len(team.extractions), 1)
        self.assertEqual([len(items) for items in team.reviews], [4, 2, 2])
        self.assertEqual(result.failures, [])

    async def test_exhausted_review_keeps_values_unverified_and_can_retry_review_only(self):
        """Failed review retains evidence and values, never labels them as approved."""
        team = SizedTeam(review_limit=0)
        result = await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(), 0)
        self.assertEqual(len(team.reviews), 7)
        self.assertTrue(all(item.value == "8000元" and item.evidence for item in result.fields))
        self.assertTrue(all(item.status == FieldStatus.UNVERIFIED for item in result.fields))
        self.assertTrue(all(item["phase"] == "review" for item in result.failures))
        team.review_limit = 100
        retried = await FieldCoordinator(team, Settings(_env_file=None)).run(
            SOURCE, self.specs(), 0, previous_fields=result.fields)
        self.assertEqual(len(team.extractions), 1)
        self.assertEqual(retried.failures, [])
        self.assertTrue(all(not item.review_issues for item in retried.fields))
        self.assertTrue(all(item.status == FieldStatus.EXTRACTED for item in retried.fields))

    async def test_successful_sibling_survives_a_failed_extraction_sub_batch(self):
        """One failed leaf must not discard values recovered by another leaf."""
        team = SizedTeam(extract_limit=1, bad_extract=["字段1"])
        result = await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(), 0)
        values = {item.name: item.value for item in result.fields}
        self.assertEqual(values["字段1"], "")
        self.assertEqual(values["字段2"], "8000元")
        self.assertEqual([name for failure in result.failures for name in failure["field_names"]], ["字段1"])

    async def test_reasoning_only_cutoff_stops_without_splitting(self):
        """Do not increase paid request count when no answer was generated."""
        team = SizedTeam(extract_limit=0, allow_split=False)
        result = await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(16), 0)
        self.assertEqual(len(team.extractions), 1)
        self.assertEqual(len(result.failures), 1)

    async def test_splitting_is_bounded_and_budget_errors_escape(self):
        """A permanently truncated response cannot trigger an unlimited retry tree."""
        team = SizedTeam(extract_limit=0)
        await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(16), 0)
        self.assertEqual(len(team.extractions), 7)
        budget_team = SizedTeam(budget_error=True)
        with self.assertRaises(HarnessLimitExceeded):
            await FieldCoordinator(budget_team, Settings(_env_file=None)).run(SOURCE, self.specs(), 0)
        self.assertEqual(len(budget_team.extractions), 1)

    async def test_review_budget_exhaustion_preserves_extracted_candidates(self):
        """An exhausted run still returns proposals for a later review-only retry."""
        team = SizedTeam()

        async def exhausted(*_args):
            """Stop at the harness boundary after extraction already succeeded."""
            raise HarnessLimitExceeded("time budget")

        team.review.review = exhausted
        result = await FieldCoordinator(team, Settings(_env_file=None)).run(SOURCE, self.specs(), 0)
        self.assertTrue(all(field.value == "8000元" for field in result.fields))
        self.assertTrue(all(field.status == FieldStatus.UNVERIFIED for field in result.fields))
        self.assertEqual(result.failures[0]["phase"], "review")
        self.assertEqual(result.failures[0]["error"]["code"], "execution_budget")
