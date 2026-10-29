"""Bounded evaluator/repair loop; no model action can approve a contract value."""

from dataclasses import dataclass, field

from app.agents.candidate_validation import apply_review, repairable, validate_candidates
from app.agents.field_mapping import model_fields
from app.agents.harness import HarnessLimitExceeded, run_step
from app.domain.contract_workflow import FieldStatus, ReviewedField
from app.model_client import ModelUnavailable
from app.observability import operations


@dataclass
class FieldCoordinationResult:
    """携带一批最近完成复核的候选、补充问题、降级提示和已完成修正轮数。"""

    fields: list[ReviewedField]
    questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    repairs: int = 0
    failures: list[dict] = field(default_factory=list)


class FieldCoordinator:
    """组织提取、独立复核和受限定向修正的批次协调器。"""

    def __init__(self, team, settings):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            team: 共享连接、角色上下文隔离的 Agent 团队。
            settings: 已解析的运行配置，包含路径、模型及预算；不得公开密钥。
        """
        self.team = team
        self.settings = settings

    @staticmethod
    def _failure(specs, error, phase):
        """Describe only the failed fields and stage, without provider payloads."""
        public = error.public_error() if isinstance(error, ModelUnavailable) else {
            "code": "model_schema", "message": "模型结果未通过校验", "retryable": True,
            "hint": "可重试未完成部分，或人工核对候选。"}
        if isinstance(error, HarnessLimitExceeded):
            public = {"code": "execution_budget", "message": "本次执行预算已用尽，候选已保留",
                      "retryable": True, "hint": "可仅重试未完成的复核，或人工核对。"}
        if phase == "review":
            public = {**public, "message": "独立复核未完成，已保留提取候选。" + public["message"],
                      "hint": "重试时只复核已保留的候选；也可人工核对。" + public.get("hint", "")}
        return {"field_names": [spec["name"] for spec in specs], "phase": phase,
                "message": public["message"], "error": public}

    async def _extract(self, source_lines, specs, depth=0):
        """Split truncated batches at most twice; keep successful sibling results."""
        try:
            extraction = await run_step(
                "extract_fields", lambda: self.team.extraction.extract(source_lines, specs))
            return FieldCoordinationResult(validate_candidates(extraction, specs, source_lines))
        except HarnessLimitExceeded:
            raise
        except (ModelUnavailable, ValueError) as error:
            if isinstance(error, ModelUnavailable) and error.code == "output_truncated" and getattr(error, "allow_batch_split", True) and len(specs) > 1 and depth < 2:
                operations.batch(self.batch_index, "extracting", "输出过长，已缩小批次重新提取")
                middle = len(specs) // 2
                left = await self._extract(source_lines, specs[:middle], depth + 1)
                right = await self._extract(source_lines, specs[middle:], depth + 1)
                return FieldCoordinationResult(left.fields + right.fields, failures=left.failures + right.failures)
            return FieldCoordinationResult([ReviewedField(**spec) for spec in specs],
                                           failures=[self._failure(specs, error, "extract")])

    async def _review(self, source_lines, specs, fields, depth=0):
        """Retry only smaller reviews on truncation; preserve unchecked proposals on failure."""
        try:
            review = await run_step("review_fields", lambda: self.team.review.review(
                source_lines, specs, [item.model_dump(mode="json") for item in fields]))
            apply_review(fields, review)
            return []
        except (ModelUnavailable, ValueError) as error:
            if isinstance(error, ModelUnavailable) and error.code == "output_truncated" and getattr(error, "allow_batch_split", True) and len(specs) > 1 and depth < 2:
                operations.batch(self.batch_index, "reviewing", "输出过长，复用提取候选并分组复核")
                middle = len(specs) // 2
                left_names = {spec["name"] for spec in specs[:middle]}
                left = await self._review(source_lines, specs[:middle],
                                          [item for item in fields if item.name in left_names], depth + 1)
                right = await self._review(source_lines, specs[middle:],
                                           [item for item in fields if item.name not in left_names], depth + 1)
                return left + right
            for item in fields:
                item.review_issues.append("独立复核未完成：候选已保留，请重试复核或人工确认")
                if item.status == FieldStatus.EXTRACTED:
                    item.status = FieldStatus.UNVERIFIED
            return [self._failure(specs, error, "review")]

    async def run(self, source_lines, specs, batch_index, previous_fields=None):
        """Retain proposals across review failures; cached review retries never re-extract them."""
        self.batch_index = batch_index
        operations.batch(batch_index, "extracting", "正在处理字段候选与复核")
        cached = {item.name: item.model_copy(deep=True) for item in previous_fields or []}
        for item in cached.values():
            item.review_issues = [issue for issue in item.review_issues if not issue.startswith("独立复核未完成：")]
            if item.status == FieldStatus.UNVERIFIED and item.value and item.evidence and not item.review_issues:
                item.status = FieldStatus.EXTRACTED
        fresh_specs = [spec for spec in specs if spec["name"] not in cached]
        result = await self._extract(source_lines, fresh_specs) if fresh_specs else FieldCoordinationResult([])
        by_name = {item.name: item for item in result.fields}
        by_name.update(cached)
        result.fields = [by_name[spec["name"]] for spec in specs]
        failed_names = {name for failure in result.failures for name in failure["field_names"]}
        review_specs = [spec for spec in specs if spec["name"] not in failed_names]
        fields = [item for item in result.fields if item.name not in failed_names]
        if review_specs:
            operations.batch(batch_index, "reviewing", "正在独立复核依据与分歧")
            result.failures.extend(await self._review(source_lines, review_specs, fields))
        if result.failures:
            retained = sum(bool(item.value) for item in result.fields)
            operations.batch(batch_index, "failed", f"部分提取或复核未完成；已保留 {retained} 个有值候选，仍待人工核对")
            return result
        # Each iteration ends in a model decision, a tool observation, or human handoff.
        for _ in range(self.settings.supervisor_max_repairs + 1):
            eligible = [item for item in result.fields if repairable(item)]
            # 每轮只给问题字段生成新的批内短编号，禁止借修正动作改写无关或人工审核项。
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
                if await self._review(source_lines, target_specs, proposed):
                    raise ModelUnavailable("修正后的复核未完成，已保留之前完成复核的候选")
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
