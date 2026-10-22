"""Validated agent results and durable, user-reviewed contract state."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceEvidence(StrictModel):
    line_number: int = Field(ge=1, description="source_lines 中实际存在的原文行号")
    quote: str = Field(min_length=1, max_length=3000, description="该行内连续、逐字存在的原文片段，不是转述")


class RequestedTemplate(StrictModel):
    name: str = Field(min_length=2, max_length=300)
    evidence: SourceEvidence


class NegotiationAnalysis(StrictModel):
    decision_summary: str = Field(default="", max_length=1000)
    summary: str = Field(max_length=4000)
    contract_type: str = Field(max_length=200)
    search_query: str = Field(min_length=1, max_length=1000)
    key_terms: list[str] = Field(default_factory=list, max_length=20)
    unresolved_points: list[str] = Field(default_factory=list, max_length=30)
    requested_templates: list[RequestedTemplate] = Field(default_factory=list, max_length=10)


class ExtractedField(StrictModel):
    field_name: str = Field(description="本批 template_fields 的 name 短编号，不是 label")
    value: str = Field(
        default="",
        max_length=5000,
        description="仅填当前槽位需要的值，不重复模板已有标签/单位；缺失或方案未决时留空",
    )
    status: str = Field(
        pattern="^(found|missing|conflict)$",
        description="found=有明确依据；missing=未取得内容；conflict=存在未解决的矛盾或歧义",
    )
    evidence: list[SourceEvidence] = Field(default_factory=list, max_length=10)
    alternatives: list[str] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=2000)


class ExtractionResult(StrictModel):
    decision_summary: str = Field(default="", max_length=1000)
    fields: list[ExtractedField]


class ReviewFinding(StrictModel):
    field_name: str
    issue: str = Field(max_length=2000)
    severity: str = Field(pattern="^(warning|conflict)$")


class ReviewResult(StrictModel):
    decision_summary: str = Field(default="", max_length=1000)
    findings: list[ReviewFinding] = Field(default_factory=list)


class CoverageGap(StrictModel):
    summary: str = Field(max_length=1000)
    evidence: SourceEvidence
    suggestion: str = Field(max_length=1000)


class CoverageResult(StrictModel):
    decision_summary: str = Field(default="", max_length=1000)
    gaps: list[CoverageGap] = Field(default_factory=list, max_length=30)


class SupervisorDecision(StrictModel):
    action: Literal["analyze_record", "retrieve_templates", "repair_fields", "request_user", "handoff"]
    decision_summary: str = Field(min_length=1, max_length=1000)
    search_query: str = Field(default="", max_length=1000)
    field_ids: list[Annotated[str, Field(min_length=1, max_length=20)]] = Field(
        default_factory=list, max_length=80
    )
    questions: list[Annotated[str, Field(min_length=1, max_length=500)]] = Field(
        default_factory=list, max_length=10
    )


class FieldStatus(StrEnum):
    EXTRACTED = "extracted"
    MISSING = "missing"
    CONFLICT = "conflict"
    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    OMITTED = "omitted"


class ReviewedField(StrictModel):
    name: str
    display_name: str = ""
    section: str = ""
    kind: str = "text"
    value_type: str = "text"
    component: str = ""
    date_group: str = ""
    fixed_unit: str = ""
    choices: list[str] = Field(default_factory=list)
    value: str = ""
    extracted_value: str = ""
    status: FieldStatus = FieldStatus.MISSING
    evidence: list[SourceEvidence] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    note: str = ""
    review_issues: list[str] = Field(default_factory=list)
    context: str = ""
    user_note: str = ""
    value_origin: str = "record"


class AgentEvent(StrictModel):
    role: str
    action: str
    detail: str
    created_at: str


class ContractWorkspace(StrictModel):
    id: str
    title: str
    source_name: str = "协商记录"
    source_text: str
    revision: int = 1
    stage: str = "source_ready"
    analysis: NegotiationAnalysis | None = None
    last_run: dict = Field(default_factory=dict)
    recommendations: list[dict] = Field(default_factory=list)
    selected_template: dict | None = None
    fields: list[ReviewedField] = Field(default_factory=list)
    extraction_failures: list[dict] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)
    coverage_status: str = "not_run"
    agent_questions: list[str] = Field(default_factory=list)
    coordination_warnings: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    created_at: str
    updated_at: str
