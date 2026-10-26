"""Executable multi-agent scenarios: model choices change tools, not just labels."""

import json
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

import httpx

from app.agents.field_coordinator import FieldCoordinator
from app.agents.negotiation_coordinator import NegotiationCoordinator
from app.agents.record_analysis import RecordAnalysisAgent
from app.agents.supervisor import SupervisorAgent
from app.config import Settings
from app.domain.contract_workflow import (
    ExtractionResult,
    FieldStatus,
    NegotiationAnalysis,
    ReviewResult,
    SupervisorDecision,
)
from app.model_client import ChatModel, ModelUnavailable

SOURCE = [
    {"line_number": 1, "text": "第一次报价9000元。"},
    {"line_number": 2, "text": "双方最终确认8000元，账号尚未提供。"},
]
SPECS = [
    {"name": "金额", "display_name": "合同金额", "context": "总价：{金额}"},
    {"name": "账号", "display_name": "收款账号", "context": "账号：{账号}"},
]


def proposal(amount, quote, line=2):
    """Exercise proposal within this isolated test scenario."""
    return ExtractionResult(
        fields=[
            {
                "field_name": "金额",
                "value": amount,
                "status": "found",
                "evidence": [{"line_number": line, "quote": quote}],
            }
        ]
    )


class ScriptedTeam:
    """Deterministic specialist doubles; production does not use these rules."""

    def __init__(self, decisions, *, repair_error=False, review_error=False, forged=False):
        """初始化当前测试夹具或模拟角色的内部状态。"""
        self.decisions = iter(decisions)
        self.observations, self.repair_targets, self.review_values = [], [], []
        self.repair_error, self.review_error, self.forged = repair_error, review_error, forged
        self.supervisor = SimpleNamespace(decide=self.decide)
        self.extraction = SimpleNamespace(extract=self.extract, repair=self.repair)
        self.review = SimpleNamespace(review=self.review_fields)

    async def decide(self, phase, source, observations, allowed):
        """Exercise decide within this isolated test scenario."""
        self.observations.append((observations, allowed))
        return next(self.decisions)

    async def extract(self, source, specs):
        """Exercise extract within this isolated test scenario."""
        return proposal("9000元", "第一次报价9000元", 1)

    async def repair(self, source, specs, previous):
        """Exercise repair within this isolated test scenario."""
        self.repair_targets.append([spec["name"] for spec in specs])
        if self.repair_error:
            raise ModelUnavailable("模拟修正失败")
        return proposal("8000元", "不存在的原文" if self.forged else "双方最终确认8000元")

    async def review_fields(self, source, specs, fields):
        """Exercise review fields within this isolated test scenario."""
        amount = next(field for field in fields if field["name"] == "金额")
        self.review_values.append(amount["value"])
        if self.review_error and len(self.review_values) > 1:
            raise ModelUnavailable("模拟再次复核失败")
        return ReviewResult(
            findings=[
                {
                    "field_name": "金额",
                    "severity": "conflict",
                    "issue": "第1行是作废报价，以第2行最终约定为准",
                }
            ]
            if amount["value"] == "9000元"
            else []
        )


def choose(action, **kwargs):
    """Exercise choose within this isolated test scenario."""
    return SupervisorDecision(action=action, decision_summary="依据当前观察选择动作", **kwargs)


