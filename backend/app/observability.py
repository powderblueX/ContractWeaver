"""Bounded, owner-gated live operation telemetry; never store prompts or keys."""

import asyncio
from collections import OrderedDict
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from functools import wraps
from threading import RLock
from time import monotonic

from app.agents.harness import ContractHarness, HarnessLimitExceeded, current_run
from app.domain.errors import WorkspaceConflict

# 当前任务键绑定实时进度；Harness 另行管理持久运行标识和租约。
current_operation = ContextVar("contract_operation", default=None)


class OperationRegistry:
    """有界、线程安全的实时进度缓存，不替代持久日志或后台队列。"""

    def __init__(self):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。"""
        self.records = OrderedDict()
        self.lock = RLock()

    def start(self, workspace_id, action, model):
        """为同一任务创建有界实时记录；重复活动操作会被拒绝。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            action: 当前业务阶段或主控选择的受限动作。
            model: 当前模型适配器或模型标识，不能包含密钥。
        """
        with self.lock:
            previous = self.records.get(workspace_id, {})
            if previous.get("status") == "running":
                raise WorkspaceConflict("此任务已有操作正在运行，请等待完成")
            if len(self.records) >= 200:
                finished = next(
                    (key for key, value in self.records.items() if value["status"] != "running"), None
                )
                if finished is None:
                    raise WorkspaceConflict("服务正在处理较多任务，请稍后重试")
                self.records.pop(finished)
            self.records[workspace_id] = {
                "action": action,
                "status": "running",
                "model": model,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "clock": monotonic(),
                "requests_started": 0,
                "responses_received": 0,
                "requests_failed": 0,
                "batches": [],
                "message": "准备模型输入",
            }

    def update(self, **values):
        """更新当前上下文关联的实时进度；未处于受观测操作时不创建虚假记录。"""
        key = current_operation.get()
        with self.lock:
            if key in self.records:
                self.records[key].update(values)

    def batch(self, index, status, message=""):
        """更新指定批次的阶段和说明，批次完成率不等于合同审核完成率。

        Args:
            index: 当前集合的内部索引。
            status: 当前步骤、传输或业务状态。
            message: 当前阶段或终态的公开简短说明。
        """
        with self.lock:
            record = self.records.get(current_operation.get())
            if record and index < len(record["batches"]):
                record["batches"][index] = {"index": index + 1, "status": status, "message": message}

    def model_event(self, event, model):
        """同步累计真实传输事件到内存进度及当前持久运行记录。

        Args:
            event: 实际传输或流程事件种类。
            model: 当前模型适配器或模型标识，不能包含密钥。
        """
        with self.lock:
            record = self.records.get(current_operation.get())
            if record:
                record["model"] = model
                record[
                    {
                        "started": "requests_started",
                        "response": "responses_received",
                        "failed": "requests_failed",
                    }[event]
                ] += 1

        runtime = current_run.get()
        if runtime:
            runtime.record_transport(event, model)

    def snapshot(self, key):
        """返回去除内部时钟的进度副本，避免调用者修改注册表。

        Args:
            key: 当前查找或更新使用的受控键。
        """
        with self.lock:
            record = deepcopy(self.records.get(key))
        if record is None:
            return None
        started = record.pop("clock")
        record["elapsed_seconds"] = round(record.get("elapsed_seconds", monotonic() - started), 1)
        return record

    def finish(self, status, message):
        """标记内存进度的终态与耗时；持久运行租约由 Harness 终结。

        Args:
            status: 当前步骤、传输或业务状态。
            message: 当前阶段或终态的公开简短说明。
        """
        with self.lock:
            record = self.records.get(current_operation.get())
            if record:
                record.update(status=status, message=message, elapsed_seconds=monotonic() - record["clock"])


operations = OperationRegistry()


def observed(action):
    """为长耗时业务方法添加归属校验、运行租约、超时和终态记录。

    Args:
        action: 当前业务阶段或主控选择的受限动作。
    """

    def decorate(method):
        """把观测与运行管理包装到指定业务方法，保留原方法元信息。

        Args:
            method: 需要被运行管理包装的业务方法。
        """

        @wraps(method)
        async def run(service, workspace_id, user_id, revision, *args, **kwargs):
            """执行被观测的方法；只有业务状态提交成功后才发布运行完成。

            Args:
                service: 依赖注入的业务服务。
                workspace_id: 需要校验归属的合同任务标识。
                user_id: 当前访问资源的账户标识。
                revision: 调用方持有的任务修订号。
            """
            service._load(workspace_id, user_id, revision)  # authorize before publishing any state
            operations.start(workspace_id, action, service.settings.llm_model)
            token = current_operation.set(workspace_id)
            runtime = None
            runtime_token = None
            try:
                runtime = ContractHarness(
                    service.settings,
                    service.repository.database,
                    workspace_id,
                    user_id,
                    revision,
                    action,
                    operations.update,
                )
                runtime_token = current_run.set(runtime)
                async with asyncio.timeout(service.settings.harness_timeout_seconds):
                    result = await method(service, workspace_id, user_id, revision, *args, **kwargs)
                # Completion is visible only after the workflow's database commit succeeds.
                runtime.finish(
                    result.last_run.get("status", "completed"), result.last_run.get("message", "处理完成")
                )
                operations.finish(
                    result.last_run.get("status", "completed"), result.last_run.get("message", "处理完成")
                )
                return result
            except BaseException as error:
                if runtime:
                    runtime.finish(
                        "interrupted" if isinstance(error, asyncio.CancelledError) else "failed",
                        "操作未完成，已保存任务保留；请重试或人工补充",
                    )
                operations.finish("failed", "操作未完成，请查看错误说明；已保存的任务仍保留")
                if isinstance(error, TimeoutError):
                    raise HarnessLimitExceeded(
                        "Agent 已达到 LAW_HARNESS_TIMEOUT_SECONDS，请重试或人工补充"
                    ) from None
                raise
            finally:
                if runtime_token is not None:
                    current_run.reset(runtime_token)
                current_operation.reset(token)

        return run

    return decorate


def finish_run(workspace):
    """在业务提交前检查租约，并把当前运行摘要关联到任务状态。

    Args:
        workspace: 当前合同任务领域快照。
    """
    runtime = current_run.get()
    if runtime:
        runtime.ensure_active()
    partial = bool(
        workspace.extraction_failures or workspace.coordination_warnings
    ) or workspace.coverage_status in ("failed", "unverified")
    workspace.last_run = operations.snapshot(workspace.id) or {}
    workspace.last_run.update(
        status="partial" if partial else "completed",
        message="部分规划、提取或复核未完成，请查看详情并核对" if partial else "处理完成，请审核结果",
    )
    if workspace.last_run.get("harness"):
        workspace.last_run["harness"].update(
            status=workspace.last_run["status"], message=workspace.last_run["message"]
        )
