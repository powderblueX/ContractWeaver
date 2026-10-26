"""账户认证服务。"""

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings
from app.repositories.accounts import AccountRepository
from app.security import hash_password, new_token, token_hash, verify_password


class AuthenticationFailed(ValueError):
    """认证失败。"""

    pass


class AccountService:
    """账户认证服务。"""

    def __init__(self, repository: AccountRepository, settings: Settings):
        """保存账户仓储和认证配置。"""
        self.repository = repository
        self.settings = settings

    def register(self, email: str, password: str) -> dict:
        """创建邮箱账户。"""
        email = email.strip().lower()
        if self.repository.find_by_email(email):
            raise sqlite3.IntegrityError("Email already exists")
        # 旧表的 username 非空约束要求保留内部兼容值。
        result = self.repository.create("account_" + uuid4().hex, email, hash_password(password))
        return {key: result[key] for key in ("id", "email")}

    def login(self, identity: str, password: str) -> dict:
        """验证账户并创建会话。"""
        user = self.repository.find_by_email(identity)
        if user is None or not verify_password(password, user["password_hash"]):
            raise AuthenticationFailed("邮箱或密码错误")
        if user["password_hash"].startswith(("$2a$", "$2b$", "$2y$")):
            self.repository.upgrade_password(user["id"], hash_password(password))
        token, digest, expiry = new_token(self.settings.token_hours)
        self.repository.save_token(digest, user["id"], expiry)
        return {
            "access_token": token,
            "token_type": "bearer",
            "expires_at": expiry,
            "user": {key: user[key] for key in ("id", "email")},
        }

    def current_user(self, token: str) -> dict:
        """读取有效会话对应的账户。"""
        row = self.repository.find_token(token_hash(token))
        if row is None or datetime.fromisoformat(row["expires_at"]) <= datetime.now(timezone.utc):
            raise AuthenticationFailed("登录已过期")
        return {key: row[key] for key in ("id", "email")}

    def logout(self, token: str, user_id: int) -> None:
        """撤销当前访问令牌。"""
        self.repository.delete_token(token_hash(token), user_id)
