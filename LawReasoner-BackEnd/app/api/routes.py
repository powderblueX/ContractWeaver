"""HTTP adapters: validate input, invoke use cases and map domain errors."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import bearer, current_user, get_db
from app.api.schemas import LoginRequest, RegisterRequest, RenameRequest, RunRequest
from app.config import get_settings
from app.database import Database
from app.model_client import ModelUnavailable
from app.repositories.accounts import AccountRepository
from app.repositories.conversations import ConversationRepository, SessionNotFound
from app.services.accounts import AccountService, AuthenticationFailed
from app.services.contract_templates import ContractTemplateCatalog
from app.services.conversations import ConversationService


router = APIRouter(prefix="/api/v1")


def account_service(db: Database) -> AccountService:
    return AccountService(AccountRepository(db), get_settings())


def conversation_repository(db: Database) -> ConversationRepository:
    return ConversationRepository(db)


def contract_template_catalog() -> ContractTemplateCatalog:
    settings = get_settings()
    return ContractTemplateCatalog(settings.resources_dir, settings.generated_dir, settings.embedding_model_path)


@router.get("/health")
def health():
    return {"status": "ok", "model_configured": bool(get_settings().llm_api_key.get_secret_value())}


@router.post("/auth/register", status_code=201)
def register(request: RegisterRequest, db: Database = Depends(get_db)):
    try:
        return account_service(db).register(request.username, request.email, request.password)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="用户名或邮箱已存在") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/auth/login")
def login(request: LoginRequest, db: Database = Depends(get_db)):
    try:
        return account_service(db).login(request.username, request.password)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/auth/logout")
def logout(user: dict = Depends(current_user), db: Database = Depends(get_db), credentials=Depends(bearer)):
    account_service(db).logout(credentials.credentials, user["id"])
    return {"ok": True}


@router.get("/auth/me")
def me(user: dict = Depends(current_user)):
    return user


@router.get("/agent/sessions")
def sessions(user: dict = Depends(current_user), db: Database = Depends(get_db)):
    return conversation_repository(db).list(user["id"])


@router.get("/agent/sessions/{session_id}")
def session_detail(session_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    try:
        return conversation_repository(db).detail(session_id, user["id"])
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/agent/sessions/{session_id}")
def rename_session(session_id: str, request: RenameRequest, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    try:
        conversation_repository(db).rename(session_id, user["id"], request.title.strip())
        return {"ok": True}
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/agent/sessions/{session_id}")
def delete_session(session_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    try:
        conversation_repository(db).delete(session_id, user["id"])
        return {"ok": True}
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agent/runs")
async def run_agent(request: RunRequest, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    try:
        return await ConversationService(conversation_repository(db), get_settings()).run(user["id"], request.message, request.session_id, request.allow_draft)
    except SessionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/contracts/templates")
def templates(group: str | None = None, query: str = "", limit: int = 30, user: dict = Depends(current_user)):
    try:
        return contract_template_catalog().list_templates(group, query, limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/contracts/templates/{template_id}")
def template_detail(template_id: str, user: dict = Depends(current_user)):
    try:
        return contract_template_catalog().describe_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/contracts/{contract_id}/download")
def download(contract_id: str, user: dict = Depends(current_user), db: Database = Depends(get_db)):
    record = conversation_repository(db).generated_contract(contract_id, user["id"])
    if record is None:
        raise HTTPException(status_code=404, detail="合同文件不存在")
    generated = get_settings().generated_dir.resolve()
    path = (generated / record["filename"]).resolve()
    if not path.is_relative_to(generated) or not path.is_file():
        raise HTTPException(status_code=404, detail="合同文件不存在")
    return FileResponse(path, filename=f"合同_{contract_id[:8]}.docx", media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
