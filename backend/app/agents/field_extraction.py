"""Map negotiation evidence to the exact fields of the user's chosen template."""

from app.agents.field_mapping import batch_schema, model_fields, restore_names
from app.agents.prompts import FIELD_EXTRACTION_PROMPT, REPAIR_INSTRUCTION
from app.domain.contract_workflow import ExtractedField, ExtractionResult
from app.model_client import ChatModel


class FieldExtractionAgent:
    """从纪要提出字段值或定向修正提议的专业角色。"""

    def __init__(self, model: ChatModel):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            model: 当前模型适配器或模型标识，不能包含密钥。
        """
        self.model = model

    async def extract(self, source_lines: list[dict], template_fields: list[dict]) -> ExtractionResult:
        """按当前批次的短编号提取候选值和逐字证据，再恢复 Word 定位名。

        Args:
            source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
            template_fields: 当前批次可填写位置及附近文字、类型约束。
        """
        mapping, fields = model_fields(template_fields)
        result = await self.model.generate_structured(
            FIELD_EXTRACTION_PROMPT,
            {"source_lines": source_lines, "template_fields": fields},
            batch_schema(ExtractionResult, ExtractedField, "fields", mapping),
        )
        restore_names(result.fields, mapping)
        return result

    async def repair(self, source_lines, template_fields, previous_fields):
        """携带旧候选与复核反馈，仅重新提取指定问题字段，结果仍需再次复核。

        Args:
            source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
            template_fields: 当前批次可填写位置及附近文字、类型约束。
            previous_fields: 用于定位修正问题的旧候选，不作为事实来源。
        """
        mapping, fields = model_fields(template_fields)
        reverse = {value: key for key, value in mapping.items()}
        feedback = [
            {
                "field_name": reverse[field.name],
                "previous_value": field.value,
                "issues": field.review_issues,
                "status": field.status.value,
            }
            for field in previous_fields
        ]
        result = await self.model.generate_structured(
            FIELD_EXTRACTION_PROMPT + REPAIR_INSTRUCTION,
            {"source_lines": source_lines, "template_fields": fields, "repair_context": feedback},
            batch_schema(ExtractionResult, ExtractedField, "fields", mapping),
        )
        restore_names(result.fields, mapping)
        return result
