"""Agent run use case and atomic transcript persistence."""

import uuid

from app.legal_agent import LegalAgent
from app.config import Settings
from app.model_client import ChatModel
from app.repositories.conversations import ConversationRepository
from app.services.contract_templates import ContractTemplateCatalog
from app.services.civil_code import CivilCode


class ConversationService:
    def __init__(self, repository: ConversationRepository, settings: Settings):
        self.repository = repository
        self.settings = settings

    async def run(self, user_id: int, message: str, session_id: str | None, allow_draft: bool) -> dict:
        new_session = session_id is None
        history = self.repository.history(session_id, user_id) if session_id else []
        session_id = session_id or uuid.uuid4().hex
        contracts = ContractTemplateCatalog(self.settings.resources_dir, self.settings.generated_dir, self.settings.embedding_model_path)
        agent = LegalAgent(ChatModel(self.settings), CivilCode(self.settings.law_data_path), contracts, self.settings.max_agent_steps)
        result = await agent.run(history, message, allow_draft)
        self.repository.save_run(session_id, user_id, message, result, new_session=new_session)
        return {"session_id": session_id, **result}
