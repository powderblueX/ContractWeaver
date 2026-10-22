"""Bounded evaluator/repair loop; no model action can approve a contract value."""

from dataclasses import dataclass, field

from app.agents.candidate_validation import apply_review, repairable, validate_candidates
from app.agents.field_mapping import model_fields
from app.agents.harness import run_step
from app.domain.contract_workflow import ReviewedField
from app.model_client import ModelUnavailable
from app.observability import operations


@dataclass
class FieldCoordinationResult:
    fields: list[ReviewedField]
    questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repairs: int = 0


class FieldCoordinator:
    def __init__(self, team, settings):
        self.team = team
        self.settings = settings

    async def _review(self, source_lines, specs, fields):
        review = await run_step(
            "review_fields",
            lambda: self.team.review.review(
                source_lines, specs, [field.model_dump(mode="json") for field in fields]
            ),
        )
        apply_review(fields, review)

    async def run(self, source_lines, specs, batch_index):
        operations.batch(batch_index, "extracting", "正在从记录提取填写内容")
        extraction = await run_step(
            "extract_fields", lambda: self.team.extraction.extract(source_lines, specs)
        )
        fields = validate_candidates(extraction, specs, source_lines)
        operations.batch(batch_index, "reviewing", "正在独立复核依据与分歧")
        await self._review(source_lines, specs, fields)
        result = FieldCoordinationResult(fields)
        # Each iteration ends in a model decision, a tool observation, or human handoff.
        for _ in range(self.settings.supervisor_max_repairs + 1):
            eligible = [item for item in result.fields if repairable(item)]
            eligible_specs = [spec for spec in specs if any(item.name == spec["name"] for item in eligible)]
            mapping, descriptions = model_fields(eligible_specs)
            observations = {
                "repair_rounds_used": result.repairs,
                "repairs_remaining": max(0, self.settings.supervisor_max_repairs - result.repairs),
                "repairable_fields": [
                    {
                        **description,
                        "value": item.value,
                        "review_issues": item.review_issues,
                        "status": item.status.value,
                    }
                    for description, item in zip(descriptions, eligible)
                ],
                "missing_fields": [
                    item.display_name or item.name for item in result.fields if not item.value
                ][:30],
            }
            allowed = ["handoff", "request_user"]
            if mapping and result.repairs < self.settings.supervisor_max_repairs:
                allowed.append("repair_fields")
            try:
                decision = await run_step(
                    "plan_next_action",
                    lambda: self.team.supervisor.decide("field_review", source_lines, observations, allowed),
                )
                if decision.action not in allowed:
                    raise ModelUnavailable("主控动作超出当前允许范围")
                if decision.action in ("handoff", "request_user"):
                    result.questions = decision.questions
                    break
                if (
                    not decision.field_ids
                    or len(set(decision.field_ids)) != len(decision.field_ids)
                    or any(key not in mapping for key in decision.field_ids)
                ):
                    raise ModelUnavailable("主控请求修正未知、重复或非问题字段，未执行")
                target_names = {mapping[key] for key in decision.field_ids}
                target_specs = [spec for spec in specs if spec["name"] in target_names]
                previous = [item for item in result.fields if item.name in target_names]
                operations.batch(batch_index, "repairing", f"主控分派定向修正 {len(target_specs)} 个候选")
                repaired = await run_step(
                    "repair_fields", lambda: self.team.extraction.repair(source_lines, target_specs, previous)
                )
                proposed = validate_candidates(repaired, target_specs, source_lines, require_complete=True)
                operations.batch(batch_index, "reviewing", "修正后再次独立复核")
                await self._review(source_lines, target_specs, proposed)
                # Merge only after both repair and a fresh review complete successfully.
                by_name = {item.name: item for item in proposed}
                for item in proposed:
                    item.note = ("主控依据复核反馈进行了定向修正，仍待人工确认。" + item.note)[:2000]
                result.fields = [by_name.get(item.name, item) for item in result.fields]
                result.repairs += 1
            except (ModelUnavailable, ValueError) as error:
                result.warnings.append(
                    f"主控/定向修正未完成，已保留本批最近一次完成复核的候选：{str(error)[:200]}"
                )
                break
        operations.batch(
            batch_index, "completed", f"提取与复核完成，定向修正 {result.repairs} 轮；仍需人工审核"
        )
        return result
