"""User-scoped source, template choice, review and export operations."""

from fastapi import APIRouter, Depends, File, UploadFile
from starlette.concurrency import run_in_threadpool

from app.api.contract_requests import (
    CreateWorkspaceRequest,
    ExtractFieldsRequest,
    GenerateContractRequest,
    RenameWorkspaceRequest,
    ReviewFieldsRequest,
    RevisionRequest,
    SelectTemplateRequest,
)
from app.api.dependencies import current_user
from app.api.workspace_dependencies import get_workflow_service
from app.config import get_settings
from app.observability import operations
from app.repositories.agent_runs import AgentRunRepository
from app.services.contract_workflow import ContractWorkflowService
from app.services.source_records import parse_source_file

router = APIRouter(tags=["contract workspaces"])


@router.post("/sources/parse")
async def parse_source(file: UploadFile = File(...), user: dict = Depends(current_user)):
    settings = get_settings()
    try:
        content = await file.read(settings.max_upload_bytes + 1)
        text = await run_in_threadpool(parse_source_file, file.filename or "", content, settings)
        return {
            "source_name": (file.filename or "协商记录")[:255],
            "source_text": text,
            "character_count": len(text),
        }
    finally:
        await file.close()


@router.get("/workspaces")
def list_workspaces(
    user: dict = Depends(current_user), service: ContractWorkflowService = Depends(get_workflow_service)
):
    return service.repository.list_workspaces(user["id"])


@router.post("/workspaces", status_code=201)
def create_workspace(
    request: CreateWorkspaceRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.create(user["id"], request.title, request.source_name, request.source_text)


@router.get("/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.present_workspace(service.repository.get(workspace_id, user["id"]))


@router.get("/workspaces/{workspace_id}/activity")
def workspace_activity(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    workspace = service.repository.get(workspace_id, user["id"])
    runs = AgentRunRepository(service.repository.database).list(workspace_id, user["id"], limit=1)
    live = operations.snapshot(workspace_id)
    if runs:
        latest = runs[0]
        if live and live.get("harness", {}).get("run_id") == latest["run_id"]:
            return {**live, "status": latest["status"], "harness": latest}
        return {**latest, "harness": latest}
    return live or workspace.last_run or {"status": "idle"}


@router.get("/workspaces/{workspace_id}/runs")
def workspace_runs(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    service.repository.get(workspace_id, user["id"])
    return {"items": AgentRunRepository(service.repository.database).list(workspace_id, user["id"])}


@router.patch("/workspaces/{workspace_id}")
def rename_workspace(
    workspace_id: str,
    request: RenameWorkspaceRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.rename(workspace_id, user["id"], request.revision, request.title)


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    service.delete(workspace_id, user["id"])
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/analyze")
async def analyze_record(
    workspace_id: str,
    request: RevisionRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return await service.analyze(workspace_id, user["id"], request.revision)


@router.post("/workspaces/{workspace_id}/template")
def select_template(
    workspace_id: str,
    request: SelectTemplateRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.select_template(workspace_id, user["id"], request.revision, request.template_id)


@router.post("/workspaces/{workspace_id}/extract")
async def extract_fields(
    workspace_id: str,
    request: ExtractFieldsRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return await service.extract_fields(
        workspace_id, user["id"], request.revision, request.replace_reviewed, request.retry_failed
    )


@router.patch("/workspaces/{workspace_id}/fields")
def review_fields(
    workspace_id: str,
    request: ReviewFieldsRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.review_fields(
        workspace_id, user["id"], request.revision, [decision.model_dump() for decision in request.decisions]
    )


@router.get("/workspaces/{workspace_id}/preview")
def preview_contract(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.preview(workspace_id, user["id"])


@router.post("/workspaces/{workspace_id}/generate")
def generate_contract(
    workspace_id: str,
    request: GenerateContractRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    return service.generate(
        workspace_id,
        user["id"],
        request.revision,
        request.preview_acknowledged,
        request.visual_review_acknowledged,
    )
