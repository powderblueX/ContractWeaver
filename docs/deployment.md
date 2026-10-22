# 本地运行与部署

README 提供项目介绍和可复制的快速启动，本文件提供平台差异、完整验证、排障及服务器部署边界。这是常见的开源项目组织方式，不存在所有 GitHub 项目必须采用的唯一部署文档格式；参见 [GitHub README 指南](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)。

Windows 11 且无 Docker 的用户可直接跟随[专用入门与关闭手册](windows-quickstart.md)。示例会议纪要及验收清单在 [examples/](../examples/README.md)。

## 前置条件与运行范围

- Python 3.11+、Node.js 20+ 和 npm，能安装依赖。
- 自动分析、提取和复核需要互联网和有效 DeepSeek API Key；基础应用不需要 GPU、CUDA、本地 LLM、Redis 或向量数据库。
- SQLite 默认在后端 `data/` 创建数据，已有数据库会沿用；模板随项目提供，原件目录为 `backend/resources/contracts/templates/`。
- 未填写密钥仍可启动、注册登录、导入记录、选模板、人工审核并导出支持的合同；模型功能会提示缺失配置。
- 当前为单机、人工审核的开发版本，不是所有模板均可用的无人值守服务。567 份原件的当前结构支持范围见[验证记录](validation.md)；含图形的可填写模板还需单独视觉确认。

## 新手从这里开始：两种方式选一种

先下载并解压源码，或 `git clone` 后进入含 `README.md`、`backend/`、`frontend/` 的项目根目录。GitHub 仓库名称不影响启动，不需要修改 Git 远程地址。首次下载后不要移动内部目录。

### 方式 A：本地开发（有 Python 和 Node.js）

1. 安装 Python 3.11+（新手建议 3.12）和 Node.js 20+，Windows 安装 Python 时勾选加入 PATH。重新打开终端，运行 `python --version`（Linux/macOS 用 `python3 --version`）、`node --version`、`npm --version` 确认成功。Linux 可能需安装系统的 Python venv 包。脚本不会安装系统软件或请求管理员权限。
2. 初始化依赖，必须等待命令成功退出：

   Windows，在项目根目录运行 `scripts\setup.bat`，也可双击它。Linux/macOS 运行 `bash scripts/setup.sh`。默认后端环境保存在 `backend/.venv/`，前端依赖在 `frontend/node_modules/`，已有 `backend/.env` 不会被覆盖。

3. 用文本编辑器打开 `backend/.env`，填写 `LAW_LLM_API_KEY`，其他 DeepSeek 默认参数可先不改。文件没有出现时，将 `backend/.env.example` 复制为 `.env`；Windows 注意不要误存成 `.env.txt`。不要把密钥配置在前端。
4. 分别启动并保持两个终端打开：

   | 系统 | 后端终端 | 前端终端 |
   | --- | --- | --- |
   | Windows | `scripts\start-backend.bat` | `scripts\start-frontend.bat` |
   | Linux/macOS | `bash scripts/start-backend.sh` | `bash scripts/start-frontend.sh` |

5. 浏览器打开 `http://localhost:5173`，注册并登录；后端 API 文档是 `http://127.0.0.1:8000/docs`。如果后端启动失败，先看后端终端错误，不要反复点击分析。
6. 用不含真实敏感信息的记录尝试分析 → 模板选择 → 提取与复核 → 人工纠正/补充/确认 → 预览 → 下载 Word。分析和提取会向模型服务商发送记录与字段上下文并产生 API 费用；密钥为空时可先测试人工填写链路。
7. 停止：Windows 在项目根目录运行 `scripts\stop-project.bat`，清除项目服务/启动器及子进程并清理临时缓存；需要连依赖与构建产物一起删除时用 `scripts\stop-and-clean.bat`，下次先重新初始化。Linux/macOS 分别在两个终端按 Ctrl+C。更新源码后再次运行初始化，修改后端 `.env` 后重启后端。两种 Windows 清理均保留 `.env`、源码、模板和 `backend/data/`，不会清除其他项目或系统共享缓存。详情和限制见 Windows 手册。

