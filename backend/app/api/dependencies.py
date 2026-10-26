"""接口依赖项。"""

from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.database import Database
from app.repositories.accounts import AccountRepository
from app.services.accounts import AccountService, AuthenticationFailed

bearer = HTTPBearer(auto_error=False)


@lru_cache
def get_database() -> Database:
    """返回数据库访问对象。"""
    return Database(get_settings().database_path)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer), db: Database = Depends(get_database)
) -> dict:
    """验证访问令牌并返回当前账户。"""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    try:
        return AccountService(AccountRepository(db), get_settings()).current_user(credentials.credentials)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
