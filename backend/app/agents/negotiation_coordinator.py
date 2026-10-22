"""Model-directed analyze/search/observe loop with a mandatory user handoff."""

import asyncio

from app.agents.harness import run_step
from app.domain.errors import InvalidContractInput
from app.model_client import ModelUnavailable
from app.services.template_retrieval import normalize_title


class NegotiationCoordinator:
    def __init__(self, team, catalog, settings):
        self.team = team
        self.catalog = catalog
        self.settings = settings

    async def run(self, source_lines, source_text):
        analysis, candidates, fused, searches, history = None, {}, {}, 0, []
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
