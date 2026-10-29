"""One bounded evidence-grounded repair after cross-field coverage review."""

from app.agents.candidate_validation import apply_review, validate_candidates
from app.agents.harness import HarnessLimitExceeded, run_step
from app.domain.contract_workflow import FieldStatus
from app.model_client import ModelUnavailable


async def repair_coverage(team, source_lines, specs, fields, gaps, limit=5):
    """Propose fixes to named existing slots, keeping human decisions immutable."""
    source = {line["line_number"]: line["text"] for line in source_lines}
    feedback = {}
    for gap in gaps:
        if gap.evidence.quote not in source.get(gap.evidence.line_number, ""):
            continue
        for name in gap.target_fields:
            feedback.setdefault(name, []).append(
                f"覆盖检查：{gap.summary}；原文第{gap.evidence.line_number}行：{gap.evidence.quote}；{gap.suggestion}")
    targets = [field for field in fields if field.name in feedback and
               field.status not in (FieldStatus.CONFIRMED, FieldStatus.OMITTED)][:limit]
    if not targets:
        return False, []
    names = {field.name for field in targets}
    target_specs = [spec for spec in specs if spec["name"] in names]
    previous = [field.model_copy(deep=True) for field in targets]
    for field in previous:
        field.review_issues.extend(feedback[field.name])
    try:
        output = await run_step("repair_fields", lambda: team.extraction.repair(source_lines, target_specs, previous))
        proposed = validate_candidates(output, target_specs, source_lines, require_complete=True)
        review = await run_step("review_fields", lambda: team.review.review(
            source_lines, target_specs, [field.model_dump(mode="json") for field in proposed]))
        apply_review(proposed, review)
        accepted = {field.name: field for field in proposed if field.value and field.evidence and
                    field.status == FieldStatus.EXTRACTED and not field.review_issues}
        changed = False
        for index, field in enumerate(fields):
            candidate = accepted.get(field.name)
            if candidate and candidate.value != field.value:
                candidate.note = ("已依据覆盖检查补充候选并独立复核，仍需人工确认。" + candidate.note)[:2000]
                fields[index] = candidate
                changed = True
        return changed, []
    except HarnessLimitExceeded:
        raise
    except (ModelUnavailable, ValueError):
        return False, ["覆盖遗漏的定向修正未完成，已保留原候选与遗漏清单；请人工核对。"]
