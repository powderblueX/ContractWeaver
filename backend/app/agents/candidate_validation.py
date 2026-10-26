"""Deterministic proposal/evidence guards shared by extraction and repair."""

from app.documents.slot_constraints import value_issue
from app.domain.contract_workflow import FieldStatus, ReviewedField
from app.model_client import ModelUnavailable


def validate_candidates(extraction, template_fields, source_lines, *, require_complete=False):
    """将模型提议映射回允许字段，并核验逐字证据、状态和槽位类型；不替用户确认。

    Args:
        extraction: 通过结构模型解析的提取或修正结果。
        template_fields: 当前批次可填写位置及附近文字、类型约束。
        source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
        require_complete: 是否要求修正结果完整返回全部指定目标。
    """
    expected = {field["name"] for field in template_fields}
    candidates = {}
    for candidate in extraction.fields:
        if candidate.field_name not in expected or candidate.field_name in candidates:
            raise ModelUnavailable("模型返回未知或重复字段")
        candidates[candidate.field_name] = candidate
    if require_complete and set(candidates) != expected:
        raise ModelUnavailable("定向修正未完整返回目标字段，原候选已保留")
    source_by_line = {line["line_number"]: line["text"] for line in source_lines}
    fields = []
    for spec in template_fields:
        field = ReviewedField(**spec)
        candidate = candidates.get(field.name)
        if candidate:
            field.value = candidate.value.strip()
            field.extracted_value = field.value
            field.evidence = [
                item for item in candidate.evidence if item.quote in source_by_line.get(item.line_number, "")
            ]
            field.alternatives = candidate.alternatives
            field.note = candidate.note
            if candidate.status == "conflict":
                field.status = FieldStatus.CONFLICT
            elif field.value and candidate.status == "found":
                field.status = FieldStatus.EXTRACTED if field.evidence else FieldStatus.UNVERIFIED
            if len(field.evidence) != len(candidate.evidence):
                field.review_issues.append("部分模型引用无法在对应原文行中核验，已移除")
            if field.value and not field.evidence:
                field.review_issues.append("未找到可核验的原文依据，请人工补充或确认")
            issue = value_issue(spec, field.value)
            if issue:
                field.review_issues.append(issue)
                field.status = FieldStatus.UNVERIFIED
            if candidate.status == "missing" and field.value:
                field.review_issues.append("模型声明缺失但返回了填写值，请核验")
                field.status = FieldStatus.UNVERIFIED
        fields.append(field)
    return fields


def apply_review(fields, review):
    """将独立复核意见附到候选字段，保留问题状态供主控和用户处理。

    Args:
        fields: 本次操作关联的字段集合。
        review: 独立复核输出的问题集合。
    """
    by_name = {field.name: field for field in fields}
    for finding in review.findings:
        if finding.field_name not in by_name:
            raise ModelUnavailable("复核模型返回未知字段")
        field = by_name[finding.field_name]
        field.review_issues.append(finding.issue)
        if field.value or finding.severity == "conflict":
            field.status = FieldStatus.CONFLICT if finding.severity == "conflict" else FieldStatus.UNVERIFIED


def repairable(field):
    """判断未审核候选是否存在可供主控定向修正的问题。

    Args:
        field: 待判断或展示的字段状态。
    """
    return field.status not in (FieldStatus.CONFIRMED, FieldStatus.OMITTED) and (
        bool(field.review_issues) or field.status in (FieldStatus.CONFLICT, FieldStatus.UNVERIFIED)
    )
