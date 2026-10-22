# 契织：项目能力与可执行证据

本文件对应已经提交的项目描述，不改写简历、不补造过去的实现时间或模型效果。当前项目由 LawReasoner 演进，目标是基于协商记录/会议纪要的、人工监督的合同填写。

## 能力对应

| 项目描述 | 当前代码依据 | 边界 |
| --- | --- | --- |
| 多 Agent 协同 | `agents/supervisor.py`、`negotiation_coordinator.py`、`field_coordinator.py`、`team.py` | 一个主控、四个专业角色，共用同一配置模型，不是五个不同基础模型 |
| 模板推荐 | 分析角色提取意图；主控可根据候选改写检索词；`services/contract_templates.py` 检索/跨轮融合 | 用户仍可手动选库中其他原件，主控不能替用户选定 |
| 混合检索 | 名称 BM25、业务关键词 BM25、完整名称匹配的多路 RRF；可选本地 FAISS 向量通道 | 默认不代表已开启 dense embedding；没有配置时为多路词法融合，不是完整合同条款 RAG |
| DeepSeek API 与结构化输出 | `model_client.py`、`agents/prompts.py`、动态字段/动作 Schema | 配置在 `backend/.env`；不依赖原生 tool_calls，JSON 动作由服务器校验和分派 |
| 原文证据校验与监督 | `candidate_validation.py`、独立复核、全合同覆盖检查、类型/日期/选项约束 | 引用存在不代表语义必然正确；模型判断不能替代人工确认 |
| 合同填写与 Word 导出 | 原始 DOCX → 结构槽位 → 审核值 → XML 定点写入 | 不把整个 Word 交给模型重写；复杂结构仍拦截，版面需人工检查 |
| 人机协同 | 主控提出问题、字段审核/暂留空、预览及导出确认 | 不自动选择争议方案、批准字段或导出 |

## 本次补强的实际循环

1. 主控读取 `allowed_actions` 和当前观察，返回经过 Schema 限制的下一动作。
2. 模板阶段：调用分析角色、检索、读取候选结果，可更换聚焦词再次检索，最后交用户。相同检索词会停止循环，原文明确点名原件始终保持优先。
3. 填写阶段：提取候选 → 程序校验 → 独立复核 → 主控决定修正/提出问题/交人工。
4. 修正只针对已标记问题的本批字段。再次校验与独立复核完成后才合并；失败保留最近一次完成复核的结果；未涉及字段不改。
5. 所有动作仍受工具白名单、修正/检索次数、共享模型请求数、时间预算和用户权限约束。不能越权调用确认或导出。

这是有界的 supervisor/worker 与 evaluator/repair 协作，不是无限自治或多模型投票。设计借鉴 [Anthropic 的 Agent 与 evaluator-optimizer 模式](https://www.anthropic.com/research/building-effective-agents)及 [LangGraph 的 workflow/agent 区分](https://docs.langchain.com/oss/python/langgraph/workflows-agents)，当前不依赖这些框架运行。

## 离线验收入口

在已安装依赖的 backend 目录运行：

```powershell
python -m unittest discover -s tests -p test_agent_coordination.py -v
python -m unittest discover -s tests -p test_contract_workflow.py -v
```

场景覆盖：错误模板候选触发主控改写检索词；旧报价被复核发现、主控定向修正并再次复核；未知信息交用户；伪造引用不能冒充已验证；未知目标/导出动作被拒绝；重复检索/修正预算终止；修正或再次复核失败保留已有候选；修正结果只有经人工批准才能写进最终 DOCX。另有模拟 HTTP + 真实适配器验证动作并非由测试代码在生产路径硬编码，SQLite 日志验证所选动作持久化。

这些是使用假模型/模拟 HTTP 的程序行为验收，不是 DeepSeek 提取准确率、推荐命中率或成本改善证明；也不代表当前仍有未运行的真实服务商验收已经完成。

## 后续优化优先级

1. 建立带标注的保管/买卖等纪要集，分开统计模板 Recall@5、字段准确率、证据支持率、需人工纠正数、修正前后变化与耗时/费用。真实 API 运行需明确记录模型、配置、日期和费用；没有结果不写提升百分比。
2. 在现有字段审核基础上加入有版本管理的补充记录，再做增量重提取和问题状态更新；当前问题列表只是本次快照。
3. 针对重点原件增加人工版面验收，优先提升常用合同可用性，再考虑桌面打包。当前不承诺任意原件均可填写或法律完整性。
