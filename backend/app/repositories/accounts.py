"""Account and revocable session persistence."""

from app.database import Database


class AccountRepository:
    def __init__(self, db: Database):
        self.db = db

    def create(self, username: str, email: str, password_hash: str) -> dict:
        with self.db.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO users(username,email,password_hash) VALUES(?,?,?)",
                (username, email, password_hash),
            )
            return {"id": cursor.lastrowid, "username": username, "email": email}

    def find_by_email(self, identity: str):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT id,username,email,password_hash FROM users WHERE lower(email)=?",
                (identity.strip().lower(),),
            ).fetchone()
            return dict(row) if row else None

    def upgrade_password(self, user_id: int, password_hash: str) -> None:
        with self.db.connection() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))

    def save_token(self, digest: str, user_id: int, expiry: str) -> None:
        with self.db.connection() as conn:
            conn.execute(
                "INSERT INTO access_tokens(token_hash,user_id,expires_at) VALUES(?,?,?)",
                (digest, user_id, expiry),
            )

    def find_token(self, digest: str):
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT u.id,u.username,u.email,t.expires_at FROM access_tokens t "
                "JOIN users u ON u.id=t.user_id WHERE t.token_hash=?",
                (digest,),
            ).fetchone()
            return dict(row) if row else None

    def delete_token(self, digest: str, user_id: int) -> None:
        with self.db.connection() as conn:
            conn.execute("DELETE FROM access_tokens WHERE token_hash=? AND user_id=?", (digest, user_id))
