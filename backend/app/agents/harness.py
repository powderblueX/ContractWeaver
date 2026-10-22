"""Constrained contract harness: explicit steps, budgets and durable audit events.

The workflow owns routing and human approval. Models cannot register new tools,
execute shell commands, confirm fields or export documents through this runtime.
"""

import asyncio
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from time import monotonic, time
from uuid import uuid4

from app.agents.prompts import PROMPT_VERSION
from app.repositories.agent_runs import AgentRunRepository

current_run = ContextVar("contract_harness_run", default=None)
current_step = ContextVar("contract_harness_step", default=None)

PLANS = {
    "analyze": {
        "plan_next_action": "主控 Agent 根据观察选择下一步",
        "analyze_record": "分析交易类型、最终共识和未定事项",
        "retrieve_templates": "检索原始模板，等待用户选择",
    },
    "extract": {
        "plan_next_action": "主控 Agent 评估复核反馈并分派动作",
        "extract_fields": "分批提取字段与原文证据",
        "review_fields": "独立复核字段映射与分歧",
        "repair_fields": "依据复核反馈定向修正候选",
        "review_coverage": "检查跨字段遗漏，等待人工审核",
    },
}


class HarnessLimitExceeded(ValueError):
    """A finite execution boundary was reached before further external work."""


class ContractHarness:
    def __init__(self, settings, database, workspace_id, user_id, revision, action, publish):
        self.settings = settings
        self.journal = AgentRunRepository(database)
        self.publish = publish
        self.clock = monotonic()
        self.snapshot = {
            "run_id": uuid4().hex,
            "version": "contract-harness/2",
            "plan_kind": "capability_catalog",
            "prompt_version": PROMPT_VERSION,
            "action": action,
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "plan": [{"name": name, "label": label} for name, label in PLANS[action].items()],
            "steps": [],
            "model_requests": 0,
            "requests_started": 0,
            "responses_received": 0,
            "requests_failed": 0,
            "model": settings.llm_model,
            "token_usage": {},
            "thinking_mode": settings.llm_thinking_mode,
            "reasoning_effort": settings.llm_reasoning_effort,
            "limits": {
                "requests": settings.harness_max_requests,
                "steps": settings.harness_max_steps,
                "seconds": settings.harness_timeout_seconds,
                "input_chars": settings.harness_max_input_chars,
            },
            "message": "按受限计划执行；模型建议不能替代用户确认",
        }
        self.journal.start(
            self.snapshot, workspace_id, user_id, revision, time() + settings.harness_timeout_seconds
        )
        self.flush()

    def flush(self):
        self.snapshot["elapsed_seconds"] = round(monotonic() - self.clock, 1)
        self.journal.save(self.snapshot)
        self.publish(harness=deepcopy(self.snapshot))

    def ensure_active(self):
        if monotonic() - self.clock >= self.settings.harness_timeout_seconds:
            raise HarnessLimitExceeded("Agent 已达到执行时间预算，请重试失败批次或人工补充")
        self.journal.assert_active(self.snapshot["run_id"])

    def reserve_request(self, input_chars):
        self.ensure_active()
        if input_chars > self.settings.harness_max_input_chars:
            raise HarnessLimitExceeded("模型输入超过 LAW_HARNESS_MAX_INPUT_CHARS，未发送请求")
        if self.snapshot["model_requests"] >= self.settings.harness_max_requests:
            raise HarnessLimitExceeded("Agent 已达到 LAW_HARNESS_MAX_REQUESTS，未发送更多请求")
        self.snapshot["model_requests"] += 1
        self.flush()

    def record_transport(self, event, model):
        key = {"started": "requests_started", "response": "responses_received", "failed": "requests_failed"}[
            event
        ]
        self.snapshot[key] += 1
        self.snapshot["model"] = model
        self.flush()

    def record_usage(self, usage):
        # Only numeric usage metadata; never persist provider reasoning_content.
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key) if isinstance(usage, dict) else None
            if type(value) is int and value >= 0:
                self.snapshot["token_usage"][key] = self.snapshot["token_usage"].get(key, 0) + value
        self.flush()

    def record_summary(self, summary):
        step = current_step.get()
        if step is not None and isinstance(summary, str):
            step["decision_summary"] = summary[:1000]
            self.flush()

    def record_decision(self, action, target_count):
        step = current_step.get()
        if step is not None:
            step.update(chosen_action=action, target_count=target_count)
            self.flush()

    async def execute(self, name, callback):
        self.ensure_active()
        if name not in PLANS[self.snapshot["action"]]:
            raise HarnessLimitExceeded("该操作不在当前 Agent 工具白名单中")
        if len(self.snapshot["steps"]) >= self.settings.harness_max_steps:
            raise HarnessLimitExceeded("Agent 已达到 LAW_HARNESS_MAX_STEPS")
        step = {
            "index": len(self.snapshot["steps"]) + 1,
            "name": name,
            "label": PLANS[self.snapshot["action"]][name],
            "status": "running",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self.snapshot["steps"].append(step)
        self.flush()
        token = current_step.set(step)
        started = monotonic()
        try:
            result = await callback()
            step["status"] = "completed"
            return result
        except BaseException as error:
            step["status"] = "interrupted" if isinstance(error, asyncio.CancelledError) else "failed"
            step["error_type"] = type(error).__name__  # no provider payload or secret-bearing errors
            raise
        finally:
            step["elapsed_seconds"] = round(monotonic() - started, 1)
            current_step.reset(token)
            self.flush()

    def finish(self, status, message):
        self.snapshot.update(status=status, message=message)
        self.flush()


async def run_step(name, callback):
    """Keep deterministic role tests usable outside a running harness."""
    runtime = current_run.get()
    return await runtime.execute(name, callback) if runtime else await callback()
