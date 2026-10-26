"""Check the whole proposed contract for agreed facts lost between field batches."""

import json
import re

from app.agents.prompts import CONTRACT_COVERAGE_PROMPT
from app.domain.contract_workflow import CoverageResult
from app.model_client import ModelUnavailable


class ContractCoverageAgent:
    """检查跨字段遗漏与可见模板文义冲突的专业角色，不负责法律完整性认证。"""

    def __init__(self, model, max_context_chars=120000):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            model: 当前模型适配器或模型标识，不能包含密钥。
            max_context_chars: 覆盖检查输入 JSON 的字符预算。
        """
        self.model = model
        self.max_context_chars = max_context_chars

    async def review(self, source_lines, template_fields, extracted_fields):
        """对照完整纪要和所有候选上下文检查遗漏；超出上下文预算时不发送请求。

        Args:
            source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
            template_fields: 当前批次可填写位置及附近文字、类型约束。
            extracted_fields: 已提出但尚未代表人工确认的字段候选。
        """
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
