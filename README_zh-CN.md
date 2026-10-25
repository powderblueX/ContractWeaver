# 契织（ContractWeaver）· 基于多 Agent 协同的智能合同填写系统

[English](README.md) | 简体中文

版本号：`0.1.0`（初始开发版本）。这是围绕合同填写构建的 multi-agent 项目，不代表已经完成生产验收或真实服务商端到端验收；仓库没有创建发布标签。模板结构识别的适用范围见下文和[模板引擎说明](docs/template-engine.md)。

从合同协商的聊天记录或会议纪要出发，识别交易需求，检索合同模板，由用户选择模板，再提取对应字段、核对原文、补充修改，最后生成 DOCX 合同。

## 使用流程

完整学习入口：[Agent + Harness 中文图解](docs/agent-harness-guide.zh-CN.md) · [整个项目代码阅读顺序](docs/code-reading-guide.zh-CN.md) · [注释规范与检查](docs/code-commenting.md)。

主控 Agent 现已根据观察动态分派动作：分析后可调整检索词再次检索；独立复核后可定向修正问题字段并再次复核，或交用户补充。不是只给固定流水线的节点换名字；也不是无限自主改写合同。实现、测试和能力边界见 [项目能力证据](docs/project-evidence.md)。

LLM 请求的输入说明、处理顺序、字段映射与结构化输出规则，统一维护在 [prompts.py](backend/app/agents/prompts.py)，见 [任务提示词说明](docs/agent-prompts.md)。这与服务商的思考模式开关相互独立。

已补充合同专用 **Agent Harness**：统一执行预算、步骤白名单、SQLite 运行日志与并发租约。前端可展开查看真实步骤及简短决策摘要，不冒充模型内部完整思维链。思考模式配置、开源架构参考及中断恢复边界见 [Harness 说明](docs/agent-harness.md)。

页面提供“下一步”指引、实际请求计数、逐批状态、等待动画和审核概览。注册/登录只使用邮箱，不再需要用户名。操作和进度含义见[使用引导](docs/user-guide.md)。

可直接导入[虚构保管合同会议纪要](examples/meeting-minutes-custody.md)，对照[示例验收清单](examples/README.md)体验最终费用、缺失与分歧处理，以及一键暂留空后继续完善草稿。

1. 粘贴协商记录，或导入 TXT、Markdown、DOCX。保留发言人和协商先后顺序。
2. 记录分析 Agent 识别交易类型、已达成事项和待确认内容，生成检索意图。
3. 系统推荐候选模板并给出排序理由。用户也可搜索、分页浏览完整模板库，预览或下载原模板，自行选择。
4. 用户选定模板后，字段提取 Agent 按模板字段查找原文；独立复核 Agent 检查提议与最终约定、金额、当事人、时间和引用依据。
5. 界面逐项显示填写值、模板上下文、原文行号与引用、分歧和缺失项。用户确认、修正、补充；需要保留空白时明确填写原因。
6. 审核完所有字段后，查看文字预览，确认当前版本，再生成和下载 DOCX。

生成过程只采用用户审核后的值。记录、模板选择、原始提取值、人工修改、执行事件和各次生成版本均随合同任务保存。当前产品聚焦合同填写，已移除泛法律咨询与法条查询工作流。

## Multi-agent 的职责和边界

| 角色 | 输入 | 输出 | 调用时机 |
| --- | --- | --- | --- |
| 主控协调 Agent | 当前观察、可执行动作及剩余预算 | 动作、检索词、修正目标或补充问题 | 分析/检索后与每批复核后 |
| 记录分析 Agent | 带行号的协商记录 | 交易摘要、合同类型、检索词、待确认事项 | 用户点击分析记录 |
| 字段提取 Agent | 原记录、用户选定模板的字段与上下文 | 候选填写值、逐字原文引用、缺失与分歧 | 用户点击提取字段 |
| 独立复核 Agent | 原记录、模板字段、提取结果 | 依据不足、错误映射或未达成共识的问题 | 每批提取后 |
| 全合同覆盖 Agent | 完整记录、全部字段与提取值 | 已约定但未落入合同的事项、原模板文义歧义及带引用的补充建议 | 全部批次结束后 |