只安装一端时：Windows 使用 `scripts\setup.bat -Component backend` 或 `-Component frontend`；Linux/macOS 使用 `bash scripts/setup.sh backend` 或 `frontend`。Windows `.bat` 只对当前 PowerShell 进程使用执行策略参数，不修改系统策略；可审阅对应 `.ps1` 后再运行。脚本自动定位项目位置，支持目录名包含空格。

默认端口为后端 8000、前端 5173；端口被占用时不会偷偷切换。Windows 可在终端执行 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-backend.ps1 -Port 8001`，前端脚本同理支持 `-Port 5174`。Linux/macOS 可在命令前设置 `CONTRACTWEAVER_BACKEND_PORT=8001` / `CONTRACTWEAVER_FRONTEND_PORT=5174`。后端改端口还需修改 `frontend/.env` 的 `VITE_DEV_API_TARGET`；前端改端口需相应修改后端 `LAW_CORS_ORIGINS`。两端均应重启。

### 方式 B：Docker Compose（无需单独安装 Python/Node.js）

Docker 不是开源项目的硬性要求，但便于复现运行环境。本仓库提供 `compose.yaml`、两端 Dockerfile 与 Nginx 同源代理。安装并启动 Docker Engine/Desktop 和 Compose v2.24+，先确认 `docker info`、`docker compose version` 成功，再在项目根目录操作。首次需要联网拉镜像、安装依赖并构建。

1. 只在 `.env` 不存在时复制配置：Windows 用 `if (-not (Test-Path backend/.env)) { Copy-Item backend/.env.example backend/.env }`；Linux/macOS 用 `test -f backend/.env || (umask 077; cp backend/.env.example backend/.env)`。
2. 编辑 `backend/.env` 中的 API Key；不要运行会将配置值输出到终端的调试命令，不要把 `.env` 提交到 Git。
3. 运行 `docker compose config --quiet` 检查配置，再运行 `docker compose up -d --build --wait --wait-timeout 180`。第一次构建可能较久；镜像构建本身不受这个健康等待时间限制。
4. 打开 `http://localhost:8080`。同源 `/api/` 转发到内部后端，后端 8000 端口不直接发布；健康接口为 `http://localhost:8080/api/v1/health`。
5. 查看状态 `docker compose ps`，排错 `docker compose logs --tail 100 backend frontend`。停止用 `docker compose down`，再次启动用相同的 `up` 命令；不要使用 `down -v`，它会删除持久化数据卷。
6. 修改模型配置后运行 `docker compose up -d --force-recreate --wait`，不是仅刷新网页。更新代码时重新运行带 `--build` 的命令。

