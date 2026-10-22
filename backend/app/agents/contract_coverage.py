"""Check the whole proposed contract for agreed facts lost between field batches."""

import json
import re

from app.agents.prompts import CONTRACT_COVERAGE_PROMPT
from app.domain.contract_workflow import CoverageResult
from app.model_client import ModelUnavailable


class ContractCoverageAgent:
    def __init__(self, model, max_context_chars=120000):
        self.model = model
        self.max_context_chars = max_context_chars

    async def review(self, source_lines, template_fields, extracted_fields):
        values = {field.name: field.value for field in extracted_fields}
        payload = {
            "source_lines": source_lines,
            "contract_fields": [
                {
                    "label": field.get("display_name", field["name"]),
                    "context": re.sub(r"\{[^{}]+\}", "[填写处]", field["context"]),
                    "value": values.get(field["name"], ""),
                }
                for field in template_fields
            ],
        }
        if len(json.dumps(payload, ensure_ascii=False)) > self.max_context_chars:
            raise ModelUnavailable(
                "全合同覆盖检查超过配置的上下文上限，未发送请求；请人工核对，或调整 LAW_COVERAGE_MAX_CONTEXT_CHARS 后重新提取"
            )
        return await self.model.generate_structured(
            CONTRACT_COVERAGE_PROMPT,
            payload,
            CoverageResult,
        )
