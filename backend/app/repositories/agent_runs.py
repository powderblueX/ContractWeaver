"""Owner-scoped run journal and cross-worker execution lease, not a job queue."""

import json
from time import time

from app.domain.errors import WorkspaceConflict


class AgentRunRepository:
    """按用户隔离的运行日志与跨进程租约仓储。"""

    def __init__(self, database):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            database: 负责短连接和事务的数据库访问对象。
        """
        self.database = database

    def start(self, snapshot, workspace_id, user_id, revision, deadline):
        """在短事务内核验修订并获取跨进程租约，同时清理过期活动状态和旧历史。

        Args:
            snapshot: 运行或领域状态的当前快照。
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            revision: 调用方持有的任务修订号。
            deadline: 本次租约到期的 Unix 时间。
        """
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT revision FROM contract_workspaces WHERE id=? AND user_id=?",
                (workspace_id, user_id),
            ).fetchone()
            if row is None or row["revision"] != revision:
                raise WorkspaceConflict("任务已更新，请重新打开后操作")
            # A crashed worker cannot hold a lease beyond the bounded run deadline.
            connection.execute(
                "UPDATE contract_agent_runs SET status='interrupted' WHERE workspace_id=? AND status='running' AND deadline<=?",
                (workspace_id, time()),
            )
            active = connection.execute(
                "SELECT id FROM contract_agent_runs WHERE workspace_id=? AND status='running'",
                (workspace_id,),
            ).fetchone()
            if active:
                raise WorkspaceConflict("此任务已有 Agent 执行中，请等待完成")
            connection.execute(
                "INSERT INTO contract_agent_runs VALUES(?,?,?,?,?,?,?)",
                (
                    snapshot["run_id"],
                    workspace_id,
                    user_id,
                    "running",
                    deadline,
                    json.dumps(snapshot, ensure_ascii=False),
                    snapshot["started_at"],
                ),
            )
            # Keep the most recent 20 runs per task, including failures.
            connection.execute(
                "DELETE FROM contract_agent_runs WHERE workspace_id=? AND status!='running' AND id NOT IN (SELECT id FROM contract_agent_runs WHERE workspace_id=? ORDER BY created_at DESC LIMIT 20)",
                (workspace_id, workspace_id),
            )

    def save(self, snapshot):
        """仅更新仍处于活动状态的运行，过期旧执行者不能覆盖替代运行。

        Args:
            snapshot: 运行或领域状态的当前快照。
        """
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE contract_agent_runs SET status=?,snapshot_json=? WHERE id=? AND status='running'",
                (snapshot["status"], json.dumps(snapshot, ensure_ascii=False), snapshot["run_id"]),
            )

    def assert_active(self, run_id):
        """检查持久运行记录是否仍在有效租期内。

        Args:
            run_id: 持久执行日志的唯一运行标识。
        """
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT status,deadline FROM contract_agent_runs WHERE id=?", (run_id,)
            ).fetchone()
        if row is None or row["status"] != "running" or row["deadline"] <= time():
            raise WorkspaceConflict("Agent 运行租约已结束，请重新打开任务后操作")

    def list(self, workspace_id, user_id, limit=20):
        """按用户和任务读取最近运行记录，并将过期活动记录呈现为中断。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
            limit: 结果数量上限，仍受服务端范围约束。
        """
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT status,deadline,snapshot_json FROM contract_agent_runs WHERE workspace_id=? AND user_id=? ORDER BY created_at DESC LIMIT ?",
                (workspace_id, user_id, max(1, min(limit, 20))),
            ).fetchall()
        results = []
        for row in rows:
            snapshot = json.loads(row["snapshot_json"])
            if row["status"] == "interrupted" or (row["status"] == "running" and row["deadline"] <= time()):
                snapshot.update(
                    status="interrupted", message="执行期限已过，可能因服务重启或中断；请重新发起或人工补充"
                )
                for step in snapshot.get("steps", []):
                    if step["status"] == "running":
                        step["status"] = "interrupted"
            results.append(snapshot)
        return results
