"""Model-directed analyze/search/observe loop with a mandatory user handoff."""

import asyncio

from app.agents.harness import run_step
from app.domain.errors import InvalidContractInput
from app.model_client import ModelUnavailable
from app.services.template_retrieval import normalize_title


class NegotiationCoordinator:
    """根据主控观察结果调度分析与检索，最终保留人工选模板关卡。"""

    def __init__(self, team, catalog, settings):
        """注入依赖并初始化本实例的状态，保持资源所有权与其他请求隔离。

        Args:
            team: 共享连接、角色上下文隔离的 Agent 团队。
            catalog: 受控的原始模板目录及检索/写入服务。
            settings: 已解析的运行配置，包含路径、模型及预算；不得公开密钥。
        """
        self.team = team
        self.catalog = catalog
        self.settings = settings

    async def run(self, source_lines, source_text):
        """按模型决策执行分析与多轮检索，防止重复查询并最终交用户选择。

        Args:
            source_lines: 带服务器行号的原始纪要，是逐字证据的核验来源。
            source_text: 尚未被模型改写的原始协商记录。
        """
        analysis, candidates, fused, searches, history = None, {}, {}, 0, []
        # fused 累计跨轮检索名次；用户明确点名的模板始终保留优先级。
        questions = []
        warnings = []
        for _ in range(self.settings.supervisor_max_searches + 2):
            allowed = ["analyze_record"] if analysis is None else ["retrieve_templates"]
            if searches:
                allowed = ["handoff", "request_user"] + (
                    ["retrieve_templates"] if searches < self.settings.supervisor_max_searches else []
                )
            observations = {
                "analysis": analysis.model_dump(mode="json") if analysis else None,
                "searches_used": searches,
                "searches_remaining": self.settings.supervisor_max_searches - searches,
                "search_history": history,
                "candidates": list(candidates.values())[:30],
            }
            try:
                decision = await run_step(
                    "plan_next_action",
                    lambda: self.team.supervisor.decide(
                        "template_retrieval", source_lines, observations, allowed
                    ),
                )
            except (ModelUnavailable, ValueError) as error:
                if analysis is None:
                    raise
                warnings.append(f"主控后续规划未完成，保留已完成分析与候选，可手动选模板：{str(error)[:200]}")
                break
            if decision.action not in allowed:
                raise InvalidContractInput("主控返回了当前不允许的检索动作")
            if decision.action == "analyze_record":
                analysis = await run_step("analyze_record", lambda: self.team.analysis.analyze(source_lines))
            elif decision.action == "retrieve_templates":
                source_by_line = {line["line_number"]: line["text"] for line in source_lines}
                requested = [
                    item.name
                    for item in analysis.requested_templates
                    if item.evidence.quote in source_by_line.get(item.evidence.line_number, "")
                    and normalize_title(item.name) in normalize_title(item.evidence.quote)
                ]
                query = decision.search_query.strip() or (
                    analysis.search_query + " " + " ".join(analysis.key_terms)
                )
                if query in history:
                    warnings.append("主控重复相同检索词，已停止循环并保留候选；可手动选择模板")
                    break
                try:
                    found = await run_step(
                        "retrieve_templates",
                        lambda: asyncio.to_thread(
                            self.catalog.search_templates,
                            query,
                            limit=self.settings.recommendation_limit,
                            explicit_names=requested,
                            source_text=source_text,
                        ),
                    )
                except Exception:
                    # 保留已完成的分析与前轮候选，交由用户手动浏览模板库。
                    warnings.append(
                        "自动模板检索暂时不可用，记录分析已保留。请在模板库中搜索并选择；持续失败请联系服务维护者。"
                    )
                    break
                searches += 1
                history.append(query)
                for rank, item in enumerate(found, 1):
                    candidates[item["id"]] = item
                    fused[item["id"]] = fused.get(item["id"], 0) + 1 / (
                        self.settings.retrieval_rrf_constant + rank
                    )
            else:
                questions = decision.questions
                break
        # Explicit source requests retain precedence across all model-selected searches.
        ranked = sorted(
            candidates.values(),
            key=lambda item: (not item.get("explicitly_requested", False), -fused[item["id"]], item["name"]),
        )
        return analysis, ranked[: self.settings.recommendation_limit], questions, searches, warnings
