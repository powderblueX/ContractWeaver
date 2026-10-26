"""Validated agent results and durable, user-reviewed contract state."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """拒绝额外键的领域模型基类，用于控制 LLM 与接口输出边界。"""

    model_config = ConfigDict(extra="forbid")


class SourceEvidence(StrictModel):
    """标识一条可在指定原文行逐字验证的证据。"""

    line_number: int = Field(ge=1, description="source_lines 中实际存在的原文行号")
    quote: str = Field(min_length=1, max_length=3000, description="该行内连续、逐字存在的原文片段，不是转述")


class RequestedTemplate(StrictModel):
    """保存用户明确点名的模板原名及来源证据。"""

    name: str = Field(min_length=2, max_length=300)
    evidence: SourceEvidence


class NegotiationAnalysis(StrictModel):
    """分析角色的结构化交易摘要、检索意图和未定事项。"""

    decision_summary: str = Field(default="", max_length=1000)
    summary: str = Field(max_length=4000)
    contract_type: str = Field(max_length=200)
    search_query: str = Field(min_length=1, max_length=1000)
    key_terms: list[str] = Field(default_factory=list, max_length=20)
    unresolved_points: list[str] = Field(default_factory=list, max_length=30)
    requested_templates: list[RequestedTemplate] = Field(default_factory=list, max_length=10)


class ExtractedField(StrictModel):
    """模型提出的单个候选值及其证据，尚不代表人工确认。"""

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
    """一批候选字段及可选简短决策摘要。"""

    decision_summary: str = Field(default="", max_length=1000)
    fields: list[ExtractedField]


class ReviewFinding(StrictModel):
    """针对某个字段的复核问题及其严重程度。"""

    field_name: str
    issue: str = Field(max_length=2000)
    severity: str = Field(pattern="^(warning|conflict)$")


class ReviewResult(StrictModel):
    """独立复核产生的问题集合，不直接修改合同值。"""

    decision_summary: str = Field(default="", max_length=1000)
    findings: list[ReviewFinding] = Field(default_factory=list)


class CoverageGap(StrictModel):
    """跨字段覆盖检查提出的遗漏或文义冲突及其证据。"""

    summary: str = Field(max_length=1000)
    evidence: SourceEvidence
    suggestion: str = Field(max_length=1000)


class CoverageResult(StrictModel):
    """全合同候选上下文的覆盖检查结果。"""

    decision_summary: str = Field(default="", max_length=1000)
    gaps: list[CoverageGap] = Field(default_factory=list, max_length=30)


class SupervisorDecision(StrictModel):
    """模型下一动作的受限协议，动作参数还须通过协调器验证。"""

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
    """区分提取、缺失、冲突、待核验及人工确认/留空的状态枚举。"""

    EXTRACTED = "extracted"
    MISSING = "missing"
    CONFLICT = "conflict"
    UNVERIFIED = "unverified"
    CONFIRMED = "confirmed"
    OMITTED = "omitted"


class ReviewedField(StrictModel):
    """连接 Word 定位、模型提议、证据和用户审核决定的字段状态。"""

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
    """记录角色、动作、说明和统一时间的任务内事件。"""

    role: str
    action: str
    detail: str
    created_at: str


class ContractWorkspace(StrictModel):
    """合同任务的持久领域快照，修订号控制并发与预览有效性。"""

    id: str
    title: str
    source_name: str = "协商记录"
    source_text: str
    revision: int = 1
    # revision 保护数据库比较交换和预览有效性；stage 记录领域流程阶段。
    stage: str = "source_ready"
    analysis: NegotiationAnalysis | None = None
    last_run: dict = Field(default_factory=dict)
    # 运行摘要仅用于回显；完整有界运行历史和跨进程租约存于独立日志表。
    recommendations: list[dict] = Field(default_factory=list)
    selected_template: dict | None = None
    fields: list[ReviewedField] = Field(default_factory=list)
    extraction_failures: list[dict] = Field(default_factory=list)
    coverage_gaps: list[CoverageGap] = Field(default_factory=list)
    coverage_status: str = "not_run"
    agent_questions: list[str] = Field(default_factory=list)
    # 问题是本次主控执行的快照，用户补填后不会自动变成新的对话事实。
    coordination_warnings: list[str] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)
    events: list[AgentEvent] = Field(default_factory=list)
    created_at: str
    updated_at: str
