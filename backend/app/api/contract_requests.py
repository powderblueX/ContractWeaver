"""HTTP input contracts for source import and explicit workflow transitions."""

from typing import Literal

from pydantic import Field

from app.domain.contract_workflow import StrictModel


class CreateWorkspaceRequest(StrictModel):
    """校验新任务名称、来源说明和纪要正文。"""

    title: str = Field(default="新的合同任务", max_length=100)
    source_name: str = Field(default="协商记录", max_length=255)
    source_text: str = Field(min_length=10, max_length=300000)


class RevisionRequest(StrictModel):
    """携带客户端期望修订号，防止陈旧请求覆盖新状态。"""

    revision: int = Field(ge=1)


class SelectTemplateRequest(RevisionRequest):
    """要求用户明确提交模板标识及当前任务修订。"""

    template_id: str = Field(min_length=1, max_length=100)


class ExtractFieldsRequest(RevisionRequest):
    """区分首次提取、覆盖已审核值及仅重试失败批次的意图。"""

    replace_reviewed: bool = False
    retry_failed: bool = False


class FieldDecision(StrictModel):
    """记录用户确认或留空的值与原因，不接受模型自动审批。"""

    name: str = Field(min_length=1, max_length=5000)
    value: str = Field(default="", max_length=5000)
    action: Literal["confirm", "omit"] = "confirm"
    note: str = Field(default="", max_length=2000)


class ReviewFieldsRequest(RevisionRequest):
    """以单个修订批量提交用户字段审核决定。"""

    decisions: list[FieldDecision] = Field(min_length=1, max_length=5000)


class GenerateContractRequest(RevisionRequest):
    """要求当前修订及预览/视觉复核确认后才允许导出。"""

    preview_acknowledged: bool = False
    visual_review_acknowledged: bool = False


class RenameWorkspaceRequest(RevisionRequest):
    """校验任务重命名的名称与预期修订。"""

    title: str = Field(min_length=1, max_length=100)
