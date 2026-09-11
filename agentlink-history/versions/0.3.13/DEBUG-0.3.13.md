# AgentLink 0.3.13 修复与验证

日期：2026-09-11。基于交付的 0.3.12；保留原包、项目源代码、用户权限及登录配置。

## 两个根因

1. 实际 settings.json 固定指向 OpenAI/Codex/bin/codex.exe，其版本为 0.130.0-alpha.5。该版本真实 config/read 复现 FilesystemPermissionToml 错误；当前桌面版本目录的 0.153.4 可读取同一配置。原测试使用自动发现路径，没有覆盖用户保存的旧入口，这是之前验证缺口。
2. 当前 config/read 的 node_repl.tool_timeout_sec 返回 null。0.3.12 将它原样送回 thread/start，JSON 到 TOML 转换后成为空字符串，报 expected f64。0.3.13 在回传前去除对象内的 null 字段，保留 false、0、空字符串和有效 transport 配置，继续禁用 MCP/插件。

## 修复行为

- Settings.load 对桌面管理的旧 bin/codex.exe 自动选择本机版本目录；已删除的受管理版本路径同样恢复。自动发现优先版本目录。
- 显式选择且仍存在的特定版本、自定义路径保持不变；无可用替代时保留原值并正常报错。该迁移只在内存中生效，未擅自改用户设置文件。
- 不放宽项目读写范围、审批、网络设置；不修改 Codex config.toml。

## 验证结果

- 33 项单元测试通过：MCP 配置 4、路径发现 5、项目 13、流程 6、执行归属 5。
- 项目 GUI 检查通过。
- 文字 GUI 首次检查失败：终态事件已到而异步历史列表尚未刷新，断言过早。测试增加有时限的历史刷新等待后通过；原失败日志保留，应用 UI 未因该测试修改。
- 真实接口：旧 0.130.0-alpha.5 复现 config/read 失败；0.3.12 配合 0.153.4 复现 tool_timeout_sec 类型错误；修复后 0.153.4 的 config/read、A 实施、B 审查、A 总结 thread/start 均通过，返回的权限名称/审批/cwd 与请求一致。
- 本机实际 settings.json 只读迁移检查通过，选择 0.153.4，磁盘文件未变。
- 所有真实探测均拦截 turn/start，模型请求数 0。会话创建与配置确认不能证明实际命令隔离、独立 B 测试或双机完整审查通过。

## 用户操作

1. 两端关闭旧程序，使用 0.3.13。A 端直接运行 C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.13\AgentLink.exe。B 端将 ZIP 解压到本机后运行。
2. 旧桌面入口会在加载设置时自动迁移到本机已安装版本。B 如果只有旧 Codex，先更新本机 Codex；不要照搬 A 的用户路径或版本目录名。
3. 本机当前 elevated 配置已通过会话预检，不需要再修改权限。B 环境须在 B 本机验证。
4. 审查 0.3.12 时保留项目目录 C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.12\source。运行版本与被审查源码版本可以不同。
5. 点击“新建讨论”，选择原项目并重新提交议题；不继续失败场次。

本轮未上传 GitHub、未修改 B 电脑、未启动真实模型测试。

证据：C:\AgentLink-hotfix-0.3.13\results.json、evidence/ 下回归日志及设置迁移记录。修复前对照：C:\AgentLink-diagnostics-20260911-runtime\results.json。
