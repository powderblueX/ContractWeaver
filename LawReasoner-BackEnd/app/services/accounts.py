"""Authentication use cases independent of FastAPI."""

from datetime import datetime, timezone

from app.config import Settings
from app.repositories.accounts import AccountRepository
from app.security import hash_password, new_token, token_hash, verify_password


class AuthenticationFailed(ValueError):
    pass


class AccountService:
    def __init__(self, repository: AccountRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    def register(self, username: str, email: str, password: str) -> dict:
        username = username.strip()
        if len(username) < 2:
            raise ValueError("用户名至少需要两个字符")
        return self.repository.create(username, email.lower(), hash_password(password))

    def login(self, identity: str, password: str) -> dict:
        user = self.repository.find_by_identity(identity)
        if user is None or not verify_password(password, user["password_hash"]):
            raise AuthenticationFailed("用户名或密码错误")
        if user["password_hash"].startswith(("$2a$", "$2b$", "$2y$")):
            self.repository.upgrade_password(user["id"], hash_password(password))
        token, digest, expiry = new_token(self.settings.token_hours)
        self.repository.save_token(digest, user["id"], expiry)
        return {"access_token": token, "token_type": "bearer", "expires_at": expiry, "user": {key: user[key] for key in ("id", "username", "email")}}

    def current_user(self, token: str) -> dict:
        row = self.repository.find_token(token_hash(token))
        if row is None or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            raise AuthenticationFailed("登录已过期")
        return {key: row[key] for key in ("id", "username", "email")}

    def logout(self, token: str, user_id: int) -> None:
        self.repository.delete_token(token_hash(token), user_id)
