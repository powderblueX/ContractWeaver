"""Independently challenge extracted values against their original evidence."""

from app.agents.field_mapping import batch_schema, model_fields, restore_names
from app.agents.prompts import FIELD_REVIEW_PROMPT
from app.domain.contract_workflow import ReviewFinding, ReviewResult
from app.model_client import ChatModel


class FieldReviewAgent:
    def __init__(self, model: ChatModel):
        self.model = model

    async def review(
        self, source_lines: list[dict], template_fields: list[dict], extracted_fields: list[dict]
    ) -> ReviewResult:
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
