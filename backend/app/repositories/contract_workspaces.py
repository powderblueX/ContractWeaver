"""User-scoped workflow persistence with compare-and-swap revisions."""

from datetime import datetime, timezone

from app.database import Database
from app.domain.contract_workflow import ContractWorkspace
from app.domain.errors import WorkspaceConflict, WorkspaceNotFound


def utc_timestamp() -> str:
    """生成统一的 UTC 时间戳，用于持久状态和执行事件。"""
    return datetime.now(timezone.utc).isoformat()


class ContractWorkspaceRepository:
    """按用户隔离并使用修订号比较交换保存任务的仓储。"""

    def __init__(self, database: Database):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            database: 负责短连接和事务的数据库访问对象。
        """
        self.database = database

    def create(self, workspace: ContractWorkspace, user_id: int) -> ContractWorkspace:
        """为指定用户保存初始任务状态及其修订号。

        Args:
            workspace: 当前合同任务领域快照。
            user_id: 当前访问资源的账户标识。
        """
        with self.database.connection() as connection:
            connection.execute(
                "INSERT INTO contract_workspaces(id,user_id,title,stage,revision,state_json,updated_at) VALUES(?,?,?,?,?,?,?)",
                (
                    workspace.id,
                    user_id,
                    workspace.title,
                    workspace.stage,
                    workspace.revision,
                    workspace.model_dump_json(),
                    workspace.updated_at,
                ),
            )
        return workspace

    def list_workspaces(self, user_id: int) -> list[dict]:
        """读取指定用户的任务摘要，按最近修改时间排序。

        Args:
            user_id: 当前访问资源的账户标识。
        """
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id,title,stage,revision,created_at,updated_at FROM contract_workspaces WHERE user_id=? ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, workspace_id: str, user_id: int) -> ContractWorkspace:
        """按任务和用户双重条件读取状态，避免跨账户访问。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
        """
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT state_json FROM contract_workspaces WHERE id=? AND user_id=?", (workspace_id, user_id)
            ).fetchone()
        if row is None:
            raise WorkspaceNotFound("合同任务不存在")
        return ContractWorkspace.model_validate_json(row["state_json"])

    def save(
        self, workspace: ContractWorkspace, user_id: int, expected_revision: int, artifact: dict | None = None
    ) -> ContractWorkspace:
        """Commit state and artifact ownership together; concurrent edits never overwrite."""
        workspace.revision = expected_revision + 1
        workspace.updated_at = utc_timestamp()
        with self.database.connection() as connection:
            cursor = connection.execute(
                "UPDATE contract_workspaces SET title=?,stage=?,revision=?,state_json=?,updated_at=? WHERE id=? AND user_id=? AND revision=?",
                (
                    workspace.title,
                    workspace.stage,
                    workspace.revision,
                    workspace.model_dump_json(),
                    workspace.updated_at,
                    workspace.id,
                    user_id,
                    expected_revision,
                ),
            )
            if cursor.rowcount != 1:
                raise WorkspaceConflict("任务已被其他操作更新，请重新打开任务后再操作")
            if artifact is not None:
                connection.execute(
                    "INSERT INTO generated_contracts(id,user_id,template_id,filename) VALUES(?,?,?,?)",
                    (artifact["id"], user_id, artifact["template"]["id"], artifact["filename"]),
                )
        return workspace

    def delete(self, workspace_id: str, user_id: int) -> list[str]:
        """删除归属已核验的任务与生成文件，不对目录执行递归删除。

        Args:
            workspace_id: 需要校验归属的合同任务标识。
            user_id: 当前访问资源的账户标识。
        """
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state_json FROM contract_workspaces WHERE id=? AND user_id=?", (workspace_id, user_id)
            ).fetchone()
            if row is None:
                raise WorkspaceNotFound("合同任务不存在")
            workspace = ContractWorkspace.model_validate_json(row["state_json"])
            filenames = []
            for artifact in workspace.artifacts:
                record = connection.execute(
                    "SELECT filename FROM generated_contracts WHERE id=? AND user_id=?",
                    (artifact["id"], user_id),
                ).fetchone()
                if record:
                    filenames.append(record["filename"])
                    connection.execute(
                        "DELETE FROM generated_contracts WHERE id=? AND user_id=?", (artifact["id"], user_id)
                    )
            connection.execute(
                "DELETE FROM contract_workspaces WHERE id=? AND user_id=?", (workspace_id, user_id)
            )
        return filenames

    def find_artifact(self, contract_id: str, user_id: int) -> dict | None:
        """只返回属于指定用户的生成文件记录。

        Args:
            contract_id: 已生成合同的受控标识。
            user_id: 当前访问资源的账户标识。
        """
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT filename FROM generated_contracts WHERE id=? AND user_id=?", (contract_id, user_id)
            ).fetchone()
        return dict(row) if row else None
