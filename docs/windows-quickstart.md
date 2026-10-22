# Windows 11：从零启动、体验与彻底停止

无需 Docker。以下命令在 PowerShell 中执行；不要在 Python 的 `>>>` 提示符里执行。

## 1. 准备软件

安装 Python 3.11+ 和 Node.js 20+；本地已实测 Python 3.13 与 Node.js 24，建议新手选择这两个版本系列的受支持更新版，不要新装已结束支持的 Node.js 20。安装来源：[Python Windows 官网](https://www.python.org/downloads/windows/)、[Node.js LTS 官网](https://nodejs.org/en/download)。Windows 安装 Python 时勾选加入 PATH。安装完成后重新打开 PowerShell，检查：

```powershell
python --version
node --version
npm.cmd --version
```

如果提示找不到命令，先修复软件安装或 PATH，再继续。脚本不需要管理员权限，不会替你安装系统级软件。

## 2. 初始化项目

进入含 `backend`、`frontend`、`scripts` 的项目根目录，路径换成你实际的位置：

```powershell
cd 'D:\Projects\ProjectsByPowderblueX\ContractWeaver'
.\scripts\setup.bat
```

等待出现 `Setup complete`。首次需要联网下载依赖。脚本只在 `.env` 不存在时复制示例，不覆盖已有密钥；Python 依赖装在项目内 `.venv`，npm 使用项目内 `.npm-cache`，不要求全局安装项目依赖。

## 3. 配置密钥

```powershell
notepad .\backend\.env
```

只需先填写 `LAW_LLM_API_KEY=你的密钥`，默认地址 `https://api.deepseek.com`、模型 `deepseek-flash` 可保持不变。保存文件；不要误存成 `.env.txt`。配置和密钥不应上传 GitHub。没有密钥也能启动和人工填写，不能自动分析/提取。

## 4. 分别启动

第一个 PowerShell，位于项目根目录：

```powershell
.\scripts\start-backend.bat
```

第二个 PowerShell，同样进入项目根目录：

```powershell
.\scripts\start-frontend.bat
```

两个终端保持打开。浏览器访问 `http://localhost:5173`；API 文档为 `http://127.0.0.1:8000/docs`。若窗口立即退出，请从已打开的 PowerShell 运行脚本，以便看到错误；先检查端口占用和依赖是否安装。不要为了启动项目而关闭所有 Python/Node 进程。

## 5. 使用示例会议纪要

注册、登录、新建合同任务，上传 `examples/meeting-minutes-custody.md`（保管合同会议纪要），或复制其全部内容到输入框。按“分析 → 查看并选择模板 → 提取与复核 → 人工纠正/补充/确认 → 预览 → 生成”操作。纪要不完整时可一键暂留空，再补充完善；操作说明见 `examples/README.md`。

这份虚构纪要包含明确点名的合同、作废报价、最终价格、信息缺失和未达成一致的事项。对照 [examples/README.md](../examples/README.md) 验证表现。不要把示例直接用于真实签约，模型请求可能产生费用。

## 6. 关闭项目

先保存当前审核内容，不要在生成文件或提交审核时关闭。打开第三个 PowerShell，进入项目根目录后任选一种：

### 日常关闭：停止进程、清除临时缓存

```powershell
.\scripts\stop-project.bat
```

停止能按本项目路径确认的后端、前端、启动器及其子进程，复查进程是否退出，然后清理 Vite、项目内 npm、Python 源码等运行缓存。保留依赖目录，下次可直接启动两端。

### 停止并清理环境：适合不希望保留运行环境时

```powershell
.\scripts\stop-and-clean.bat
```

也可直接双击 `scripts/stop-and-clean.bat`。它调用同一停止逻辑，并额外删除 `backend/.venv`、`frontend/node_modules`、`frontend/dist`。下次需要重新运行 `setup.bat`。脚本可重复运行；发现进程未退出、权限不足或目录包含符号链接/联接点时会报错，不会把未清理成功说成成功。

两种关闭都保留：源码、原始模板、`backend/.env`、`backend/data/` 中的账号/任务/生成合同、你另行下载的文件。这些是应保留的数据，不是垃圾文件。不会删除数据库 WAL/日志文件来冒充清理，不会卸载 Python/Node，也不会误杀其他项目或浏览器。

Windows、浏览器和共享的 pip/npm/uv 缓存不属于本项目可安全独占清理的范围；不能承诺整台电脑绝对“零磁盘痕迹”。脚本只清理本项目明确归属的进程和可重建文件。自定义外部服务、Docker、非标准启动方式或指向外部目录的资源不在该 Windows 本地脚本的自动管理范围内；当前脚本针对本仓库提供的启动入口。

关闭会中止正在进行的请求；尚未保存的页面修改可能丢失，已发送给服务商的模型请求仍可能计费。停止后刷新网页不可用是正常现象，网页标签本身可手动关闭；SQLite 中已经保存的任务仍保留。

## 7. 关闭结果怎么判断

脚本成功退出时会显示已核验没有识别出的项目服务/启动器/子进程，以及保留数据范围。不要只凭关闭浏览器判断服务已经停止。若停止脚本提示权限不足，先检查是否曾以管理员身份启动了服务；需要使用相同权限停止，而不是全局结束所有 Python/Node。

这组入口已在 Windows 上实际验证：两端启动及代理正常，停止后测试端口释放，项目启动器/服务子进程退出，依赖和缓存删除，已有 `.env` 保持不变；单独启动的无关 Node 进程不受影响。Linux/macOS 与 Docker 的支持、验收边界见 [deployment.md](deployment.md)。
