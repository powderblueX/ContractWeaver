"""Compose reusable catalog infrastructure and per-request workflow services."""

from functools import lru_cache

from fastapi import Depends

from app.api.dependencies import get_database
from app.config import get_settings
from app.database import Database
from app.repositories.contract_workspaces import ContractWorkspaceRepository
from app.services.contract_templates import ContractTemplateCatalog
from app.services.contract_workflow import ContractWorkflowService
from app.services.template_retrieval import RetrievalPolicy


@lru_cache
def get_template_catalog() -> ContractTemplateCatalog:
    """按配置组装并缓存模板目录及检索策略，不读取前端传入的文件路径。"""
    settings = get_settings()
    return ContractTemplateCatalog(
        settings.resources_dir,
        settings.generated_dir,
        settings.embedding_model_path,
        RetrievalPolicy(
            candidate_pool=settings.retrieval_candidate_pool,
            bm25_k1=settings.retrieval_bm25_k1,
            bm25_b=settings.retrieval_bm25_b,
            rrf_constant=settings.retrieval_rrf_constant,
        ),
    )


def get_workflow_service(database: Database = Depends(get_database)) -> ContractWorkflowService:
    """注入仓储、模板目录和配置，组装本次请求的合同业务服务。

    Args:
        database: 负责短连接和事务的数据库访问对象。
    """
    return ContractWorkflowService(
        ContractWorkspaceRepository(database), get_template_catalog(), get_settings()
    )
