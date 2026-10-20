"""Bounded legal agent with explicit tool schemas and an auditable trace."""

import json

from app.model_client import ChatModel
from app.services.civil_code import CivilCode
from app.services.contract_templates import ContractTemplateCatalog


SYSTEM_PROMPT = """你是法理智推 Agent，协助用户分析中国民事法律问题和起草合同。
你可以自主选择工具、观察结果并决定下一步；不能编造未查询的法条或模板。
涉及法条时先使用 search_civil_code 或 lookup_civil_code，并在结论中标明条号。
推荐合同时先搜索模板，需要填充时先 inspect_contract_template；只有用户明确要求生成文件时才能调用 draft_contract。
缺少合同字段时保持空白，并明确提示用户核对，不得虚构姓名、金额、日期或判决结果。
回答中区分已知事实、推断、待核实事项；不保证法院裁判结果。"""


TOOLS = [
    {"type": "function", "function": {"name": "search_civil_code", "description": "按关键词搜索本地民法典条文", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "lookup_civil_code", "description": "读取指定民法典条文", "parameters": {"type": "object", "properties": {"article": {"type": "integer"}}, "required": ["article"]}}},
    {"type": "function", "function": {"name": "search_contract_templates", "description": "按需求检索合同模板", "parameters": {"type": "object", "properties": {"query": {"type": "string"}, "group": {"type": "string", "enum": ["部委", "地方"]}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "inspect_contract_template", "description": "查看合同模板可填写字段", "parameters": {"type": "object", "properties": {"template_id": {"type": "string"}}, "required": ["template_id"]}}},
    {"type": "function", "function": {"name": "draft_contract", "description": "使用用户明确提供的字段生成可下载合同", "parameters": {"type": "object", "properties": {"template_id": {"type": "string"}, "values": {"type": "object", "additionalProperties": {"type": "string"}}}, "required": ["template_id", "values"]}}},
]


class LegalAgent:
    def __init__(self, model: ChatModel, law: CivilCode, contracts: ContractTemplateCatalog, max_steps: int):
        self.model = model
        self.law = law
        self.contracts = contracts
        self.max_steps = max_steps

    async def run(self, history: list[dict], user_message: str, allow_draft: bool) -> dict:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history[-16:])
        messages.append({"role": "user", "content": user_message})
        trace = []
        artifacts = []
        inspected_templates = set()
        user_facts = "\n".join(item["content"] for item in history if item["role"] == "user") + "\n" + user_message
        for _ in range(self.max_steps):
            answer = await self.model.complete(messages, TOOLS)
            calls = answer.get("tool_calls") or []
            if not calls:
                return self._build_run_result(answer.get("content") or "暂无可用结论，请补充事实。", trace, artifacts)
            messages.append({"role": "assistant", "content": answer.get("content"), "tool_calls": calls})
            for call in calls[:4]:
                name = call.get("function", {}).get("name", "")
                try:
                    arguments = json.loads(call.get("function", {}).get("arguments") or "{}")
                    if name == "draft_contract" and artifacts:
                        raise ValueError("本轮已生成一份合同，请核对后再继续")
                    if name == "draft_contract" and arguments.get("template_id") not in inspected_templates:
                        raise ValueError("生成前须先查看所选模板的字段")
                    result = self._invoke_tool(name, arguments, allow_draft, user_message, user_facts)
                    if name == "inspect_contract_template":
                        inspected_templates.add(arguments["template_id"])
                    if name == "draft_contract" and "id" in result:
                        artifacts.append(result)
                    trace.append({"tool": name, "arguments": arguments, "result": result})
                except (ValueError, TypeError, KeyError, RuntimeError) as exc:
                    result = {"error": str(exc)}
                    trace.append({"tool": name, "arguments": {}, "result": result})
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": json.dumps(result, ensure_ascii=False)})
        # Keep the trace even if the provider repeatedly requests tools.
        messages.append({"role": "system", "content": "工具调用次数已达上限。现在依据已获得的结果简洁回答，不再调用工具。"})
        final = await self.model.complete(messages, [])
        return self._build_run_result(final.get("content") or "工具调用已达上限，请缩小问题范围。", trace, artifacts)

    @staticmethod
    def _build_run_result(answer: str, trace: list[dict], artifacts: list[dict]) -> dict:
        evidence = {}
        for step in trace:
            if step["tool"] not in ("search_civil_code", "lookup_civil_code"):
                continue
            result = step["result"]
            articles = result if isinstance(result, list) else [result]
            for article in articles:
                if isinstance(article, dict) and "article" in article and "text" in article:
                    evidence[article["article"]] = article
        return {"answer": answer, "trace": trace, "artifacts": artifacts, "evidence": list(evidence.values())}

    def _invoke_tool(self, name: str, args: dict, allow_draft: bool, user_message: str, user_facts: str) -> dict | list:
        if not isinstance(args, dict):
            raise ValueError("工具参数必须是对象")
        if name == "search_civil_code":
            return self.law.search(str(args["query"]), int(args.get("limit", 5)))
        if name == "lookup_civil_code":
            return self.law.lookup(int(args["article"]))
        if name == "search_contract_templates":
            return self.contracts.search_templates(str(args["query"]), args.get("group"))
        if name == "inspect_contract_template":
            return self.contracts.describe_template(str(args["template_id"]))
        if name == "draft_contract":
            if not allow_draft or not any(word in user_message for word in ("生成合同", "起草合同", "填写合同", "制作合同", "创建合同", "生成协议", "起草协议", "写一份合同", "写一份协议")):
                raise ValueError("用户未明确要求生成合同文件")
            values = args["values"]
            if not isinstance(values, dict):
                raise ValueError("合同字段必须是对象")
            grounded_values = {key: value for key, value in values.items() if isinstance(value, str) and value.strip() and value.strip() in user_facts}
            if not grounded_values:
                raise ValueError("未发现用户明确提供的可填写字段，请先收集具体事实")
            return self.contracts.generate_contract(str(args["template_id"]), grounded_values)
        raise ValueError("不允许调用该工具")
