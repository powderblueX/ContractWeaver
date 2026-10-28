"""Application composition root."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import router
from app.config import get_settings
from app.database import Database
from app.domain.errors import InvalidContractInput, WorkspaceConflict, WorkspaceNotFound
from app.model_client import ModelUnavailable


@asynccontextmanager
async def lifespan(_: FastAPI):
    """初始化数据库表结构，随后将控制权交给应用请求生命周期。"""
    Database(get_settings().database_path).initialize()
    yield


app = FastAPI(title="ContractWeaver", version="0.1.0", lifespan=lifespan)


@app.exception_handler(WorkspaceNotFound)
async def workspace_not_found(_: Request, error: WorkspaceNotFound):
    """将任务不存在或不可见的领域异常转换为一致的 HTTP 404。

    Args:
        error: 需要映射为安全公开错误的异常。
    """
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(WorkspaceConflict)
async def workspace_conflict(_: Request, error: WorkspaceConflict):
    """将修订或并发冲突转换为 HTTP 409，提醒客户端刷新状态。

    Args:
        error: 需要映射为安全公开错误的异常。
    """
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(ModelUnavailable)
async def model_unavailable(_: Request, error: ModelUnavailable):
    """将模型连接、配置或输出错误转换为可展示的 HTTP 503。

    Args:
        error: 需要映射为安全公开错误的异常。
    """
    return JSONResponse(status_code=503, content={"detail": str(error), "error": error.public_error()})


@app.exception_handler(InvalidContractInput)
async def invalid_workflow_input(_: Request, error: InvalidContractInput):
    """将可预期的业务参数错误转换为 HTTP 400。

    Args:
        error: 需要映射为安全公开错误的异常。
    """
    return JSONResponse(status_code=400, content={"detail": str(error)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
