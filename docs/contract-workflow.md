# 合同工作流与 API 契约

API 前缀为 `/api/v1`，除健康检查、登录和注册外，都需要 `Authorization: Bearer <token>`。模型密钥只从后端环境读取，不出现在浏览器请求中。

| 方法与路径 | 输入 | 结果 |
| --- | --- | --- |
| `GET /health` | 无 | 缺失模型配置名、模型标识、输入限制，不调用模型 |
| `POST /auth/register` / `POST /auth/login` / `POST /auth/logout` | 账户信息或登录令牌 | 注册、登录或注销 |
| `POST /sources/parse` | multipart `file`，TXT/MD/DOCX | 提取的文本与文件名，不保存原始文件 |
| `POST /workspaces` | `title, source_name, source_text` | 保存原文，返回合同任务 |
| `GET /workspaces` / `GET /workspaces/{id}` | 登录用户 | 自己的任务列表或完整任务 |
| `GET /workspaces/{id}/activity` | 登录用户且拥有任务 | 当前操作状态、实际 HTTP 次数、每批进展；无实时状态则返回已保存摘要或 idle |
| `PATCH /workspaces/{id}` | `revision, title` | 修改任务名称 |
| `DELETE /workspaces/{id}` | 登录用户 | 删除任务及其生成文件 |
| `POST /workspaces/{id}/analyze` | `revision` | 记录分析结果与候选模板 |
| `GET /contracts/templates` | `query, group, offset, limit` | 完整模板库分页；不使用 Agent |
| `GET /contracts/templates/{template_id}` | 模板 ID | 原文内容预览、实际字段及上下文 |
| `GET /contracts/templates/{template_id}/download` | 模板 ID | 原始 DOCX |
| `POST /workspaces/{id}/template` | `revision, template_id` | 用户锁定模板与字段列表 |
| `POST /workspaces/{id}/extract` | `revision, replace_reviewed?, retry_failed?` | 分批提取和独立复核，返回字段及失败批次 |
| `PATCH /workspaces/{id}/fields` | `revision, decisions[]` | 保存人工审核、修改、补充或明确留空 |
| `GET /workspaces/{id}/preview` | 任务 ID | 当前版本的已确认内容预览 |
| `POST /workspaces/{id}/generate` | `revision, preview_acknowledged, visual_review_acknowledged?` | 按人工确认值生成 DOCX 并保存版本 |
| `GET /contracts/{contract_id}/download` | 文件 ID | 仅所有者可下载 |

## 字段审核

注册请求为 `email, password`；登录同样为 `email, password`，公开用户信息仅含 ID 与邮箱。旧账户使用原邮箱登录，不要求重建账号。用户名不再作为输入或返回字段。

任务新增 `last_run`，字段新增 `display_name, section, kind`，均有兼容默认值。短编号仅在 Agent 输入/输出之间映射，原有持久化字段名和审核 API 的 `name` 不变。预览新增 `pending_count` 及段落/表格 `blocks`；界面在审核完成前不展示内部标识构成的半成品。空白表格列保留，防止填充值错列展示。

分析结果新增 `requested_templates[]`，每项为原名 `name` 与 `evidence={line_number, quote}`；引用或名称不在对应原文时不用于精确置顶。模板推荐返回 `explicitly_requested` 和 `fillable`。明确点名但不可填写的原件允许出现在推荐中，界面禁用选择但保留查看/下载入口，服务端选择校验不变。

`decisions` 中每项包含 `name`、`action`、`value`、`note`。`action=confirm` 必须提供非空值；`action=omit` 必须提供留空原因 `note`，并清空填写值。自动识别的字段在导出时恢复原始空白；原件已有显式占位符则保留原标记。未知字段和重复字段会被拒绝。

模板详情额外返回 `fillable`、`generated_slots`、`unsupported_structures`、`requires_visual_review`、`warnings`、`schema_fingerprint`。`fillable=false` 表示禁止进入自动填写，不影响原件下载。检测规则及已知缺口见[模板引擎说明](template-engine.md)。`preview_acknowledged=true` 表示用户已对照原件核对填写范围、未识别空白与选项，并确认当前版本预览，不只是看过文字预览。若 `requires_visual_review=true`，生成还必须单独提供 `visual_review_acknowledged=true`，否则返回 400；表示已检查图片/图形区域无需自动填写，并会核对导出版面。该确认随生成快照保存，不能绕过结构硬拦截。

字段状态：`extracted` 待人工核对、`missing` 未提取到、`conflict` 存在分歧、`unverified` 依据待核验、`confirmed` 用户已确认、`omitted` 用户明确留空。独立复核不会自动确认任何字段。用户修改后仍保留 `extracted_value`、原文 `evidence` 和 `review_issues`；`value_origin` 标识人工确认或人工修改。

引用以 `line_number` 与 `quote` 记录，行号以任务中保存的标准化原文为准。服务器检查引用是否逐字存在于指定行；错误引用被移除，相应填写值不能自动视为可靠。

## 修订和恢复

所有状态修改要求调用方提交任务当前的 `revision`，成功后返回新版本。过期修改返回 409；前端保留本地内容并提示重新打开任务。用户选定模板后，重新分析不能替换它；更换模板必须再次明确选择，会重置字段审核。模板内容和填写引擎版本均使用 SHA-256 指纹锁定，变化返回 409；没有引擎指纹的旧任务也须重新选模板。

结构化模型格式错误仅做有限重试；模型认证、连接和限流失败不进行无上限重试。提取按批汇总：完成的批次保留，失败批次列入 `extraction_failures`，可通过 `retry_failed=true` 只重试尚未人工审核的失败字段。重新提取全部字段时，已有人工结果需要 `replace_reviewed=true`。浏览器关闭或服务重启后可重新打开已保存任务；当前版本尚无分布式任务队列和实时任务推送。

已有每秒轮询的单进程实时进度观察，不是 WebSocket 推送或持久化后台执行。状态有界存放于内存，完成摘要保存到任务；进程重启会丢失未完成的实时状态。请求计数来自模型传输层，不根据配置标志或 Agent 文本估算，不保存密钥、提示词或响应正文。具体用户解释见 [使用引导](user-guide.md)。

生成要求所有字段都已确认或明确留空，且至少有一个非空填写值；调用必须确认当前版本预览。生成文件使用不可预测 ID，文件归属与任务更新在同一数据库事务保存；版本冲突时清理本次未登记文件。各次生成的文件保存独立快照，修改字段不会改变以前的文件。
