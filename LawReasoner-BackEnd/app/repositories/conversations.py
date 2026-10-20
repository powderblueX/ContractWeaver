"""User-scoped conversation and generated document persistence."""

from __future__ import annotations

import json

from app.database import Database


class SessionNotFound(LookupError):
    pass


class ConversationRepository:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _require(conn, session_id: str, user_id: int):
        row = conn.execute("SELECT * FROM agent_sessions WHERE id=? AND user_id=?", (session_id, user_id)).fetchone()
        if row is None:
            raise SessionNotFound("会话不存在")
        return row

    def list(self, user_id: int) -> list[dict]:
        with self.db.connection() as conn:
            rows = conn.execute("SELECT id,title,created_at,updated_at FROM agent_sessions WHERE user_id=? ORDER BY updated_at DESC", (user_id,)).fetchall()
            return [dict(row) for row in rows]

    def detail(self, session_id: str, user_id: int) -> dict:
        with self.db.connection() as conn:
            session = self._require(conn, session_id, user_id)
            rows = conn.execute("SELECT id,role,content,trace_json,created_at FROM agent_messages WHERE session_id=? ORDER BY id", (session_id,)).fetchall()
            messages = [{**dict(row), "trace": json.loads(row["trace_json"] or "[]")} for row in rows]
            return {"session": dict(session), "messages": messages}

    def history(self, session_id: str, user_id: int) -> list[dict]:
        with self.db.connection() as conn:
            self._require(conn, session_id, user_id)
            rows = conn.execute("SELECT role,content,trace_json FROM agent_messages WHERE session_id=? ORDER BY id DESC LIMIT 16", (session_id,)).fetchall()
        history = []
        for row in reversed(rows):
            content = row["content"]
            if row["role"] == "assistant" and row["trace_json"]:
                # Tool IDs and verified results must survive into the next turn.
                content += "\n[上轮工具记录] " + row["trace_json"][:4000]
            history.append({"role": row["role"], "content": content})
        return history

    def save_run(self, session_id: str, user_id: int, message: str, result: dict, new_session: bool) -> None:
        with self.db.connection() as conn:
            if new_session:
                conn.execute("INSERT INTO agent_sessions(id,user_id,title) VALUES(?,?,?)", (session_id, user_id, message[:50]))
            else:
                self._require(conn, session_id, user_id)
            conn.execute("INSERT INTO agent_messages(session_id,role,content) VALUES(?,?,?)", (session_id, "user", message))
            conn.execute("INSERT INTO agent_messages(session_id,role,content,trace_json) VALUES(?,?,?,?)", (session_id, "assistant", result["answer"], json.dumps(result["trace"], ensure_ascii=False)))
            conn.execute("UPDATE agent_sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?", (session_id,))
            for artifact in result["artifacts"]:
                conn.execute("INSERT INTO generated_contracts(id,user_id,template_id,filename) VALUES(?,?,?,?)", (artifact["id"], user_id, artifact["template"]["id"], artifact["filename"]))

    def rename(self, session_id: str, user_id: int, title: str) -> None:
        with self.db.connection() as conn:
            self._require(conn, session_id, user_id)
            conn.execute("UPDATE agent_sessions SET title=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (title, session_id))

    def delete(self, session_id: str, user_id: int) -> None:
        with self.db.connection() as conn:
            self._require(conn, session_id, user_id)
            conn.execute("DELETE FROM agent_sessions WHERE id=?", (session_id,))

    def generated_contract(self, contract_id: str, user_id: int):
        with self.db.connection() as conn:
            row = conn.execute("SELECT filename,template_id FROM generated_contracts WHERE id=? AND user_id=?", (contract_id, user_id)).fetchone()
            return dict(row) if row else None
