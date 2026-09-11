# AgentLink 0.3.12 热修复记录

日期：2026-09-11。基于交付的 0.3.11 源码创建，未修改旧包、原源码或用户 Codex 配置。

## 问题和修改

0.3.11 把 TOML 风格带引号的 MCP 名称放入 JSON 配置路径，例如 mcp_servers."node_repl".enabled。真实 App Server 将其视为另一个没有 transport 的配置项，在 thread/start 加载配置时失败。0.3.12 使用嵌套 JSON 对象保留名称和已有 command/url 等传输配置，仅将 enabled 设为 false；插件同样处理。非法配置形状会在 thread/start 前拒绝。

## 当前验证

- 27 项单元测试通过：MCP 配置 3、项目 13、流程 6、执行归属 5。
- 项目 GUI 与原文字 GUI 两个脚本通过。
- 真实 App Server 对照：旧的带引号键复现截图错误；新对象配置通过解析，随后被 Windows 沙盒拒绝。
- 两个真实探测均未发送 turn/start，模型请求数 0。探测使用进程内禁用的 node_repl 配置，未修改账号配置。
- 新错误：windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed。
- 项目权限预检仍阻塞；真实双机、B 独立测试和完整审查流程未通过验收。

## 使用与剩余环境设置

1. 关闭 A/B 旧 AgentLink，分别解压本版并运行 AgentLink.exe。共享通信目录、项目和历史使用原设置。
2. 若审查的是 0.3.11，A 源码目录继续选 C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.11\source；运行程序可用 0.3.12，审查对象仍是原 0.3.11。
3. 本机现用 unelevated 沙盒不支持此读取隔离。两端需要分别完成 Codex 原生 elevated 沙盒设置，然后重新验证。此模式使用低权限专用用户及文件边界，安装过程需要管理员确认；不是将项目设为完全访问。
4. 官方配置为 config.toml 中 [windows] 下 sandbox = "elevated"。已有 [windows] 段时修改其 sandbox 值，不重复增加段，不覆盖其它配置；在 Codex 中完成原生沙盒设置的管理员提示，再重启 AgentLink。仅改配置值不代表初始化成功。若系统策略不允许安装，保持阻塞，不改成全盘访问。
5. 失败场次保留作证据。点击“新建讨论”，选原项目并重新填写议题。

官方说明：https://learn.chatgpt.com/docs/windows/windows-sandbox

本机证据：C:\AgentLink-hotfix-0.3.12\evidence。27 项是本次复测，0.3.11 的历史 109 项没有在本次全部重跑。
