"""Versioned API composition with safe, non-network readiness metadata."""

from fastapi import APIRouter

from app.api.auth_routes import router as auth_router
from app.api.template_routes import router as template_router
from app.api.workspace_routes import router as workspace_router
from app.config import get_settings

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(workspace_router)
router.include_router(template_router)


@router.get("/health", tags=["system"])
def health():
    """返回服务就绪状态与公开限制，不返回模型密钥。"""
    settings = get_settings()
    return {
        "status": "ok",
        "model_configured": settings.model_configured,
        "model": settings.llm_model,
        "missing_model_settings": settings.missing_model_settings,
        "max_source_chars": settings.max_source_chars,
        "max_upload_bytes": settings.max_upload_bytes,
        "fields_per_batch": settings.fields_per_batch,
        "supported_source_formats": ["txt", "md", "docx"],
    }
