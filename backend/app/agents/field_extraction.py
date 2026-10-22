"""Map negotiation evidence to the exact fields of the user's chosen template."""

from app.agents.field_mapping import batch_schema, model_fields, restore_names
from app.agents.prompts import FIELD_EXTRACTION_PROMPT, REPAIR_INSTRUCTION
from app.domain.contract_workflow import ExtractedField, ExtractionResult
from app.model_client import ChatModel


class FieldExtractionAgent:
    def __init__(self, model: ChatModel):
        self.model = model

    async def extract(self, source_lines: list[dict], template_fields: list[dict]) -> ExtractionResult:
        mapping, fields = model_fields(template_fields)
        result = await self.model.generate_structured(
            FIELD_EXTRACTION_PROMPT,
            {"source_lines": source_lines, "template_fields": fields},
            batch_schema(ExtractionResult, ExtractedField, "fields", mapping),
        )
        restore_names(result.fields, mapping)
        return result

    async def repair(self, source_lines, template_fields, previous_fields):
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
