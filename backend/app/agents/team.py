"""One API configuration for the supervisor and four contract specialists."""

from app.agents.contract_coverage import ContractCoverageAgent
from app.agents.field_extraction import FieldExtractionAgent
from app.agents.field_review import FieldReviewAgent
from app.agents.record_analysis import RecordAnalysisAgent
from app.agents.supervisor import SupervisorAgent
from app.config import Settings
from app.model_client import ChatModel


class ContractAgentTeam:
    """共享一套模型配置和连接的五角色集合，各角色保持独立消息上下文。"""

    def __init__(self, settings: Settings):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            settings: 已解析的运行配置，包含路径、模型及预算；不得公开密钥。
        """
        self.model = ChatModel(settings)
        self.analysis = RecordAnalysisAgent(self.model)
        self.supervisor = SupervisorAgent(self.model)
        self.extraction = FieldExtractionAgent(self.model)
        self.review = FieldReviewAgent(self.model)
        self.coverage = ContractCoverageAgent(self.model, settings.coverage_max_context_chars)

    async def __aenter__(self):
        """进入异步上下文并准备本实例共享的模型连接。"""
        await self.model.__aenter__()
        return self

    async def __aexit__(self, *args):
        """退出异步上下文，按资源所有权关闭共享连接。"""
        await self.model.__aexit__(*args)


def create_agent_team(settings: Settings) -> ContractAgentTeam:
    """创建共享同一模型连接、但指令与消息上下文隔离的角色团队。

    Args:
        settings: 已解析的运行配置，包含路径、模型及预算；不得公开密钥。
    """
    return ContractAgentTeam(settings)
