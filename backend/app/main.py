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
    Database(get_settings().database_path).initialize()
    yield


app = FastAPI(title="ContractWeaver", version="0.1.0", lifespan=lifespan)


@app.exception_handler(WorkspaceNotFound)
async def workspace_not_found(_: Request, error: WorkspaceNotFound):
    return JSONResponse(status_code=404, content={"detail": str(error)})


@app.exception_handler(WorkspaceConflict)
async def workspace_conflict(_: Request, error: WorkspaceConflict):
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(ModelUnavailable)
async def model_unavailable(_: Request, error: ModelUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.exception_handler(InvalidContractInput)
async def invalid_workflow_input(_: Request, error: InvalidContractInput):
    return JSONResponse(status_code=400, content={"detail": str(error)})


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(get_settings().cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
