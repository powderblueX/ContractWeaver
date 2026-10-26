# 契织（ContractWeaver）

简体中文 | [English](README.md)

契织是一套面向合同填写的多 Agent Web 应用。用户提交协商聊天记录或会议纪要，系统分析交易信息、检索合同模板、提取待填字段并执行独立复核。模板选择、字段确认、留空决定和最终导出始终由用户控制。

## 核心流程

1. 导入 TXT、Markdown、DOCX，或直接粘贴协商记录。
2. 记录分析 Agent 整理合同类型、已确认事项、分歧和缺失信息。
3. 检索系统返回最多五份候选模板，用户也可以浏览模板库自行选择。
4. 字段提取 Agent 按模板位置生成候选值和原文依据。
5. 独立复核 Agent 检查证据、格式和冲突；主控 Agent 可安排一次定向修正。
6. 用户批量确认、修改或暂留空，检查预览后导出 DOCX。

模板文件保持原始 DOCX 结构。模型接收会议纪要、字段位置和局部上下文，返回结构化候选数据；文档引擎负责把用户确认的值写回 Word。

## 技术栈

- 前端：Vue 3、Vite、Vue Router、Vitest
- 后端：FastAPI、Pydantic、SQLite
- 模型：OpenAI 兼容接口，默认配置为 DeepSeek Flash
- 检索：名称 BM25、业务关键词 BM25、完整名称匹配、RRF 融合；可选本地 FAISS 向量通道
- 文档：原始 DOCX 结构扫描、字段定位、写入后完整性检查
- Agent：受限主控、四个专业角色、共享执行预算、运行日志和并发租约

## Windows 11 快速启动

准备 Python 3.11+、Node.js 20+。

```bat
scripts\setup.bat
```

复制模型配置并填写密钥：

```bat
copy backend\.env.example backend\.env
```

编辑 `backend/.env`：

```ini
LAW_LLM_API_KEY=你的密钥
LAW_LLM_BASE_URL=https://api.deepseek.com
LAW_LLM_MODEL=deepseek-flash
```

分别启动后端和前端：

```bat
scripts\start-backend.bat
scripts\start-frontend.bat
```

打开 `http://127.0.0.1:5173`。后端接口文档位于 `http://127.0.0.1:8000/docs`。

停止项目：

```bat
scripts\stop-project.bat
```

停止服务并清理虚拟环境、前端依赖和构建缓存：

```bat
scripts\stop-and-clean.bat
```

该清理脚本保留源码、`backend/.env`、原始模板、数据库和生成合同。

## Docker 启动

复制 `backend/.env.example` 为 `backend/.env`，填写密钥后执行：

```bash
docker compose up --build -d
```

默认入口为 `http://127.0.0.1:8080`。

## 配置安全

- 密钥只写入 `backend/.env`。
- `.env` 已被 Git 忽略。
- 前端 `VITE_` 变量会进入浏览器构建产物，禁止存放模型密钥。
- 日志保存步骤、状态、计数和简短摘要，不保存密钥、完整提示词或模型响应正文。

## 项目目录

```text
ContractWeaver/
├─ backend/       FastAPI、Agent、检索、DOCX 引擎与测试
├─ frontend/      Vue 应用与前端测试
├─ docs/          中英文完整指南
├─ examples/      虚构会议纪要
├─ scripts/       安装、启动、检查和停止脚本
└─ compose.yaml   容器编排
```

历史工程记录与截图保存在已被 Git 忽略的 `local-notes/`，日常阅读从下面三个入口开始。

## 文档与示例

推荐阅读顺序：

1. 本 README：了解项目与快速启动。
2. [中文完整指南](docs/guide.zh-CN.md)：使用流程、架构图、配置、部署、排障与测试。
3. [Agent/Harness 源码阅读顺序](docs/code-reading-guide.zh-CN.md)：专注后端 Agent 与运行框架的实现。

[English guide](docs/guide.en.md) 是完整指南的英文版本，可按语言偏好选择。实际体验时使用以下示例：

- [保管合同会议纪要](examples/meeting-minutes-custody.md)
- [工业品买卖会议纪要](examples/meeting-minutes-equipment-purchase.md)

## 使用边界

模型输出属于待审核候选。生成合同前，请核对当事人、金额、日期、违约责任、争议解决、附件和签章信息。文字预览无法替代 Word 页面检查，涉及正式签署时还应完成业务、财务和法律审核。

当前版本面向本地开发和演示。生产部署还需补充 HTTPS、访问控制、备份、监控、限流和真实数据评测。