配置通过 Compose 文件型 secret 只挂载到后端，不进入镜像或前端。后端启动引导程序只为读取宿主机私有配置短暂以 root 运行，将配置复制到容器内私有临时文件，再降权为 UID/GID 10001 后启动 API；HTTP 服务不以 root 运行。本地 Compose 文件型 secret 不等于生产 Secret Manager，仍要限制宿主机文件与 Docker 管理权限。实现依据见 [Docker secrets](https://docs.docker.com/compose/how-tos/use-secrets/)。

默认数据保存在 `contract_data` 命名卷中，**与本地 `backend/data/` 分开，不自动迁移旧账号或合同**。备份需同时包含 SQLite 与生成文件，建议停机后使用 Docker 的卷备份方式；不要只拷贝数据库而漏掉 DOCX。Compose 中的数据库、资源和导出路径覆盖 `.env` 中宿主机绝对路径。本镜像只打包原始模板，默认 BM25 检索，不包含可选的大型 embedding 模型和 FAISS 索引。

默认仅绑定 `127.0.0.1:8080`。需要调整时在运行 Compose 前设置公开变量 `CONTRACTWEAVER_PORT` 或 `CONTRACTWEAVER_BIND_ADDRESS`；不要未经 HTTPS、访问控制、备份与限流验收就绑定公网。基础镜像按版本系列指定，不是摘要锁定；生产发布仍需固定摘要和漏洞扫描。

本机已验证 Compose 解析，但 Docker daemon 未运行，尚未完成镜像构建与容器端到端验收。Linux/macOS 脚本已做 Bash 语法检查，尚未在这两个系统实际部署。不要把配置文件存在等同于部署验收完成。

## 1. 配置 DeepSeek Flash

只在 `backend/.env` 配置，勿放在任何 `VITE_` 变量中。已有文件不要用示例覆盖，修改对应行即可：

```dotenv
LAW_LLM_BASE_URL=https://api.deepseek.com
LAW_LLM_MODEL=deepseek-flash
LAW_LLM_API_KEY=替换成你自己的密钥
LAW_LLM_JSON_MODE=json_object
LAW_LLM_THINKING_MODE=disabled
LAW_LLM_REASONING_EFFORT=provider_default
LAW_LLM_MAX_TOKENS=8192
LAW_LLM_TEMPERATURE=0.2
LAW_REQUEST_TIMEOUT=120
```

这是 [DeepSeek 官方支持的模型标识与地址](https://api-docs.deepseek.com/zh-cn/)，不是本地部署模型。服务器实际请求 `https://api.deepseek.com/chat/completions`。主控与四个专业 Agent 使用同一个模型，不同职责和独立上下文，不共享一个不断膨胀的对话历史。

`json_object` 和提示词内的 JSON Schema 用于输出结构，服务器再进行 Pydantic 校验。参考 [JSON 输出说明](https://api-docs.deepseek.com/guides/json_mode/)。Flash 的思考模式默认由服务商开启；本示例按 [思考模式说明](https://api-docs.deepseek.com/guides/thinking_mode/)显式关闭，便于控制提取请求的时间和输出预算，不代表提高了事实准确性。可选 `enabled`；显式启用时不发送温度。切换其他兼容服务商时应使用 `provider_default`，避免发送其不支持的扩展参数。

需要推理模式时，可在私有 `.env` 设置 `LAW_LLM_THINKING_MODE=enabled`、`LAW_LLM_REASONING_EFFORT=high`，并按延迟/截断情况调整 `LAW_LLM_MAX_TOKENS` 和 `LAW_REQUEST_TIMEOUT`。前端展示执行轨迹与简短决策摘要，不展示原始内部 CoT。Harness 默认无需额外服务或密钥，SQLite 新表由后端初始化时创建；细节与恢复边界见 [Harness 文档](agent-harness.md)。

环境变量优先于 `.env`。若修改文件不生效，检查进程是否仍注入旧环境变量，并重启后端。`.env` 已被 Git 忽略，不要把密钥贴进聊天、截图、Issue 或提交记录。

## 2. Windows / PowerShell

在 `ContractWeaver` 根目录打开终端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# 编辑 .env，填写密钥
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端终端保持运行，另开一个终端回到项目根目录：

```powershell
cd frontend
npm ci
npm run dev
```

打开 `http://localhost:5173`。默认开发代理把 `/api` 请求转发到 `http://127.0.0.1:8000`，无需另设前端配置。需要更改时使用 `frontend/.env.example` 的公开变量；修改后重启前端。

API 文档：`http://127.0.0.1:8000/docs`。健康检查：

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health
```

`status=ok` 说明后端已启动；`model_configured=true` 只说明配置齐全，不证明密钥有效或服务可达。

## 3. Linux / macOS

在项目根目录执行：

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
test -f .env || cp .env.example .env
# 编辑 .env
chmod 600 .env
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另一个终端从项目根目录执行 `cd frontend`、`npm ci`、`npm run dev`，访问地址和 Windows 相同。Linux/macOS 命令按平台路径提供，当前本地验收环境为 Windows，未声称逐平台实际部署验收。

## 4. 真实模型连通性与完整工作流验证

在后端目录、密钥配置完成后，手动执行：

```powershell
.\.venv\Scripts\python.exe -m app.cli.check_llm
```

Linux/macOS 使用 `.venv/bin/python -m app.cli.check_llm`。该命令会向已配置的 API 发送一次合成 JSON 测试，可能产生少量费用；不读取任务、上传合同或输出密钥，也不进行格式重试。成功只证明连接和结构化返回可用，不代表合同提取准确率已经验收。

随后在界面中注册/登录，使用不含敏感数据的短协商记录验证：导入 → 分析 → 选择模板 → 提取/复核 → 纠正与补充 → 逐项确认或说明留空 → 预览 → 下载 DOCX。分析和提取会额外产生 API 费用。所有事实值仍需人工审核，导出后还要核对 Word 排版。

自动化测试不需要真实密钥：安装 `backend/requirements-dev.txt` 与前端依赖，在 PowerShell 根目录运行 `./scripts/check.ps1`；Linux/macOS 分别运行后端 `python -m unittest discover -s tests -v`、`ruff check app tests` 和前端 `npm test`、`npm run build`。测试使用替身并隔离本地 `.env`，不会自动运行真实模型探针。

## 5. 常见问题

| 现象 | 检查项 |
| --- | --- |
| 前端打开但 API 失败 | 后端是否在 8000 端口；`VITE_DEV_API_TARGET` 是否正确；终端是否位于正确目录 |
| 401/403 模型错误 | `.env` 的 API Key、平台权限；不要把登录应用的会话令牌当作模型密钥 |
| 404 模型错误 | 基础地址及 `deepseek-flash` 拼写；不要重复添加 `/chat/completions` |
| 429 或余额不足 | 服务商额度、限流；可降低 `LAW_AGENT_PARALLELISM`，不要无上限重试 |
| 请求超时 | 网络、思考模式及 `LAW_REQUEST_TIMEOUT`；长记录/大模板会增加总调用时间 |
| 输出达到长度上限 | 减小 `LAW_FIELDS_PER_BATCH` 或在模型支持范围内增加 `LAW_LLM_MAX_TOKENS` |
| 配置已改但无效 | 重启服务，检查进程环境变量是否覆盖 `.env` |
| 模板不允许选择 | 属于安全拦截，不是缺 API Key；维护原件结构后再验收，不能绕过限制 |
| 模板库为空 | 检查 `LAW_RESOURCES_DIR`；根目录改名后，旧的自定义绝对路径需要更新 |

默认单份记录不超过 60000 字符，上传不超过 5 MB；支持 TXT/MD/DOCX，不支持 PDF、OCR 或音频。长记录与大模板会分批请求，页面不是实时流式任务队列。

## 6. 服务器部署边界

以下是部署要求，不是已经完成生产验收的声明。已有本地脚本与 Compose 配置，但尚未完成多平台和容器运行验收。

1. 前端执行 `npm ci`、`npm run build`，仅发布 `frontend/dist/`。不要用 Vite 开发服务器对公网提供正式服务，也不要把仓库根目录或 `.env` 作为静态目录。
2. 后端由进程管理器以 `uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1` 启动。当前 SQLite 与同步工作流先按单实例使用；多实例应先设计集中数据库、任务队列及文件存储。
3. 通过 HTTPS 反向代理把 `/api/` 原路径转发到后端，其他路径服务前端静态文件并支持 SPA 回退。不要去掉 `/api/v1` 前缀。代理的请求体和超时需匹配上传限制及长模型请求。
4. 优先使用 Secret Manager 注入密钥；限制 `.env`、数据库、生成合同的读取权限。备份 `data/`，验证文件所有权与恢复流程。
5. 跨域部署时显式配置 `LAW_CORS_ORIGINS`；同源反向代理通常更简单。补充限流、登录防滥用、监控、日志脱敏与容量验证后再开放公网。

README 保留能让新用户跑起来的最小步骤；运维细节放本文件，工作流接口放 [API 说明](contract-workflow.md)，资源维护放 [维护说明](maintenance.md)，实际验收范围放 [验证记录](validation.md)。