主控和四个专业角色使用同一套后端 API 配置、不同的任务指令和结构化结果模型。每个角色有独立消息上下文，提取与复核采用分批处理和有上限的并发。主控可调整检索词、定向修正问题候选或提出补充问题；修正后重新校验和独立复核，不会自动批准。覆盖检查是提取时的快照，不保证业务无遗漏，也不自动修改条款。用户负责选择模板和最终确认；服务器控制权限、预算及版本，Agent 不能覆盖用户选择或直接生成文件。

默认每批 30 个字段，最多 2 批并发。完整分析通常调用 1 次模型，提取、复核与全合同覆盖检查通常调用 `2 × ceil(字段数 / 每批字段数) + 1` 次，格式校验失败时可额外重试。成功批次会保存，失败批次可单独重试；人工已审核的字段不会在失败重试时被覆盖。`LAW_COVERAGE_MAX_CONTEXT_CHARS` 默认 120000 字符，超出时明确提示未完成覆盖检查，不截断后冒充完整检查。

复核 Agent 检查事实映射和协商状态，不执行法律合规审查。原文引用还会由服务器核验对应行和逐字片段；引用存在本身不能证明提取含义正确，所以所有填写值仍需人工确认。

## 大模型 API 在哪里配置

**唯一位置：`backend/.env`。** [.env.example](backend/.env.example) 已预设 DeepSeek Flash 的公开参数，密钥始终由你填写，不放在前端或仓库中。

在项目根目录运行（已有真实配置时不要覆盖）：

```powershell
if (-not (Test-Path backend/.env)) {
    Copy-Item backend/.env.example backend/.env
}
```

编辑后端 `.env`，使用以下配置并填写自己的密钥：

```dotenv
LAW_LLM_BASE_URL=https://api.deepseek.com
LAW_LLM_MODEL=deepseek-flash
LAW_LLM_API_KEY=你的API密钥
LAW_LLM_JSON_MODE=json_object
LAW_LLM_THINKING_MODE=disabled
LAW_LLM_REASONING_EFFORT=provider_default
LAW_LLM_MAX_TOKENS=8192
LAW_REQUEST_TIMEOUT=120
```

