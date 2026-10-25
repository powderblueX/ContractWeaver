# 契织：从零读懂整个项目的代码阅读顺序

不要按文件名字母顺序读，也不要第一天从 Word XML 细节开始。按“用户操作 → 状态 → 接口 → Agent/Harness → 文档与存储 → 前端状态 → 测试”逐层深入。每阶段读完都应能回答本节的问题；遇到复杂算法先记下调用关系，再回头读实现。

本文路径均相对仓库根目录，可点击进入。配套总图：[Agent + Harness 完整图解](agent-harness-guide.zh-CN.md)。代码采用的说明格式见 [注释规范](code-commenting.md)。

## 第一遍：先跑一条业务故事，不急着逐行解释

1. [README_zh-CN.md](../README_zh-CN.md)：产品目标、限制和配置位置。
2. [Windows 启停说明](windows-quickstart.md)：安装依赖、分别启动前后端、停止与可选清理。
3. [保管合同会议纪要](../examples/meeting-minutes-custody.md)及[人工检查清单](../examples/README.md)。
4. [用户引导](user-guide.md)：等待、批次进度、审核、一键暂留空和导出的含义。

观察：原文中哪些是共识、哪些仍未定？为什么不能把所有空白都填满？没有密钥时哪些操作仍能手动完成？

## 第二遍：按以下 10 个阶段阅读代码

### 1. 应用怎样启动和组装

依次读：

1. [backend/app/config.py](../backend/app/config.py)：环境变量、私有 `.env`、路径和预算的唯一入口。
2. [backend/app/main.py](../backend/app/main.py)：FastAPI、数据库初始化、CORS 与领域异常到 HTTP 的映射。
3. [backend/app/api/router.py](../backend/app/api/router.py)：API 前缀、子路由和公开健康状态。
4. [backend/app/api/workspace_dependencies.py](../backend/app/api/workspace_dependencies.py)：仓储、模板目录、检索策略和服务的依赖组装。
5. [frontend/src/main.js](../frontend/src/main.js) → [App.vue](../frontend/src/App.vue) → [router/index.js](../frontend/src/router/index.js)：Vue 挂载、页面过渡和导航守卫。

要能回答：模型密钥为什么不能放 `VITE_` 变量？应用启动时创建什么，生成合同时才创建什么？前端路由守卫为什么不能替代后端认证？

### 2. 先弄懂核心数据结构和状态

1. [domain/contract_workflow.py](../backend/app/domain/contract_workflow.py)：重点看 `SourceEvidence`、`SupervisorDecision`、`FieldStatus`、`ReviewedField`、`ContractWorkspace`。
2. [domain/errors.py](../backend/app/domain/errors.py)：哪些错误是输入问题、哪些是并发冲突或不可见资源。
3. [api/contract_requests.py](../backend/app/api/contract_requests.py)：客户端能提交哪些字段，哪些决定必须来自用户。

画出一份任务快照，并区分：原始纪要、模型候选、证据、用户备注、领域 stage、运行 status、revision、历史 artifact。不要把 extracted 当 confirmed，也不要把执行 completed 当合同 ready。

### 3. 沿着一次真实用户操作读接口

从 [api/workspace_routes.py](../backend/app/api/workspace_routes.py) 读六个入口：创建任务、分析、选模板、提取、保存审核、生成。

再到 [services/contract_workflow.py](../backend/app/services/contract_workflow.py)，第一遍只读这些方法的前置条件和保存出口：

`create` → `analyze` → `select_template` → `extract_fields` → `review_fields` → `preview` → `generate`。

暂时跳过提取方法内部的批次实现。先找出每个方法何时调用 `_load`、何时检查模板指纹、何时改变 stage、何时通过 repository.save 提交。注意 `analyze` / `extract_fields` 的装饰器：实际执行会先进入下一阶段的运行边界。

要能回答：用户直接跳过模型选模板是否允许？为什么重选模板要重置审核？用户在旧页面点击保存会发生什么？

### 4. 再读 Harness，而不是把它误当主控

1. [observability.py](../backend/app/observability.py)：`observed`、`OperationRegistry`、`finish_run`。
2. [agents/harness.py](../backend/app/agents/harness.py)：`current_run/current_step`、能力目录、请求预留、步骤执行和终态。
3. [repositories/agent_runs.py](../backend/app/repositories/agent_runs.py)：数据库租约、最近 20 次历史、过期与旧执行者防护。

对照 [运行时序图](../figures/harness-run-sequence.md)，从装饰器进入一次分析调用。理解“HTTP 前计数”和“领域提交后发布完成”的区别。

要能回答：ContextVar 如何让并发批次共享预算且不串用户？为什么内存进度不等于后台队列？租约与 CAS 修订各自防止什么？

### 5. 读主控及专业 Agent 的真正协同

建议严格按此顺序：

