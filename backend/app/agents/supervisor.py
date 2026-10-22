"""Model-selected actions validated against the controller's current affordances."""

from typing import Literal

from pydantic import create_model

from app.agents.harness import current_run
from app.agents.prompts import SUPERVISOR_PROMPT
from app.domain.contract_workflow import SupervisorDecision
from app.model_client import ModelUnavailable


class SupervisorAgent:
    def __init__(self, model):
        self.model = model

    async def decide(self, phase, source_lines, observations, allowed_actions):
        schema = create_model(
            "AllowedSupervisorDecision",
            __base__=SupervisorDecision,
            action=(Literal.__getitem__(tuple(allowed_actions)), ...),
        )
        decision = await self.model.generate_structured(
            SUPERVISOR_PROMPT,
            {
                "phase": phase,
                "source_lines": source_lines,
                "observations": observations,
                "allowed_actions": allowed_actions,
            },
            schema,
        )
        if decision.action not in allowed_actions:
            raise ModelUnavailable("主控返回了当前不允许的动作")
        if (decision.action != "repair_fields" and decision.field_ids) or (
            decision.action == "repair_fields" and not decision.field_ids
        ):
            raise ModelUnavailable("主控修正目标与动作不匹配")
        if len(set(decision.field_ids)) != len(decision.field_ids):
            raise ModelUnavailable("主控返回重复字段编号")
        if (decision.action != "request_user" and decision.questions) or (
            decision.action == "request_user" and not any(q.strip() for q in decision.questions)
        ):
            raise ModelUnavailable("主控补充问题与动作不匹配")
        if decision.action != "retrieve_templates" and decision.search_query:
            raise ModelUnavailable("主控在非检索动作中返回检索词")
        decision.questions = list(
            dict.fromkeys(question.strip() for question in decision.questions if question.strip())
        )
        runtime = current_run.get()
        if runtime:
            runtime.record_decision(decision.action, len(decision.field_ids))
        return decision
