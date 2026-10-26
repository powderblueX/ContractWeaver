"""Validated account registration and login request bodies."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """邮箱注册请求。"""

    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    """邮箱登录请求。"""

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
