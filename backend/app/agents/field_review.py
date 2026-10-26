"""Independently challenge extracted values against their original evidence."""

from app.agents.field_mapping import batch_schema, model_fields, restore_names
from app.agents.prompts import FIELD_REVIEW_PROMPT
from app.domain.contract_workflow import ReviewFinding, ReviewResult
from app.model_client import ChatModel


class FieldReviewAgent:
    """以独立消息上下文质疑候选依据及槽位映射的复核角色。"""

    def __init__(self, model: ChatModel):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            model: 当前模型适配器或模型标识，不能包含密钥。
        """
        self.model = model

    async def review(
        self, source_lines: list[dict], template_fields: list[dict], extracted_fields: list[dict]
    ) -> ReviewResult:
        """以独立上下文核对提取结果，返回问题而不替用户修改或确认。

        Args:
            source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
            template_fields: 当前批次可填写位置及附近文字、类型约束。
            extracted_fields: 已提出但尚未代表人工确认的字段候选。
        """
        mapping, fields = model_fields(template_fields)
        reverse = {value: key for key, value in mapping.items()}
        extracted = [{**field, "name": reverse[field["name"]]} for field in extracted_fields]
        result = await self.model.generate_structured(
            FIELD_REVIEW_PROMPT,
            {
                "source_lines": source_lines,
                "template_fields": fields,
                "extracted_fields": extracted,
            },
            batch_schema(ReviewResult, ReviewFinding, "findings", mapping),
        )
        restore_names(result.findings, mapping, allow_duplicates=True)
        return result