1. [agents/team.py](../backend/app/agents/team.py)：对象怎样创建，为什么共享配置不等于共享聊天历史。
2. [agents/prompts.py](../backend/app/agents/prompts.py)：共同边界及五角色任务规范，先看输入说明和输出契约。
3. [agents/supervisor.py](../backend/app/agents/supervisor.py)：动态 allowed_actions Schema、动作和参数匹配检查。
4. [agents/negotiation_coordinator.py](../backend/app/agents/negotiation_coordinator.py)：分析、检索、观察、改词再检索和交接。
5. [agents/record_analysis.py](../backend/app/agents/record_analysis.py)：意图与明确模板请求的提取。
6. [agents/field_mapping.py](../backend/app/agents/field_mapping.py)：`f001` 与内部定位名的批内映射。
7. [agents/field_extraction.py](../backend/app/agents/field_extraction.py)：首次提取和带复核反馈的定向修正。
8. [agents/candidate_validation.py](../backend/app/agents/candidate_validation.py)：证据、编号、类型与问题状态。
9. [agents/field_review.py](../backend/app/agents/field_review.py) → [field_coordinator.py](../backend/app/agents/field_coordinator.py)：复核如何驱动主控选择，以及修正结果何时可以合并。
10. [agents/contract_coverage.py](../backend/app/agents/contract_coverage.py)：批次之外的覆盖视野与上下文限制。
11. [model_client.py](../backend/app/model_client.py)：实际 HTTP、配置检查、预算、JSON Schema、截断检查和有限结构重试。

练习：假设首次提取把 9000 元旧报价当成最终金额，找出“复核指出 → 主控指定目标 → 修正 → 再次复核 → 仍等用户确认”的所有调用。再把账号改为原文没有，解释为什么不能靠重试把它补出来。

### 6. 模板检索：先读算法，再读目录的业务封装

1. [services/template_retrieval.py](../backend/app/services/template_retrieval.py)：分词 → BM25 → 多通道 RRF → 原名匹配/否定兜底。
2. [services/contract_templates.py](../backend/app/services/contract_templates.py)：先读 `refresh`、`get_template`、`list_templates`、`search_templates`，暂不读写入部分。
3. 回到 `NegotiationCoordinator` 看跨轮候选如何融合。

要能回答：默认哪些通道在运行？向量通道何时才启用？为什么不能直接相加 BM25 和向量的原始分数？为什么找到了指定原件也可能不允许自动填写？

### 7. Word 引擎：按“读取 → 编译 → 约束 → 写入”读

1. [documents/word_documents.py](../backend/app/documents/word_documents.py)：正文、表格、文本框及已有页眉页脚的遍历顺序。
2. [documents/word_text.py](../backend/app/documents/word_text.py)：文字原子、XML 叶节点和跨 run 的范围替换。
3. [documents/word_compatibility.py](../backend/app/documents/word_compatibility.py) 与 [template_safety.py](../backend/app/documents/template_safety.py)：新旧分支同步、复杂结构拦截和视觉复核。
4. [documents/slot_constraints.py](../backend/app/documents/slot_constraints.py)：日期分格、枚举、大写金额、有效日历日期。
5. [documents/template_slots.py](../backend/app/documents/template_slots.py)：从原始空白编译唯一位置，保存原空白，理解 `SLOT_ENGINE_VERSION`。
6. [documents/field_metadata.py](../backend/app/documents/field_metadata.py)：让机器定位具有可读的表格/业务上下文。
7. [documents/word_integrity.py](../backend/app/documents/word_integrity.py)：图形和媒体指纹为什么与文字校验分开。
8. 回到 `ContractTemplateCatalog.describe_template` → `preview_contract` → `generate_contract` → `_fill_paragraph`。

配套 [模板引擎说明](template-engine.md)。练习：把“大写金额空白后已有元”从扫描一路跟到候选“叁仟”和最终 XML，说明为什么不是直接把“叁仟元整”写进去。理解没有业务遗漏认证、没有 OCR、文字预览不等于版面。

### 8. 存储与认证：最后核对资源归属和事务

1. [database.py](../backend/app/database.py)：表之间的关系、外键、短事务及回滚。
2. [repositories/contract_workspaces.py](../backend/app/repositories/contract_workspaces.py)：CAS save、artifact 所有权、删除级联范围。
3. 复读 `repositories/agent_runs.py`，比较领域状态和执行日志的保存策略。
4. [security.py](../backend/app/security.py) → [repositories/accounts.py](../backend/app/repositories/accounts.py) → [services/accounts.py](../backend/app/services/accounts.py)：密码哈希、令牌哈希和有效期判断所在层。
5. [api/auth_requests.py](../backend/app/api/auth_requests.py)、[auth_routes.py](../backend/app/api/auth_routes.py)、[dependencies.py](../backend/app/api/dependencies.py)、[template_routes.py](../backend/app/api/template_routes.py)：请求验证和下载归属。

练习：换另一个账户调用某个任务、运行日志或下载接口，会在哪里被拒绝？不要在生产数据库上试删除；阅读对应隔离测试即可。

### 9. 前端：从数据状态到页面，再到组件