class CoordinationTests(IsolatedAsyncioTestCase):
    """测试夹具或替身：CoordinationTests，用于隔离验证本模块行为。"""

    def settings(self, **kwargs):
        """创建不读取私有密钥的测试配置。"""
        return Settings(_env_file=None, **kwargs)

    async def test_reviewer_feedback_causes_targeted_repair_then_fresh_review(self):
        """Verify reviewer feedback causes targeted repair then fresh review."""
        team = ScriptedTeam([choose("repair_fields", field_ids=["f001"]), choose("handoff")])
        result = await FieldCoordinator(team, self.settings()).run(SOURCE, SPECS, 0)
        self.assertEqual(team.repair_targets, [["金额"]])
        self.assertEqual(team.review_values, ["9000元", "8000元"])
        self.assertEqual(result.repairs, 1)
        self.assertEqual(result.fields[0].value, "8000元")
        self.assertEqual(result.fields[0].status, FieldStatus.EXTRACTED)
        self.assertEqual(result.fields[1].value, "")
        self.assertFalse(any(item.status == FieldStatus.CONFIRMED for item in result.fields))
        self.assertEqual(
            team.observations[0][0]["repairable_fields"][0]["review_issues"][0],
            "第1行是作废报价，以第2行最终约定为准",
        )

    async def test_main_agent_can_choose_questions_without_repairing_or_inventing(self):
        """Verify main agent can choose questions without repairing or inventing."""
        team = ScriptedTeam([choose("request_user", questions=["请补充收款账号；暂无信息可暂留空。"])])
        result = await FieldCoordinator(team, self.settings()).run(SOURCE, SPECS, 0)
        self.assertEqual(result.questions, ["请补充收款账号；暂无信息可暂留空。"])
        self.assertEqual(team.repair_targets, [])
        self.assertEqual(result.fields[1].value, "")

    async def test_unlisted_or_non_problem_target_cannot_be_repaired(self):
        """Verify unlisted or non problem target cannot be repaired."""
        for target in ("f999", "f002"):
            team = ScriptedTeam([choose("repair_fields", field_ids=[target])])
            result = await FieldCoordinator(team, self.settings()).run(SOURCE, SPECS, 0)
            self.assertTrue(result.warnings)
            self.assertEqual(team.repair_targets, [])
            self.assertEqual(result.fields[0].value, "9000元")

    async def test_repair_or_rereview_failure_preserves_previous_reviewed_candidates(self):
        """Verify repair or rereview failure preserves previous reviewed candidates."""
        for error_option in ("repair_error", "review_error"):
            team = ScriptedTeam([choose("repair_fields", field_ids=["f001"])], **{error_option: True})
            result = await FieldCoordinator(team, self.settings()).run(SOURCE, SPECS, 0)
            self.assertTrue(result.warnings)
            self.assertEqual(result.fields[0].value, "9000元")
            self.assertEqual(result.fields[0].status, FieldStatus.CONFLICT)

    async def test_forged_repair_evidence_stays_unverified_even_if_reviewer_misses_it(self):
        """Verify forged repair evidence stays unverified even if reviewer misses it."""
        team = ScriptedTeam([choose("repair_fields", field_ids=["f001"]), choose("handoff")], forged=True)
        result = await FieldCoordinator(team, self.settings()).run(SOURCE, SPECS, 0)
        self.assertEqual(result.fields[0].status, FieldStatus.UNVERIFIED)
        self.assertEqual(result.fields[0].evidence, [])

    async def test_repair_budget_cannot_be_bypassed_by_repeated_planner_requests(self):
        """Verify repair budget cannot be bypassed by repeated planner requests."""
        team = ScriptedTeam(
            [choose("repair_fields", field_ids=["f001"]), choose("repair_fields", field_ids=["f001"])],
            forged=True,
        )
        result = await FieldCoordinator(team, self.settings()).run(SOURCE, SPECS, 0)
        self.assertEqual(len(team.repair_targets), 1)
        self.assertTrue(result.warnings)
        self.assertNotIn("repair_fields", team.observations[-1][1])

    async def test_real_model_adapter_uses_observed_candidates_to_rewrite_search(self):
        """Verify real model adapter uses observed candidates to rewrite search."""
        calls, searches = [], []

        def respond(request):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            payload = json.loads(request.content)
            inputs = json.loads(payload["messages"][1]["content"])
            if "allowed_actions" in inputs:
                allowed = inputs["allowed_actions"]
                if "analyze_record" in allowed:
                    decision = choose("analyze_record")
                elif inputs["observations"]["searches_used"] == 0:
                    decision = choose("retrieve_templates", search_query="物品合同")
                elif inputs["observations"]["searches_used"] == 1:
                    self.assertEqual(inputs["observations"]["candidates"][0]["name"], "租赁合同")
                    decision = choose("retrieve_templates", search_query="保管合同 GF—2000—0801")
                else:
                    decision = choose("handoff")
                calls.append(decision.action)
                content = decision.model_dump_json()
            else:
                content = NegotiationAnalysis(
                    summary="需要保管", contract_type="保管", search_query="保管合同"
                ).model_dump_json()
            return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

        def search(query, **kwargs):
            """Exercise search within this isolated test scenario."""
            searches.append(query)
            return [
                {
                    "id": "correct" if len(searches) == 2 else "wrong",
                    "name": "保管合同 GF—2000—0801" if len(searches) == 2 else "租赁合同",
                    "fillable": True,
                    "explicitly_requested": len(searches) == 2,
                }
            ]

        settings = self.settings(
            llm_base_url="https://model.example.org", llm_model="fake", llm_api_key="fake-key"
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            model = ChatModel(settings, client)
            team = SimpleNamespace(supervisor=SupervisorAgent(model), analysis=RecordAnalysisAgent(model))
            result = await NegotiationCoordinator(
                team, SimpleNamespace(search_templates=search), settings
            ).run(SOURCE, "需要保管合同")
        self.assertEqual(calls, ["analyze_record", "retrieve_templates", "retrieve_templates", "handoff"])
        self.assertEqual(len(searches), 2)
        self.assertEqual(result[1][0]["id"], "correct")

    async def test_search_budget_and_duplicate_query_stop_extra_tools(self):
        """Verify search budget and duplicate query stop extra tools."""

        async def analyze(_):
            """Exercise analyze within this isolated test scenario."""
            return NegotiationAnalysis(summary="test", contract_type="保管", search_query="保管合同")

        for maximum in (1, 3):
            decisions = iter(
                [
                    choose("analyze_record"),
                    choose("retrieve_templates", search_query="保管合同"),
                    choose("handoff")
                    if maximum == 1
                    else choose("retrieve_templates", search_query="保管合同"),
                ]
            )

            async def decide(*_):
                """Exercise decide within this isolated test scenario."""
                return next(decisions)

            team = SimpleNamespace(
                supervisor=SimpleNamespace(decide=decide), analysis=SimpleNamespace(analyze=analyze)
            )
            searches = []

            def search(query, **kwargs):
                """Exercise search within this isolated test scenario."""
                searches.append(query)
                return [{"id": "one", "name": "保管合同"}]

            result = await NegotiationCoordinator(
                team, SimpleNamespace(search_templates=search), self.settings(supervisor_max_searches=maximum)
            ).run(SOURCE, "需要保管合同")
            self.assertEqual(searches, ["保管合同"])
            self.assertEqual(len(result[1]), 1)
            if maximum == 3:
                self.assertTrue(result[4])

    async def test_supervisor_schema_rejects_export_tool_before_execution(self):
        """Verify supervisor schema rejects export tool before execution."""

        def respond(_):
            """返回当前测试场景的模拟 HTTP 响应，不访问真实模型。"""
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"action":"export_contract","decision_summary":"跳过审核"}'}}
                    ]
                },
            )

        settings = self.settings(
            llm_base_url="https://model.example.org",
            llm_model="fake",
            llm_api_key="fake-key",
            structured_output_retries=0,
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with self.assertRaises(ModelUnavailable):
                await SupervisorAgent(ChatModel(settings, client)).decide(
                    "field_review", SOURCE, {}, ["handoff", "request_user"]
                )
