"""One API configuration for the supervisor and four contract specialists."""

from app.agents.contract_coverage import ContractCoverageAgent
from app.agents.field_extraction import FieldExtractionAgent
from app.agents.field_review import FieldReviewAgent
from app.agents.record_analysis import RecordAnalysisAgent
from app.agents.supervisor import SupervisorAgent
from app.config import Settings
from app.model_client import ChatModel


class ContractAgentTeam:
    def __init__(self, settings: Settings):
        self.model = ChatModel(settings)
        self.analysis = RecordAnalysisAgent(self.model)
        self.supervisor = SupervisorAgent(self.model)
        self.extraction = FieldExtractionAgent(self.model)
        self.review = FieldReviewAgent(self.model)
        self.coverage = ContractCoverageAgent(self.model, settings.coverage_max_context_chars)

    async def __aenter__(self):
        await self.model.__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.model.__aexit__(*args)


def create_agent_team(settings: Settings) -> ContractAgentTeam:
    return ContractAgentTeam(settings)
