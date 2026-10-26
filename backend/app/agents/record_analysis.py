"""Identify the transaction and retrieval intent without choosing a template."""

from app.agents.prompts import RECORD_ANALYSIS_PROMPT
from app.domain.contract_workflow import NegotiationAnalysis
from app.model_client import ChatModel


class RecordAnalysisAgent:
    """识别交易类型、最终共识及明确模板请求的分析角色。"""

    def __init__(self, model: ChatModel):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            model: 当前模型适配器或模型标识，不能包含密钥。
        """
        self.model = model

    async def analyze(self, source_lines: list[dict]) -> NegotiationAnalysis:
        """提取交易类型、最终共识和检索意图；不选择模板或生成合同。

        Args:
            source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
        """
        return await self.model.generate_structured(
            RECORD_ANALYSIS_PROMPT,
            {"source_lines": source_lines},
            NegotiationAnalysis,
        )