1. [shared/authSession.js](../frontend/src/shared/authSession.js) → [shared/httpClient.js](../frontend/src/shared/httpClient.js)：标签页会话、统一认证请求、错误和下载。
2. [features/contracts/contractApi.js](../frontend/src/features/contracts/contractApi.js)：把每个前端方法对应回第 3 阶段的 HTTP 接口。
3. [useContractWorkspace.js](../frontend/src/features/contracts/useContractWorkspace.js)：重点 `perform` / `mutate`、轮询、序号、取消、已提交状态与列表刷新分离。
4. [ContractWorkspacePage.vue](../frontend/src/features/contracts/ContractWorkspacePage.vue)：下一步引导、导航、离开未保存提醒、主控问题和页面操作。
5. 按业务顺序读 [SourceImportPanel](../frontend/src/features/contracts/components/SourceImportPanel.vue) → [TemplateLibrary](../frontend/src/features/contracts/components/TemplateLibrary.vue) → [FieldReviewPanel](../frontend/src/features/contracts/components/FieldReviewPanel.vue) → [ContractPreviewPanel](../frontend/src/features/contracts/components/ContractPreviewPanel.vue)。
6. [OperationProgress.vue](../frontend/src/features/contracts/components/OperationProgress.vue) 与 [fieldPresentation.js](../frontend/src/features/contracts/fieldPresentation.js)：真实进度和机器定位的可读化。
7. [AuthPage.vue](../frontend/src/features/auth/AuthPage.vue)：邮箱认证表单与等待保护。
8. 最后读 [shared/style.css](../frontend/src/shared/style.css)、[workspace.css](../frontend/src/features/contracts/workspace.css)、[experience.css](../frontend/src/features/contracts/experience.css)：公共尺度、页面骨架和体验修正的归属。

练习：第一页改一个字段但不保存，去第二页，再确认另一个字段。解释本地 drafts、服务器 fields、savingNames、operationSequence 各防什么问题；不要把页面切换当作后端状态转换。

### 10. 测试、脚本、部署和维护

按你刚读的代码，交叉阅读对应测试：

| 内容 | 优先测试 |
| --- | --- |
| 主控选择和修正闭环 | [test_agent_coordination.py](../backend/tests/test_agent_coordination.py) |
| 预算、租约、轨迹和隔离 | [test_agent_harness.py](../backend/tests/test_agent_harness.py) |
| 任务到真实 DOCX | [test_contract_workflow.py](../backend/tests/test_contract_workflow.py) |
| Prompt、字段编号与 HTTP | [test_agent_prompts.py](../backend/tests/test_agent_prompts.py)、[test_operation_experience.py](../backend/tests/test_operation_experience.py)、[test_model_configuration.py](../backend/tests/test_model_configuration.py) |
| Word 支持边界 | [test_template_slots.py](../backend/tests/test_template_slots.py)、[test_custody_mapping.py](../backend/tests/test_custody_mapping.py) |
| 检索融合 | [test_template_retrieval.py](../backend/tests/test_template_retrieval.py) |
| 前端完整操作和局部状态 | `frontend/src/features/contracts/__tests__/` 与认证目录测试 |
| 脚本/容器/注释 | `backend/tests/test_windows_scripts.py`、`test_container_entrypoint.py`、`test_comment_coverage.py` |

随后阅读：

- `scripts/setup.*` → `start-backend.*` / `start-frontend.*` → `stop-project.*` / `stop-and-clean.bat`：只初始化缺失配置、明确进程归属、精确清理范围。
- `scripts/windows-project-processes.ps1`：先理解强识别和路径防护，再读停止脚本；不能用端口或所有 node/python 进程作为删除/停止依据。
- `scripts/check.ps1`、`frontend/scripts/check-comments.mjs`、`backend/app/cli/check_comments.py`：格式/注释/功能验证入口。
- `frontend/scripts/check-layout.mjs`：使用模拟 API 的真实浏览器几何检查，不连接真实 LLM。
- `backend/app/cli/audit_templates.py`：只做内存结构往返；`cli/check_llm.py` 是明确选择才运行的真实付费连通检查，别把它当离线测试。
- `backend/app/container_entrypoint.py`、两端 Dockerfile、`frontend/nginx.conf`、`compose.yaml`：容器配置、代理及持久卷。
- `backend/app/migrate_legacy.py`：旧用户与聊天记录迁移工具，不是新任务日常执行入口，运行前先备份。
- [deployment.md](deployment.md)、[maintenance.md](maintenance.md)、[validation.md](validation.md)：部署、维护与已经/尚未验证的事实。
- 各层 `__init__.py` 是包边界；`package.json`、锁文件、requirements 和 Vite/Vitest 配置用于依赖与运行组装，不包含模型密钥。

## 最后，用五个问题自测是否真正读懂

1. “模型调用成功”到“用户可导出”之间有哪些独立关卡？
2. 模型怎样选择下一动作，而协调器怎样阻止非法动作和无关字段修正？
3. 如果原文引用确实存在，为什么字段仍可能错误？
4. 原始 Word 没有人造占位符，程序怎样建立位置并保护格式？
5. 关闭浏览器、取消轮询、后端崩溃、修订冲突分别意味着什么？

能用一个保管合同例子逐层回答，比背诵文件名更重要。下一步改代码时，先找到这一层的职责及对应测试，再改最小范围；不要通过修改提示词去绕过代码审批，也不要通过改前端按钮去绕过后端状态检查。
