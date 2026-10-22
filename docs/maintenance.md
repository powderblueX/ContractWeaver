# 配置、数据与资源维护

## 配置与数据保留

模型配置在 `backend/.env`，示例为 `backend/.env.example`。DeepSeek Flash 的地址与模型名已预设，密钥只需填入该文件的 `LAW_LLM_API_KEY`，不输出到日志或聊天。为保持现有部署兼容，配置名继续使用 `LAW_` 前缀；它不是产品版本号，也不需要因为展示名称改变而重新申请 API Key。完整步骤见[部署说明](deployment.md)。

新安装默认数据库为 `backend/data/contractweaver.db`。如果已有 `backend/data/lawreasoner.db` 且新数据库尚不存在，仍使用已有数据库；没有自动删除或改名。`LAW_DATABASE_PATH` 可显式指定目标路径。若曾配置旧目录的绝对路径，需自行更新；相对路径按后端目录解析。

`backend/data/legacy_shared_db.db` 是保留的历史数据库备份，已有迁移工具 `python -m app.migrate_legacy` 用于空库导入。不要为整理目录而删除数据库或历史生成合同。已有字段映射不跨模板引擎变化复用，需重新选择模板审核。

浏览器会话使用新的 `contractweaver.session` 键；曾登录旧名称应用的用户需要重新登录，服务端用户和合同记录不受影响。

## 合同资源

```text
backend/resources/contracts/
  templates/                    原始 DOCX、来源分类和业务关键词
  indexes/                      可选的本地检索索引
```

运行时只从 `templates/` 发现合同，关键词同样从该目录读取；可选向量检索使用 `indexes/`。旧 `legacy/placeholder-templates/` 及其无用说明已按所有者要求清理：1134 个 DOCX/JSON 删除前均与 Git 历史一致，可从历史恢复。原始 DOCX、业务关键词、索引、数据库和历史生成文件均未删除。

目录整理本身不会提升安全覆盖率。本轮文档引擎已增加文字节点保留写入、文本框扫描和相同兼容分支同步，图形不再一律拦截；最新整库统计见[验证记录](validation.md)。模板或引擎变动需重新运行 `python -m app.cli.audit_templates --summary --progress`，并完成业务与版面验收。旧任务必须重新选择模板，不能复用旧引擎字段映射。

## 验证

安装 `backend/requirements-dev.txt` 和前端依赖后，从根目录运行 `./scripts/check.ps1`。可通过 `-BackendPython` 指定已安装依赖的 Python；`-SkipFrontend` 只运行后端检查。脚本不会安装依赖或调用真实 LLM。单项命令见 README。只有手工执行 `python -m app.cli.check_llm` 或界面分析/提取操作会调用真实模型；连通性探针仅发送合成测试内容，不读取合同任务。

运行环境、`.env`、数据库、生成文件、缓存和构建产物不应提交。准备公开仓库前，还需确认历史密钥已轮换、模板及检索资源的许可证与来源满足公开分发要求；新项目名称不等于重新获得资源授权。本轮没有擅自添加覆盖这些资源的开源许可证。
