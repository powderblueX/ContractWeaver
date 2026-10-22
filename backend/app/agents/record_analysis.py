"""Identify the transaction and retrieval intent without choosing a template."""

from app.agents.prompts import RECORD_ANALYSIS_PROMPT
from app.domain.contract_workflow import NegotiationAnalysis
from app.model_client import ChatModel


class RecordAnalysisAgent:
    def __init__(self, model: ChatModel):
        self.model = model

    async def analyze(self, source_lines: list[dict]) -> NegotiationAnalysis:
        return await self.model.generate_structured(
            RECORD_ANALYSIS_PROMPT,
            {"source_lines": source_lines},
            NegotiationAnalysis,
        )
