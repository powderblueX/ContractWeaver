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

# ContextVar 随异步任务传播，避免并发用户的预算与日志串到同一个全局变量。
current_run = ContextVar("contract_harness_run", default=None)
# 当前步骤对象仅用于将摘要/所选动作关联到正确调用，不保存原始提示词。
current_step = ContextVar("contract_harness_step", default=None)

# 能力目录用于声明可选动作，协调器会根据当前阶段进一步收窄权限。
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
    """约束执行权限和预算，并持久记录实际动作的运行容器。"""

    def __init__(self, settings, database, workspace_id, user_id, revision, action, publish):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            settings: 已解析的运行配置，包含路径、模型及预算；不得公开密钥。
            database: 负责短连接和事务的数据库访问对象。
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            action: 当前业务阶段或主控选择的受限动作。
            publish: 向实时进度层发布脱敏快照的回调。
        """
        self.settings = settings
        self.journal = AgentRunRepository(database)
        self.publish = publish
        self.clock = monotonic()
        # 仅衡量本进程耗时；持久租约使用 Unix 到期时间，不能把单调时钟写成跨进程时间。
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
        """持久化当前运行快照并发布副本，避免界面修改共享状态。"""
        self.snapshot["elapsed_seconds"] = round(monotonic() - self.clock, 1)
        self.journal.save(self.snapshot)
        self.publish(harness=deepcopy(self.snapshot))

    def ensure_active(self):
        """校验总时间预算及数据库租约，阻止过期运行继续请求或提交。"""
        if monotonic() - self.clock >= self.settings.harness_timeout_seconds:
            raise HarnessLimitExceeded("Agent 已达到执行时间预算，请重试失败批次或人工补充")
        self.journal.assert_active(self.snapshot["run_id"])

    def reserve_request(self, input_chars):
        """在 HTTP 发送前预留共享请求额度，并检查单次输入大小。

        Args:
            input_chars: 序列化请求的字符数量，不等于 Token 数。
        """
        self.ensure_active()
        if input_chars > self.settings.harness_max_input_chars:
            raise HarnessLimitExceeded("模型输入超过 LAW_HARNESS_MAX_INPUT_CHARS，未发送请求")
        if self.snapshot["model_requests"] >= self.settings.harness_max_requests:
            raise HarnessLimitExceeded("Agent 已达到 LAW_HARNESS_MAX_REQUESTS，未发送更多请求")
        self.snapshot["model_requests"] += 1
        self.flush()

    def record_transport(self, event, model):
        """累计真实 HTTP 发起、成功响应或失败次数，并同步执行日志。

        Args:
            event: 实际传输或流程事件种类。
            model: 当前模型适配器或模型标识，不能包含密钥。
        """
        key = {"started": "requests_started", "response": "responses_received", "failed": "requests_failed"}[
            event
        ]
        self.snapshot[key] += 1
        self.snapshot["model"] = model
        self.flush()

    def record_usage(self, usage):
        # Only numeric usage metadata; never persist provider reasoning_content.
        """仅累计服务商返回的非负 Token 数，不存储提示词或内部推理内容。

        Args:
            usage: 仅包含服务商报告的数值 Token 统计。
        """
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key) if isinstance(usage, dict) else None
            if type(value) is int and value >= 0:
                self.snapshot["token_usage"][key] = self.snapshot["token_usage"].get(key, 0) + value
        self.flush()

    def record_response(self, diagnostics):
        """Attach numeric response statistics to its concurrent step, never raw content."""
        step = current_step.get()
        if step is not None:
            step.setdefault("responses", []).append(dict(diagnostics))
            self.flush()

    def record_summary(self, summary):
        """将结构校验后的简短结论关联到当前步骤，不记录完整推理过程。

        Args:
            summary: 模型返回并通过结构校验的简短解释。
        """
        step = current_step.get()
        if step is not None and isinstance(summary, str):
            step["decision_summary"] = summary[:1000]
            self.flush()

    def record_decision(self, action, target_count):
        """记录模型选择的动作及目标数量；记录决策不代表工具已执行成功。

        Args:
            action: 当前业务阶段或主控选择的受限动作。
            target_count: 本次主控动作关联的字段数量。
        """
        step = current_step.get()
        if step is not None:
            step.update(chosen_action=action, target_count=target_count)
            self.flush()

    async def execute(self, name, callback):
        """在白名单和预算约束下执行一步，并持久记录完成、失败或取消状态。

        Args:
            name: 字段、步骤或模板的受控名称。
            callback: 本步骤实际执行的异步操作。
        """
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
            if callable(getattr(error, "public_error", None)):
                step["error"] = error.public_error()
            raise
        finally:
            step["elapsed_seconds"] = round(monotonic() - started, 1)
            current_step.reset(token)
            self.flush()

    def finish(self, status, message):
        """写入终态与说明，释放本次运行占用的活动租约。

        Args:
            status: 当前步骤、传输或业务状态。
            message: 当前阶段或终态的公开简短说明。
        """
        self.snapshot.update(status=status, message=message)
        self.flush()


async def run_step(name, callback):
    """Keep deterministic role tests usable outside a running harness."""
    runtime = current_run.get()
    return await runtime.execute(name, callback) if runtime else await callback()
