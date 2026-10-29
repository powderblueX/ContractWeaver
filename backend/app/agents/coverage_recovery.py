"""Bounded coverage recovery retaining the complete factual comparison context."""

from app.agents.harness import HarnessLimitExceeded, run_step
from app.domain.contract_workflow import CoverageResult
from app.model_client import ModelUnavailable


async def review_coverage(agent, source_lines, specs, fields):
    """Split only the reporting scope, never remove cross-line or cross-field context."""
    gaps, failures = [], []

    async def visit(focus, depth=0):
        """Retry a length-limited report on disjoint evidence ranges at most twice."""
        try:
            if depth:
                result = await run_step("review_coverage", lambda: agent.review(
                    source_lines, specs, fields, focus_line_numbers=focus))
            else:
                result = await run_step("review_coverage", lambda: agent.review(source_lines, specs, fields))
            gaps.extend(result.gaps)
        except HarnessLimitExceeded as error:
            error.partial_coverage_gaps = list(gaps)
            raise
        except (ModelUnavailable, ValueError) as error:
            if (isinstance(error, ModelUnavailable) and error.code == "output_truncated"
                    and getattr(error, "allow_batch_split", True) and len(focus) > 1 and depth < 2):
                middle = len(focus) // 2
                await visit(focus[:middle], depth + 1)
                await visit(focus[middle:], depth + 1)
            else:
                failures.append(error)

    await visit([line["line_number"] for line in source_lines])
    unique = {gap.model_dump_json(): gap for gap in gaps}
    if failures:
        error = failures[0]
        error.partial_coverage_gaps = list(unique.values())
        raise error
    if len(unique) > 30:
        error = ModelUnavailable("覆盖检查发现超过30项问题，请分阶段人工核对", code="coverage_incomplete")
        error.partial_coverage_gaps = list(unique.values())
        raise error
    return CoverageResult(gaps=list(unique.values()))
