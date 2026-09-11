# AgentLink 0.3.14：B 节点沙盒启动失败

日期：2026-09-11。基于 0.3.13，保留原源码、场次、共享清单、权限及登录配置。

## 问题证据

B 截图：thread/start 在加载环境指令时失败，底层为 orchestrator_helper_launch_failed，helper=codex-windows-sandbox-setup.exe，error=program not found。截图的 cwd 是工作目录，不是要求在该目录放置 exe；manifest.json 是源码清单，.manifest.json.io.lock 是文件读写锁，不应删除。

已读取用户共享的 manifest.json：49 个源码文件的 SHA-256 与交付 0.3.13 全部一致。此检查证明清单匹配，不证明 B 已独立读取所有文件。用户确认 B 为正常安装的 Codex 桌面版。

本机隔离目录仅复制同版 codex.exe、去掉继承的 Codex PATH 后，真实接口复现了截图中的同一 program not found 错误。因此修复覆盖两条路径：组件实际缺失、组件没有进入子进程查找路径。B 本机的具体缺件与路径状态须由诊断工具确认。

## 修改

- 子进程 PATH 首位设为当前选择的 Codex 所在目录，不修改系统/用户 PATH。
- 检查 codex-windows-sandbox-setup.exe、codex-command-runner.exe、codex-code-mode-host.exe；缺件时在项目 thread/start 前给出目录和名称。
- 节点连接时发布组件检查状态；新版本在创建项目场次前检查已知的双方缺件，避免 A 先耗费请求才发现 B 无法执行。旧节点没有该检查字段，因此建议两端都更新。此检查不是完整的沙盒可用性验收。
- 提供 Repair-CodexRuntime.cmd 和 source/packaging/Repair-CodexRuntime.ps1。只从当前用户已安装的 OpenAI.Codex 包 app/resources 取文件，先比对完整 codex.exe SHA-256；不匹配拒绝复制。替换已有异版辅助文件前备份，并逐文件校验。
- 不联网下载、不复制账号数据、不修改 Codex 权限配置、不自动提升审批、不自动重发失败场次。

## B 端使用

1. 关闭 B 的 AgentLink；解压 0.3.14 ZIP。
2. 双击解压目录根部 Repair-CodexRuntime.cmd。窗口显示每个辅助文件是否存在及诊断 result.json 的保存路径。
3. 如果显示 components_present，启动同目录 AgentLink.exe；A 也使用本版，新建讨论后重试。若仍报错误，提供诊断 result.json 及新的完整错误。
4. 如果提示没有 SHA-256 匹配的完整安装包：工具不会混用版本。先更新/修复 B 本机 Codex 桌面安装，再在 AgentLink 设置选择该安装的当前 codex.exe，重新运行修复工具。
5. 审查对象仍可使用 0.3.13 的 source；不要把沙盒组件放入被审查源码或共享快照。

CMD 仅为本次 PowerShell 子进程使用 Bypass 执行策略，以便运行随包检查脚本，不永久修改系统执行策略。也可手动执行 PowerShell 脚本；不带 -Repair 时仅诊断。

## 验证

- 39 项单元测试通过：组件 6、MCP 4、路径发现 5、项目 13、流程 6、执行归属 5。
- 项目 GUI 与原文字 GUI 两个脚本通过。
- 真实修复对照：缺组件时复现 B 的 helper program not found；用匹配安装包补齐组件后，A 实施/B 只读审查/A 总结三种 thread/start 权限确认均通过，PATH 仍为受控的最小继承环境。
- 修复工具不匹配哈希用例通过：退出码 1，不复制辅助文件。
- 所有真实探测禁止 turn/start，本次模型请求数 0。未在 B 电脑执行修复或测试，不宣称双机审查已通过。

证据目录：C:\AgentLink-hotfix-0.3.14\evidence。
官方 Windows 沙盒说明：https://learn.chatgpt.com/docs/windows/windows-sandbox
