# 合同 Agent Harness 与可解释执行

## 当前实现

项目使用自己的受限 `ContractHarness`，不是 LangChain/LangGraph 的包装，也不是通用自动编程 Agent。当前增加了主控 `SupervisorAgent`：由 LLM 根据工具观察动态选择下一动作，而不是仅展示代码预设计划。领域状态与人工关卡仍由服务器强制执行。

参考开源 [Deep Agents 架构](https://github.com/langchain-ai/deepagents/blob/main/libs/ARCHITECTURE.md) 的 middleware/能力边界分离，以及 [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence) 的持久状态思路。当前合同流程明确且人工关卡较多，保留现有领域状态和 CAS 修订，避免同时维护两套状态源。不安装 LangChain、LangGraph、Deep Agents，也不需要 LangSmith 密钥。

## 流程与能力边界

主控决策 → 分析记录 → 主控检索/观察/调整检索词 → **用户选择** → 分批提取与证据校验 → 独立复核 → 主控定向修正/再次复核或提出补充问题 → 全合同覆盖检查 → **用户确认/修改/暂留空** → 预览确认 → 代码生成 Word。

- `app/agents/harness.py`：能力白名单、任务隔离上下文、全运行请求/步骤/时间/单次输入预算。所有主控、并行批次、修正与 JSON 重试共享预算。`plan` 是可用能力清单，不是执行顺序；`steps` 与 `chosen_action` 才是实际轨迹。
- `app/agents/supervisor.py`：LLM 返回 action/目标/简短依据；Schema 动态限制当前 allowed_actions，服务器再验证参数及可修正目标。是结构化动作协议与受限分派，不是提供商原生 tool_calls，也不是让模型自由执行 Python。
- `negotiation_coordinator.py`：强制先分析、至少一次检索，然后主控可选择聚焦词重新检索、提出问题或交回用户；跨轮融合保留原文点名原件的优先级。重复检索词停止循环并保留已有结果。
- `field_coordinator.py`：必须先提取、校验及独立复核，主控才能选择修正问题字段或请求人工补充。修正目标必须是本批已标记的问题，修正后重新校验并独立复核；完成后才合并，失败保留最近一次完成复核的候选。达到次数上限仍有问题则交人工，不伪装为自动解决。
- `app/repositories/agent_runs.py`：SQLite 日志和跨进程运行租约。每任务最多保留最近 20 条运行；成功、部分成功和失败均可查。删除任务时级联删除这些日志。
- 模型只提出结构化结果，不能批准字段、选择模板、绕过视觉检查或调用导出；没有 Shell、网络搜索或任意文件读写工具。代码限定模型调用和本地检索。
- 运行完成状态在领域状态提交成功后公布。失败不会冒充成功；并行执行下步骤按实际启动顺序记录，而不是编造串行“思考顺序”。
- `GET /api/v1/workspaces/{id}/activity` 返回当前运行与步骤；`GET /api/v1/workspaces/{id}/runs` 返回最近运行，均需登录并校验任务归属。前端进度卡可展开查看计划、步骤、耗时、决策摘要和服务商 Token 使用统计。

这是一套有持久审计的有界 harness，**不是持久后台队列或 LangGraph checkpointer**。正常完成和部分失败后保存领域状态；可重试失败字段，保留已审核项。进程在调用中崩溃时，未提交的输出可能丢失；租约在运行期限后显示 interrupted，用户需重新执行，不宣称从中间 Token 或节点自动恢复。请求内同步本地检索在线程中执行，取消不能强杀已进入的线程；其不会执行导出等有副作用的动作。生产级任意节点恢复/断线后台执行仍需额外队列与幂等检查点设计。

## 思考模式、CoT 与决策摘要

若“CoT”指请求中的任务处理指导，而不是服务商内部推理，请看 [Agent 任务提示词](agent-prompts.md)：主控及四个专业角色的输入说明、处理顺序、映射示例和输出契约已集中维护，不依赖思考模式开关。

框架不会凭空给非推理模型添加内部 CoT，也不能保证模型公开完整内部推理。项目提供的是可验证的原文引用、约束校验、独立复核，以及 `decision_summary`（最多 1000 字符的简短结论/依据/待定事项）。摘要是模型输出的解释，不是内部推理录音，不保证正确；没有摘要时如实显示缺失，不伪造。

[DeepSeek 官方思考模式文档](https://api-docs.deepseek.com/guides/thinking_mode/)说明兼容接口可用 `thinking` 启用思考，`reasoning_effort` 调整强度。配置在 **`backend/.env`**，以 `.env.example` 为说明；本次不改动用户私有 `.env`。

```ini
LAW_LLM_BASE_URL=https://api.deepseek.com
LAW_LLM_MODEL=deepseek-flash
LAW_LLM_API_KEY=填写你自己的密钥
LAW_LLM_THINKING_MODE=enabled
LAW_LLM_REASONING_EFFORT=high
LAW_LLM_JSON_MODE=json_object
LAW_LLM_MAX_TOKENS=16384
LAW_REQUEST_TIMEOUT=180
```

修改后重启后端。思考会增加延迟和 Token 使用，输出预算不足可能发生截断；可降低每批字段数或调整输出上限。以上不是替所有服务商保证兼容，错误会明确返回，不自动降级到非思考模式。换用其他兼容服务商时，优先设置两项为 `provider_default`，避免发送其不支持的扩展参数。显式 enabled 时不发送 temperature。

服务商返回的原始 `reasoning_content` 不写入数据库、不暴露到 UI、不送去下一角色；当前也没有需要回传该字段的原生多轮 tool-call 协议。简短摘要、原文证据和字段结果与任务一样属于私有业务数据，运行日志也需按合同数据保护；不要在摘要填写密钥或敏感认证信息。

## 安全预算配置

```ini
LAW_HARNESS_MAX_REQUESTS=512
LAW_HARNESS_MAX_STEPS=512
LAW_HARNESS_TIMEOUT_SECONDS=3600
LAW_HARNESS_MAX_INPUT_CHARS=500000
LAW_SUPERVISOR_MAX_SEARCHES=3
LAW_SUPERVISOR_MAX_REPAIRS=1
```

请求数在每次传输前预留；结构重试也计入，不是账单统计。单次输入按请求 JSON 字符数检查，不等于模型 Token 上限；服务商返回 usage 时才累计 Token，缺失时不估造。预算耗尽不会再发新请求，已完成但尚未汇总的批次按现有部分失败流程处理；总超时则结束本轮，未提交结果不保证保留。HTTP 请求仍受单次 `LAW_REQUEST_TIMEOUT` 约束。运行日志只保存计划、状态和简短摘要/数值元数据，不保存完整提示词、API Key、HTTP 响应正文或内部思维链。

检索上限是每次分析的总检索次数；修正上限是每批的修正轮次（允许 0 关闭修正，但保留主控交接决策）。主控调用会增加耗时与费用，不能把新增调用数说成准确率提升。主控失败会明确提醒；初次规划/分析失败则本轮失败，已有分析后的规划失败保留可用结果；修正失败保留已复核候选。补充问题是本次结果的快照，用户在现有审核界面补填，不是已经实现了无限轮对话记忆或自主修改纪要。
