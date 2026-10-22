"""HTTP input contracts for source import and explicit workflow transitions."""

from typing import Literal

from pydantic import Field

from app.domain.contract_workflow import StrictModel


class CreateWorkspaceRequest(StrictModel):
    title: str = Field(default="新的合同任务", max_length=100)
    source_name: str = Field(default="协商记录", max_length=255)
    source_text: str = Field(min_length=10, max_length=300000)


class RevisionRequest(StrictModel):
    revision: int = Field(ge=1)


class SelectTemplateRequest(RevisionRequest):
    template_id: str = Field(min_length=1, max_length=100)


class ExtractFieldsRequest(RevisionRequest):
    replace_reviewed: bool = False
    retry_failed: bool = False


class FieldDecision(StrictModel):
    name: str = Field(min_length=1, max_length=5000)
    value: str = Field(default="", max_length=5000)
    action: Literal["confirm", "omit"] = "confirm"
    note: str = Field(default="", max_length=2000)


class ReviewFieldsRequest(RevisionRequest):
    decisions: list[FieldDecision] = Field(min_length=1, max_length=5000)


class GenerateContractRequest(RevisionRequest):
    preview_acknowledged: bool = False
    visual_review_acknowledged: bool = False


class RenameWorkspaceRequest(RevisionRequest):
    title: str = Field(min_length=1, max_length=100)
