"""One-time, idempotent import of legacy users and chat records.

The source database is kept intact. Legacy bcrypt passwords are upgraded to
PBKDF2 after a successful login, so no plaintext password is needed here.
"""

import sqlite3
from pathlib import Path

from app.config import BASE_DIR, get_settings
from app.database import Database


def migrate(source: Path | None = None) -> dict[str, int]:
    """幂等导入旧版用户、会话和聊天消息；保持来源数据库不变。

    Args:
        source: 旧版 SQLite 数据库路径；迁移前应备份目标数据库。
    """
    source = source or BASE_DIR / "data" / "legacy_shared_db.db"
    if not source.is_file():
        raise FileNotFoundError(source)
    db = Database(get_settings().database_path)
    db.initialize()
    counts = {"users": 0, "sessions": 0, "messages": 0}
    with sqlite3.connect(source) as old, db.connection() as new:
        old.row_factory = sqlite3.Row
        for user in old.execute("SELECT * FROM users"):
            cursor = new.execute(
                "INSERT OR IGNORE INTO users(id,username,email,password_hash,created_at) VALUES(?,?,?,?,?)",
                (
                    user["id"],
                    user["username"],
                    user["email"],
                    user["hashed_password"],
                    user["created_at"] or "1970-01-01",
                ),
            )
            counts["users"] += cursor.rowcount
        for session in old.execute("SELECT * FROM chat_sessions"):
            identifier = f"legacy-{session['id']}"
            cursor = new.execute(
                "INSERT OR IGNORE INTO agent_sessions(id,user_id,title,created_at,updated_at) VALUES(?,?,?,?,?)",
                (
                    identifier,
                    session["user_id"],
                    session["title"],
                    session["created_at"],
                    session["updated_at"],
                ),
            )
            counts["sessions"] += cursor.rowcount
        for message in old.execute("SELECT * FROM chat_messages"):
            identifier = f"legacy-{message['session_id']}"
            # Stable high IDs make repeated imports safe and preserve message order.
            cursor = new.execute(
                "INSERT OR IGNORE INTO agent_messages(id,session_id,role,content,created_at) VALUES(?,?,?,?,?)",
                (
                    1_000_000_000 + message["id"] * 2,
                    identifier,
                    "user",
                    message["content"],
                    message["created_at"],
                ),
            )
            counts["messages"] += cursor.rowcount
            if message["response"]:
                cursor = new.execute(
                    "INSERT OR IGNORE INTO agent_messages(id,session_id,role,content,created_at) VALUES(?,?,?,?,?)",
                    (
                        1_000_000_000 + message["id"] * 2 + 1,
                        identifier,
                        "assistant",
                        message["response"],
                        message["created_at"],
                    ),
                )
                counts["messages"] += cursor.rowcount
    return counts


if __name__ == "__main__":
    print(migrate())
