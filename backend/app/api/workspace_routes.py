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
    """限制上传大小并解析协商文件；无论成功失败均关闭上传句柄。

    Args:
        file: 需要限制大小并在结束后关闭的上传文件。
        user: 认证后的账户公开身份。
    """
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
    """读取指定用户的任务摘要，按最近修改时间排序。

    Args:
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.repository.list_workspaces(user["id"])


@router.post("/workspaces", status_code=201)
def create_workspace(
    request: CreateWorkspaceRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """以当前账户身份保存新的协商记录和初始任务状态。

    Args:
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.create(user["id"], request.title, request.source_name, request.source_text)


@router.get("/workspaces/{workspace_id}")
def get_workspace(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """校验任务归属后返回状态，并补充与当前引擎一致的可读字段信息。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.present_workspace(service.repository.get(workspace_id, user["id"]))


@router.get("/workspaces/{workspace_id}/activity")
def workspace_activity(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """优先提供当前运行的进度，进程重启后可回退到持久日志。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
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
    """校验任务归属后读取有界运行历史，包含成功、部分失败和中断。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    service.repository.get(workspace_id, user["id"])
    return {"items": AgentRunRepository(service.repository.database).list(workspace_id, user["id"])}


@router.patch("/workspaces/{workspace_id}")
def rename_workspace(
    workspace_id: str,
    request: RenameWorkspaceRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """使用修订号更新任务名称，拒绝旧页面覆盖新版本。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.rename(workspace_id, user["id"], request.revision, request.title)


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """删除当前账户拥有的任务及关联生成文件，不删除原始模板。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    service.delete(workspace_id, user["id"])
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/analyze")
async def analyze_record(
    workspace_id: str,
    request: RevisionRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """执行受主控和 Harness 约束的记录分析及模板推荐。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return await service.analyze(workspace_id, user["id"], request.revision)


@router.post("/workspaces/{workspace_id}/template")
def select_template(
    workspace_id: str,
    request: SelectTemplateRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """由用户明确选定原件，并重新建立字段映射与人工审核起点。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.select_template(workspace_id, user["id"], request.revision, request.template_id)


@router.post("/workspaces/{workspace_id}/extract")
async def extract_fields(
    workspace_id: str,
    request: ExtractFieldsRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """分批提取、复核并按需定向修正；失败批次和已有人工审核有独立保护。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
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
    """保存用户的确认、修改或明确留空决定，并验证填写类型约束。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.review_fields(
        workspace_id, user["id"], request.revision, [decision.model_dump() for decision in request.decisions]
    )


@router.get("/workspaces/{workspace_id}/preview")
def preview_contract(
    workspace_id: str,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """基于审核值替换临时位置标识，并按段落和表格生成文字预览。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.preview(workspace_id, user["id"])


@router.post("/workspaces/{workspace_id}/generate")
def generate_contract(
    workspace_id: str,
    request: GenerateContractRequest,
    user: dict = Depends(current_user),
    service: ContractWorkflowService = Depends(get_workflow_service),
):
    """仅在人工审核及当前版本预览获批后生成新的 Word 合同。

    Args:
        workspace_id: 需要校验归属的合同任务标识。
        request: 已经通过请求模型解析的接口输入。
        user: 认证后的账户公开身份。
        service: 依赖注入的业务服务。
    """
    return service.generate(
        workspace_id,
        user["id"],
        request.revision,
        request.preview_acknowledged,
        request.visual_review_acknowledged,
    )
