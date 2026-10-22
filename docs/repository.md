# 项目与 GitHub 仓库命名

项目展示名、本地目录和 GitHub 仓库名统一使用 **ContractWeaver** 即可，不要求改成小写连字符。

名称表达从协商记录组织合同内容的工作流，不暗示无人审核的法律服务，也不将项目绑定到某个 LLM 或编排框架。名称是建议，未声明全网独占，最终以账号下可用名称为准。

## 推荐重命名现有仓库

建议将现有 `powderblueX/LawReasoner` 重命名为 `powderblueX/ContractWeaver`。产品可以有新的定位与初始开发版本，不必因此重建 Git 仓库或清空历史。保留已有来源、提交和协作记录更合适。

仓库所有者可在 GitHub 的 Settings → General → Repository name 中修改。修改完成后，在本地运行：

```powershell
git remote set-url origin https://github.com/powderblueX/ContractWeaver.git
git remote -v
```

上述命令仅供仓库重命名完成后执行，本次本地重构没有操作 GitHub、修改 `origin`、创建标签或推送代码。目录重命名保留了当前未提交工作。

GitHub 会为多数旧仓库地址提供重定向，但项目站点和作为 Action 被引用的地址存在例外，应按[GitHub 官方说明](https://docs.github.com/en/repositories/creating-and-managing-repositories/renaming-a-repository)检查。不要在改名后重新占用旧仓库名而依赖旧地址始终重定向。

如果希望旧项目继续作为独立产品维护，才更适合另建仓库；这与本次“聚焦合同填写的新定位”不是同一决定。无论选择哪种方式，都应保留资源来源与必要授权，不应以新名字规避旧密钥的撤销或资源许可检查。

## 本地根目录

当前工作区根目录已由所有者改为 `ContractWeaver`。应用路径按后端目录解析，不绑定旧绝对目录；如曾自定义绝对路径，应检查 `.env` 的资源和数据位置。内部目录统一为 `backend/`、`frontend/`、`docs/`、`scripts/`。

本项目没有使用新的“升级版”标签。版本 `0.1.0` 表示初始开发阶段，并不承诺全库模板或真实模型已经验收。

GitHub About 描述可使用：`Human-reviewed multi-agent contract filling from negotiation records.` 建议主题：`multi-agent`、`llm`、`contract-automation`、`fastapi`、`vue`。
