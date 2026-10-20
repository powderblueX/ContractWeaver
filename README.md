# 法理智推 · LawReasoner Agent

法理智推是一个面向中国民事法律问题和合同起草的可审计 Agent。用户在同一个对话里描述事实或合同需求；模型决定调用哪些受控工具，观察法条或模板检索结果，再继续分析。合同文件只在用户本轮明确要求且勾选允许生成时创建，缺失字段保留在文档中供人工核对。

> 输出是辅助分析与合同草稿，不替代专业法律审查。内置《民法典》数据是项目内的静态副本，上线前须核验版本与现行效力。用户输入将发送到配置的模型服务商。

## 功能

- Agent 工具：搜索/读取《民法典》、搜索合同模板、查看模板字段、生成 DOCX。每轮限制工具步数，执行记录与对话一起保存；法条原文作为可展开的依据显示在回复旁。
- 合同资源：保留原项目及 `AI-Contract-Generator` 的部委、地方合同模板和占位符数据，共 567 份。默认基于名称和模板关键词本地检索；可选加载本地 `all-MiniLM-L6-v2 + FAISS` 索引增强排序。
- 账户和会话：注册、登录、注销、历史对话、会话重命名/删除、按用户隔离的合同下载。令牌是加密安全的随机值，数据库仅存储其 SHA-256 摘要；密码使用带随机盐的 PBKDF2。
- 《民法典》按需由 Agent 工具查询，界面不再有独立知识库入口。

## 架构

```text
LawReasoner-FrontEnd/src/
  features/agent/       Agent 工作台
  features/auth/        登录与注册
  shared/               httpClient、authSession 和共享样式
  router/               页面路由与访问控制

LawReasoner-BackEnd/
  app/api/              HTTP 路由、验证和依赖注入
  app/legal_agent.py    工具决策循环与白名单
  app/model_client.py   OpenAI 兼容模型接口
  app/services/         civil_code 与 contract_templates 领域服务
  app/repositories/     用户、会话和文档的数据访问
  app/database.py       SQLite 模式与事务
  app/security.py       密码和会话令牌
  app/config.py         统一环境配置
  resources/            民法典、合同模板、索引及本地模型
  data/                 运行数据与原数据库备份（不入库）
```

HTTP API 在 `/api/v1`，交互文档在后端 `/docs`。前端开发环境通过 Vite 代理转发 `/api`；生产环境应由反向代理提供同源 `/api/v1`。

## 本地运行

需要 Python 3.11+ 和 Node.js 20+。在 Windows PowerShell 中：

```powershell
cd LawReasoner-BackEnd
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

在 `.env` 中设置 `LAW_LLM_API_KEY`，必要时修改 `LAW_LLM_BASE_URL` 与 `LAW_LLM_MODEL`。模型服务须支持 OpenAI 兼容的 `chat/completions` 和函数工具调用。启动后端：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

再开一个终端启动前端：

```powershell
cd LawReasoner-FrontEnd
npm ci
Copy-Item .env.example .env
npm run dev
```

浏览器打开 `http://localhost:5173`。未配置模型密钥时，健康检查与账户功能可用，Agent 请求会明确返回 503。

仓库不依赖已创建的虚拟环境或 `node_modules`：后端通过 `requirements.txt`（可选检索依赖见 `requirements-search.txt`）重建，前端通过 `package-lock.json` 和 `npm ci` 重建。后端 `.env` 只放本机或部署环境；前端 `.env` 只允许公开的 API 路径和开发代理地址，不能放模型密钥。

### 可选语义检索

默认检索不下载模型，可以直接使用。若要使用已迁入的本地模型与 FAISS 索引：

```powershell
cd LawReasoner-BackEnd
.\.venv\Scripts\python.exe -m pip install -r requirements-search.txt
```

设置 `LAW_EMBEDDING_MODEL_PATH` 为 `LawReasoner-BackEnd/resources/embedding/all-MiniLM-L6-v2` 的绝对路径。索引与文件名数量不符时，系统回退到关键词检索。模型路径和其它部署路径可通过环境变量覆盖，详见 `.env.example`。

## 配置与保密

所有模型密钥只从后端进程环境或本地 `.env` 读取；`.env`、数据库、生成合同、虚拟环境及前端构建目录已列入 `.gitignore`。不要在 `VITE_` 变量中放密钥，因为前端构建会公开它们。生产环境建议用部署平台的 Secret Manager 注入环境变量，不要把 `.env` 提交到仓库。原项目中的千问密钥、邮箱授权码和固定 JWT 密钥曾以明文存在，须在对应服务商处轮换或撤销；删除代码并不能撤销已泄露的凭据。

主要环境变量：

| 变量 | 用途 |
| --- | --- |
| `LAW_LLM_API_KEY` | 模型服务密钥，Agent 必填 |
| `LAW_LLM_BASE_URL` / `LAW_LLM_MODEL` | 模型端点和模型名 |
| `LAW_DATABASE_PATH` | SQLite 数据库路径 |
| `LAW_RESOURCES_DIR` / `LAW_GENERATED_DIR` | 模板资源与生成文件路径 |
| `LAW_CIVIL_CODE_PATH` | 本地《民法典》JSON 路径 |
| `LAW_EMBEDDING_MODEL_PATH` | 可选本地嵌入模型目录 |
| `LAW_CORS_ORIGINS` | 允许的前端来源，逗号分隔 |
| `LAW_MAX_AGENT_STEPS` | 单轮工具调用步数上限 |

旧数据库原件保留在 `LawReasoner-BackEnd/data/legacy_shared_db.db`。本次已导入现有 2 个账户和 1 个历史会话；如果重新部署到空数据库，可以运行 `python -m app.migrate_legacy`，脚本可重复执行。旧 bcrypt 密码在用户首次成功登录后升级为 PBKDF2。

## 验证

```powershell
cd LawReasoner-BackEnd
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
cd ..\LawReasoner-FrontEnd
npm run build
```

测试覆盖认证、Agent 法条工具、会话归属隔离、注销及合同 DOCX 占位符处理。真实模型调用需配置自己的密钥；测试中的 Agent 模型是受控替身，不产生计费请求。

## 当前边界

- 本地《民法典》检索只覆盖随项目提供的静态文本，不自动同步法规变更；回答仍需人工核对引用与事实。
- SQLite 适合单机或小规模部署。多实例部署应替换数据层为集中式数据库，并引入任务队列处理较长的模型调用。
- 合同草稿保留未填写的占位符，不自动补造事实；提交给他人前必须核对和审阅。
- 旧系统的邮件验证码、密码重置和个人资料编辑没有迁入新工作台；上线前若需要这些能力，应接入合适的身份服务或补齐对应流程。
