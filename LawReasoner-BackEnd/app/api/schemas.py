"""Validated public request and response bodies."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class RunRequest(BaseModel):
    message: str = Field(min_length=2, max_length=12000)
    session_id: str | None = None
    allow_draft: bool = False


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
