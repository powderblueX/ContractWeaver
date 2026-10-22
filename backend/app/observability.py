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

current_operation = ContextVar("contract_operation", default=None)


class OperationRegistry:
    def __init__(self):
        self.records = OrderedDict()
        self.lock = RLock()

    def start(self, workspace_id, action, model):
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
        key = current_operation.get()
        with self.lock:
            if key in self.records:
                self.records[key].update(values)

    def batch(self, index, status, message=""):
        with self.lock:
            record = self.records.get(current_operation.get())
            if record and index < len(record["batches"]):
                record["batches"][index] = {"index": index + 1, "status": status, "message": message}

    def model_event(self, event, model):
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
        with self.lock:
            record = deepcopy(self.records.get(key))
        if record is None:
            return None
        started = record.pop("clock")
        record["elapsed_seconds"] = round(record.get("elapsed_seconds", monotonic() - started), 1)
        return record

    def finish(self, status, message):
        with self.lock:
            record = self.records.get(current_operation.get())
            if record:
                record.update(status=status, message=message, elapsed_seconds=monotonic() - record["clock"])


operations = OperationRegistry()


def observed(action):
    def decorate(method):
        @wraps(method)
        async def run(service, workspace_id, user_id, revision, *args, **kwargs):
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
