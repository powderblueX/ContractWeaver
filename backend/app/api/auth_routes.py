"""Account HTTP endpoints; authentication behavior is delegated to services."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_requests import LoginRequest, RegisterRequest
from app.api.dependencies import bearer, current_user, get_database
from app.config import get_settings
from app.database import Database
from app.repositories.accounts import AccountRepository
from app.services.accounts import AccountService, AuthenticationFailed

router = APIRouter(prefix="/auth", tags=["accounts"])


def account_service(database: Database) -> AccountService:
    return AccountService(AccountRepository(database), get_settings())


@router.post("/register", status_code=201)
def register(request: RegisterRequest, database: Database = Depends(get_database)):
    try:
        return account_service(database).register(str(request.email), request.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="该邮箱已注册，请直接登录") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/login")
def login(request: LoginRequest, database: Database = Depends(get_database)):
    try:
        return account_service(database).login(str(request.email), request.password)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/logout")
def logout(
    user: dict = Depends(current_user),
    database: Database = Depends(get_database),
    credentials=Depends(bearer),
):
    account_service(database).logout(credentials.credentials, user["id"])
    return {"ok": True}


@router.get("/me")
def authenticated_account(user: dict = Depends(current_user)):
    return user
