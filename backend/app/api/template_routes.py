"""Manual template library and authenticated generated-document downloads."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from app.api.dependencies import current_user
from app.api.workspace_dependencies import get_template_catalog, get_workflow_service
from app.config import get_settings
from app.services.contract_templates import ContractTemplateCatalog
from app.services.contract_workflow import ContractWorkflowService

router = APIRouter(prefix="/contracts", tags=["templates and files"])


@router.get("/templates")
def browse_templates(
    group: str | None = None,
    query: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    user: dict = Depends(current_user),
    catalog: ContractTemplateCatalog = Depends(get_template_catalog),
):
    return catalog.browse_templates(group, query, offset, limit)


@router.get("/templates/{template_id}")
def get_template_details(
    template_id: str,
    user: dict = Depends(current_user),
    catalog: ContractTemplateCatalog = Depends(get_template_catalog),
):
    try:
        return catalog.describe_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/templates/{template_id}/download")
def download_template(
    template_id: str,
    user: dict = Depends(current_user),
    catalog: ContractTemplateCatalog = Depends(get_template_catalog),
):
    try:
        template = catalog.get_template(template_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        template.path,
        filename=f"{template.name}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{contract_id}/download")
def download_contract(
    contract_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    record = service.repository.find_artifact(contract_id, user["id"])
    if record is None:
        raise HTTPException(status_code=404, detail="合同文件不存在")
    generated_root = get_settings().generated_dir.resolve()
    path = (generated_root / record["filename"]).resolve()
    if not path.is_relative_to(generated_root) or not path.is_file():
        raise HTTPException(status_code=404, detail="合同文件不存在")
    return FileResponse(
        path,
        filename=f"合同_{contract_id[:8]}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