地址和模型标识以 [DeepSeek 官方文档](https://api-docs.deepseek.com/zh-cn/) 为依据。基础 URL 不含 `/chat/completions`。本项目通过 HTTPS 的 OpenAI 兼容 Chat Completions API 调用模型；默认要求 JSON 对象输出，当前工作流不依赖函数工具调用。使用其他兼容服务商时仍可更改地址和模型；其支持 JSON Schema 时可选择 `json_schema`，只支持普通文本时选择 `prompt`，服务器始终解析并校验 JSON，限制格式重试次数。

主控和四个专业 Agent 共用这一套配置。Flash 预设显式关闭思考模式，便于结构化提取时控制延迟和输出长度，并不代表自动保证事实正确。可将 `LAW_LLM_THINKING_MODE` 改为 `enabled`；使用不支持该扩展的其他服务商时选 `provider_default`，请求不会发送 `thinking` 参数。输出被截断时会提示减小批次或增加输出上限，不会把半截 JSON 当成成功结果。

远程 API 必须使用 HTTPS；本机服务可使用 `http://localhost` 或 `http://127.0.0.1`。进程环境变量优先于 `.env`。修改配置后重启后端。前端配置只能包含公开 API 路径和开发代理地址，不能放模型密钥。

`GET /api/v1/health` 返回缺失配置项名称和配置是否完整，不返回密钥，不实际调用模型。填写完整不等于连接已经验证，需要运行一次真实记录分析确认服务可用。自动测试隔离本地 `.env` 并使用模型替身，不读取你的真实密钥发起模型请求。

## 本地运行

**Windows 11、无 Docker：直接看[启动与彻底停止手册](docs/windows-quickstart.md)。** `stop-project.bat` 停服务并清缓存；`stop-and-clean.bat` 还删除依赖和构建产物，保留源码、密钥和用户数据，不误清其他项目。

新手优先阅读[逐步部署手册](docs/deployment.md)：Windows 运行 `scripts\setup.bat`，填写 `backend/.env` 的密钥后，分别运行 `scripts\start-backend.bat` 和 `scripts\start-frontend.bat`。Linux/macOS 提供同名 `.sh` 脚本。初始化不会覆盖已有密钥配置，也不会安装系统级 Python/Node.js。

也提供 `compose.yaml` 和前后端 Dockerfile：配置 `.env` 后运行 `docker compose up -d --build --wait`，访问 `http://localhost:8080`。Docker 方式使用独立持久化卷，不自动导入本地数据库；容器实跑验收状态见部署手册。

需要 Python 3.11+、Node.js 20+。在项目根目录打开 PowerShell：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# 按上一节创建并编辑 .env
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开终端启动前端：

```powershell
cd frontend
npm ci
# 默认同源 API 和本地开发代理即可运行；需要调整时复制 .env.example 为 .env
npm run dev
```

打开 `http://localhost:5173` 注册或登录。未配置模型时可以导入记录、浏览并选择模板、人工填写审核和导出；分析、自动提取和复核需要配置模型。

运行环境不随源码保存。后端按 `requirements.txt` 重建，前端按 `package-lock.json` 与 `npm ci` 重建。

本 README 保留快速启动；Windows、Linux/macOS 完整步骤、常见问题和服务器部署边界见 [部署说明](docs/deployment.md)。基础应用不需要 GPU、本地推理模型或向量数据库；自动分析和提取需要联网调用已配置的 API。

## 模板检索与资源

模板库只使用 `resources/contracts/templates/{Ministerial,Regional}/*.docx` 中的原始 Word 文档，不依赖旧占位符 DOCX 或 JSON。无需先把原件手工改写成 `{字段名}` 模板；原件已有明确标记仍兼容。

结构编译器在内存中识别连续下划线、带下划线的空白 run、段内连续空格、空白表格单元，以及冒号后的候选位置，生成可定位的内部字段。不同位置分别审核；表格字段附带首行、当前行及列号。原文件不修改，模型也不能直接重写合同。明确留空的自动识别位置在导出时恢复原有空白，不遗留内部标记。

检测是偏保守、过量召回的规则扫描：排版空格和条款标题也可能成为候选；单个普通空格、图片中的空白、依赖视觉语义的选项等不能保证识别。用户必须对照下载的原件核对填写范围。LLM 可以提取候选信息，但结构化 JSON 不保证事实和映射正确，不能宣称“任意合同无漏填”。图片和图形原样保留，不执行 OCR，导出前需单独确认视觉区域；Word 文本框参与填写，相同的新版/旧版兼容分支同步写入。嵌入对象、内容控件、修订、实际脚注及不一致分支仍硬拦截。

已按仓库所有者要求清理旧占位符 DOCX、占位符 JSON 及其说明文件；删除前已确认 1134 个资源与 Git 历史一致，可从历史恢复。原始合同、关键词和索引不删除。清理不代表被拦截模板已通过验收。详情见[模板引擎与验收边界](docs/template-engine.md)。

整库离线审计覆盖 567 份原件：494 份通过结构写入和重读检查，73 份仍拦截，错误为 0；通过的模板中 92 份需单独视觉确认。详见[验证记录](docs/validation.md)。审计检查所有已识别位置的写入、DOCX 保存/重新读取，以及图形和媒体保持；不是业务无遗漏或版面认证。

默认由 LLM 分析记录生成检索意图，名称 BM25、业务关键词 BM25、完整名称匹配通过 RRF 融合排序；可选加入本地向量召回。默认前 30 个候选经过结构安全过滤，最多推荐 5 份，不强行凑数。排序分不是适用概率，也不声称全库最优，详见[检索设计与评估](docs/template-retrieval.md)。模板库仍可独立分页浏览和手动选择。用户明确选择的模板 ID 和文件指纹会被保存；模板或引擎更新后须重新选择和审查。

明确点名的合同先按原名匹配：模型需保留原名和引用，程序还扫描原文中的明确正向请求兜底，不让泛化检索词覆盖点名意图。若点名原件被结构拦截，会显示原件和原因、允许查看下载但禁止自动填写。名称同义、版本歧义或后续改口仍需人工核对，不能承诺百分之百理解所有会话。

核心开发闭环不等于全部需求已经验收；请查看[需求交付状态](docs/requirements-status.md)，尤其是真实模型、剩余模板、容器实跑和资源授权。

可选启用随项目迁入的本地 MiniLM + FAISS 排序：

```powershell
cd backend
.\.venv\Scripts\python.exe -m pip install -r requirements-search.txt
```

将 `LAW_EMBEDDING_MODEL_PATH` 设置为本地 `resources/embedding/all-MiniLM-L6-v2` 的绝对目录。模型和索引必须保持对应；依赖或索引不可用时退回关键词检索。它仅用于模板检索，不是对话 LLM，也没有接入项目专属微调的对话模型。当前未搭建面向整库条款问答的 RAG。

## 架构

```text
backend/app/
  api/             分域路由、请求校验、依赖组合
  agents/          记录分析、字段提取、独立复核、共享模型连接
  domain/          类型化的工作流、字段状态和原文引用
  services/        工作流编排、文件导入、模板检索与 DOCX 填充
  repositories/    用户和任务持久化、并发版本控制
  config.py        环境配置与校验
  model_client.py  统一模型传输、结构化输出校验和有限重试
  database.py      SQLite 表结构和事务
  security.py      密码散列与不透明会话令牌

frontend/src/
  features/contracts/
    components/    记录导入、模板库、字段审核、预览导出
    contractApi.js HTTP 请求契约
    useContractWorkspace.js  服务端状态与操作
  features/auth/   登录和注册
  shared/          HTTP 客户端、登录会话、基础样式
```

工作流状态依次为 `source_ready → template_selection → template_selected → field_review → ready_to_generate → generated`。用户可以跳过推荐，直接选择模板，也可人工填写而不运行模型。

所有修改带 `revision`，服务器使用数据库比较并交换避免旧页面覆盖新修改。状态和合同文件归属在同一数据库事务中保存。导出使用已确认字段；自动识别位置明确留空时恢复原空白，原件已有的手写占位符明确留空时仍保留该标记。文件指纹及填写引擎版本锁定字段映射，旧任务需要重新选择模板。后续修改会使旧预览失效；已生成的文件作为历史版本保留。删除任务会删除其记录、审核结果和该任务生成的文件。

交互 API 文档在 `http://127.0.0.1:8000/docs`。主要路由见 [API 与工作流说明](docs/contract-workflow.md)。

## 配置项

| 配置 | 用途及默认值 |
| --- | --- |
| `LAW_LLM_BASE_URL` / `LAW_LLM_MODEL` / `LAW_LLM_API_KEY` | 模型地址、标识、密钥；均需显式配置 |
| `LAW_LLM_JSON_MODE` | `json_object`、`json_schema` 或 `prompt` |
| `LAW_LLM_THINKING_MODE` | `provider_default`、`enabled` 或 `disabled`；Flash 示例为 `disabled` |
| `LAW_LLM_REASONING_EFFORT` | `provider_default`、`low`、`high`、`max`；启用前确认服务商支持 |
| `LAW_HARNESS_MAX_REQUESTS` / `LAW_HARNESS_MAX_STEPS` | 每轮跨并行批次和重试的请求/步骤预算，均默认 512 |
| `LAW_HARNESS_TIMEOUT_SECONDS` | 每轮总执行期限，默认 3600 秒；不是后台队列承诺 |
| `LAW_HARNESS_MAX_INPUT_CHARS` | 单次请求 JSON 字符数上限，默认 500000，不等于 Token 上限 |
| `LAW_LLM_MAX_TOKENS` / `LAW_LLM_TEMPERATURE` | 输出上限 8192 / 温度 0.2；显式开启思考时不发送温度 |
| `LAW_STRUCTURED_OUTPUT_RETRIES` | 结构化输出格式重试，默认 1，最多 2 |
| `LAW_REQUEST_TIMEOUT` | 单次请求代码默认 90 秒，Flash 配置示例为 120 秒 |
| `LAW_FIELDS_PER_BATCH` / `LAW_AGENT_PARALLELISM` | 每批字段数 30 / 最多并发批数 2 |
| `LAW_MAX_SOURCE_CHARS` / `LAW_MAX_UPLOAD_BYTES` | 单份记录默认 60000 字符 / 上传默认 5 MB |
| `LAW_DATABASE_PATH` | 新安装默认 `data/contractweaver.db`；已有旧数据库自动沿用，不搬动或删除 |
| `LAW_RESOURCES_DIR` / `LAW_GENERATED_DIR` | 模板根目录 / 生成文件目录 |
| `LAW_EMBEDDING_MODEL_PATH` | 可选本地检索模型，默认禁用 |
| `LAW_CORS_ORIGINS` | 默认 `http://localhost:5173`，逗号分隔 |
| `LAW_TOKEN_HOURS` | 登录令牌有效期，默认 24 小时 |

## 验证与维护

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd ../frontend
npm test
npm run build
npm run format
```

需要 Python 格式检查时安装 `requirements-dev.txt`，运行 `ruff check app tests` 和 `ruff format app tests`。模板资源可用 `python -m app.cli.audit_templates` 做离线审计；该命令不调用模型、不修改原文件。

本次测试、真实模板写入检查和整库扫描结果见 [验证记录](docs/validation.md)。仅看汇总可运行 `python -m app.cli.audit_templates --summary --progress`。

后端测试覆盖真实 SQLite/DOCX 端到端流程、伪造引用、人工补充与留空、手动选模板、并发修订、文件归属与删除、模板版本变化、配置和模型响应错误。前端测试覆盖手动选模板、逐字段审核时保留其他未保存修改、预览确认与版本失效、请求失败时保留已提交状态。

数据库启动时增加新表，不删除已有用户和旧会话。旧聊天表仅作为历史保留，不混入新合同工作流；旧数据库备份保留在 `data/legacy_shared_db.db`。需要向空数据库导入旧用户时可运行 `python -m app.migrate_legacy`，迁移脚本可重复执行，旧密码在首次登录后升级散列。

`.env`、数据库、生成合同、依赖环境和构建产物均不提交到 Git。生产部署可由 Secret Manager 注入配置；曾在旧项目公开过的密钥仍需由所有者撤销或轮换。

当前导入支持文本和 DOCX，不支持音频转写、图片 OCR 或 PDF；一份任务按一笔交易处理，建议先拆分包含多笔交易的长记录。预览按段落和表格展示文字，不是 Word 版面渲染。大模板可能需要较多 API 请求；可以轮询同一后端进程中的实时状态，但服务重启可能丢失未保存结果，不是持久化后台队列。SQLite 面向本地或单机部署，多实例需进一步接入集中式数据库与任务队列。

## 项目规模与仓库

采用 `backend/`、`frontend/`、`docs/`、`scripts/` 的轻量单仓结构：一个后端进程、一个前端应用，后端内部按职责分层，不把每个 Agent 拆成独立微服务，也不引入空的共享包或额外编排框架。

项目展示名、GitHub 仓库名和本地根目录均可使用 **ContractWeaver**。建议重命名现有仓库以保留历史，而不是删除 `.git` 或重建仓库。产品可作为新项目呈现，无需抹掉来源；具体步骤见[仓库命名与迁移](docs/repository.md)。本地根目录已改名，应用通过相对路径运行，不绑定原来的绝对目录。

为避免破坏已有 API 配置，`LAW_` 环境变量名称继续保留；前端仍不能保存模型密钥。创建数据库、模板与历史文件的兼容说明见[维护与迁移](docs/maintenance.md)。安装开发依赖后，可从根目录运行 `./scripts/check.ps1` 统一检查。
