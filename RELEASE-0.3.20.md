# AgentLink GUI 0.3.20 交付报告

封装时间：2026-09-13T04:09:37.309207+08:00。基线：0.3.19。用户授权：按已确认九项修复策略实施并发行 0.3.20。

结论：**九项代码修复及本机回归已完成；便携版本地发行。FULL_ACCEPTANCE=false。** 真实双机、真实 SMB、真实模型、独立 B 复核尚未执行；当前 Codex 运行环境无法建立所需权限隔离，真实权限预检阻塞；GitHub 返回 Forbidden，未完成远端发行。

受测开发源码：C:\AgentLink-release-0.3.20\source。只读受测副本：C:\AgentLink-release-0.3.20\readonly-parent\source。代码实现提交：7f8ffa2d9e394db9398f172f2e4dc449923c7708。最终来源清单及应用源码哈希在验证证据包 source-manifest.json / final-checks.json，外部 VERIFICATION-0.3.20.json 记录最终源码提交及 ZIP 哈希。

0.3.19 原始 source 的 92 个文件保持不变；原审查快照和历史发行物保留。没有删除业务功能；新增执行能力要求双方 0.3.20，旧端在正式执行前被拒绝。

## 逐项变化与验证

| 编号 | 最终行为 | 实际证据边界 |
|---|---|---|
| A01 | 创建未提交前不调度；持久创建意图与可证明未发送的残留收敛 | 写入切点、真实子进程退出/新服务实例、ready 门禁通过 |
| A02 | 最终关联复核停止/暂停；发送管道写入与停止提交互斥 | 停止、暂停、旧启动回调、发送前停止通过 |
| A03 | 集中 discuss/review/edit 阶段权限；讨论的 B 测试目录只读 | 配置和工作流回归通过；实际 Codex 工具权限预检阻塞 |
| A06 | 统一扩展路径 I/O/枚举，保存普通路径表示兼容配置 | 259/260/262/320 字符、中文、对话发现和快照收发通过；真实 UNC 未执行 |
| B03 | 候选文本无副作用；请求账本一次记录消息集合，三条请求路径统一提交 | 预算阻塞、账本失败、消息变化、uncertain/delivered、定向恢复通过 |
| A05 | 按真实步骤/执行方查请求；无证据返回 UNKNOWN | 对端 interrupted_uncertain 与缺少执行方回归通过 |
| A04 | 成功清理本次临时包；失败保留有界诊断并回收重复字节 | 成功、校验失败、长路径及清理拒绝回归通过 |
| B01 | 所有当前测试输出使用外部根；延迟解析默认临时目录；增加越界写入守卫 | 源码及父目录实际拒绝写入，38 个标准脚本通过，前后哈希一致 |
| B02 | 标题引用统一版本；C# 模板由版本源生成；启动器使用 -B | 最终 EXE Win32 标题为 0.3.20，文件/产品版本为 0.3.20.0 |

## 验证汇总

- 只读源码完整回归：**38/38 个脚本通过，219 次 unittest 用例执行**。源和父目录由 Windows ACL 拒绝写入，读取允许；源码前后哈希一致。
- 包内 Python/Qt：**9/9 个脚本通过，68 次 unittest 用例执行**。这是重复验证，不与 219 相加宣称唯一用例数。脚本内 subTest 也不另充唯一测试数。
- 创建崩溃：真实子进程在 context 写入前及 ready/state 写入后 os._exit(73)，新服务实例恢复；两项均通过，claim=0、模型请求=0。
- 最终 AgentLink.exe：隔离用户数据启动、读取 Win32 标题、正常关闭及拥有的子进程树清理通过；标题为 AgentLink 0.3.20 · 双机协作，FileVersion/ProductVersion 均为 0.3.20.0。
- 发行运行时：Python 3.13.13 x64、PyQt5 5.15.11、Qt 5.15.2。GUI 使用原生 Windows Qt 平台插件验证。
- 离线用例均使用本机模拟进程；真实模型 turn/start **0 次**。实际权限预检尝试 3 个 thread/start（总结/审查/实施），均在 Windows sandbox 准备阶段被拒绝，未发送模型请求。
- 最终应用源码与只读受测副本、包内 app 逐字节一致。完整 source 另包含发行报告/开发日志，以及单独执行的 check_creation_crash.py；这些新增交付材料不伪称在先前只读副本中执行过。

实际命令及逐脚本结果：

```text
python -B C:\AgentLink-release-0.3.20\readonly-parent\source\tests\run_release_checks.py --out C:\AL20-verified --timeout 240
<包内 runtime/python.exe> -B <包内 source/tests/run_release_checks.py> --out C:\AL20-package-verified --names test_upgrade020.py test_peer_recovery.py test_context_resume_guard.py test_review_fix_integration.py test_conversation_guards.py test_storage.py test_projects.py test_windows_startup.py test_runtime_discovery.py --timeout 240
python -B tests/check_creation_crash.py --out C:\AgentLink-release-0.3.20\evidence\process-crash
python -B C:\AgentLink-release-0.3.20\verify_native_package.py C:\AgentLink-release-0.3.20\evidence\native-final
python -B packaging/build.py --zip-only
```

| 标准脚本 | 状态 | unittest 执行数 |
|---|---|---:|
| test_authority.py | 通过 | 5 |
| test_cleanup_admission.py | 通过 | 2 |
| test_cleanup_failures.py | 通过 | 4 |
| test_code_gui.py | 通过 | 0 |
| test_code_workflow.py | 通过 | 6 |
| test_context.py | 通过 | 8 |
| test_context_resume_guard.py | 通过 | 1 |
| test_context_ui.py | 通过 | 1 |
| test_context_view.py | 通过 | 6 |
| test_context_workflow.py | 通过 | 7 |
| test_conversation.py | 通过 | 14 |
| test_conversation_guards.py | 通过 | 8 |
| test_failure_recovery.py | 通过 | 1 |
| test_faults.py | 通过 | 8 |
| test_freshness.py | 通过 | 7 |
| test_gaps.py | 通过 | 6 |
| test_gui.py | 通过 | 0 |
| test_integration_upgrade.py | 通过 | 6 |
| test_intervention.py | 通过 | 5 |
| test_intervention_gui.py | 通过 | 0 |
| test_mcp_overrides.py | 通过 | 4 |
| test_peer_recovery.py | 通过 | 10 |
| test_peer_review.py | 通过 | 6 |
| test_peer_ui.py | 通过 | 1 |
| test_process_job.py | 通过 | 3 |
| test_projects.py | 通过 | 13 |
| test_read_memory.py | 通过 | 2 |
| test_repairs.py | 通过 | 9 |
| test_review_fix_gui.py | 通过 | 0 |
| test_review_fix_integration.py | 通过 | 2 |
| test_review_fixes.py | 通过 | 17 |
| test_runtime_components.py | 通过 | 6 |
| test_runtime_discovery.py | 通过 | 5 |
| test_storage.py | 通过 | 8 |
| test_system.py | 通过 | 6 |
| test_upgrade020.py | 通过 | 21 |
| test_waiting.py | 通过 | 11 |
| test_windows_startup.py | 通过 | 0 |

计数为 0 的脚本使用自有断言/GUI 检查，不代表没有检查。准确命令、环境、时间、退出码和原始日志见证据包的 final-source / final-package 目录。

## 首次失败与复测

旧版新增回归先复现 A01/A02/A04/A05/A06/B02/B03 七项；A03 独立复现 B 审查 scratch 写权限；B01 在越界 mkdir 前由守卫拦截。首次失败均保留。实现后的失败包括：新增 import 放在 __future__ 前造成语法错误；旧输入排序测试仍预期构造文本就消费消息；旧兼容测试仍等候 0.3.10 文案；扩展路径表示泄露至运行时设置。相应修复及最终复测日志分别保留，不包装成首次通过。

只读测试前置的 Windows ACL 首次使用通用写拒绝，连带阻止同步读取；修正为具体写权限拒绝后，明确验证读允许/写拒绝。随后发现 runner 即使提供 --out 也提前探测默认 TEMP；改为仅在未指定 --out 时求默认目录。前者属于夹具设置问题，后者是 B01 的补充修复。

## 未验证、阻塞与升级限制

- 当前真实 Codex thread/start 报错：windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; refusing to run unsandboxed。权限规则和配置回归已通过，但不能将它等同于真实工具权限通过。本版保留拒绝执行，不通过移除隔离解决该阻塞。错误来自本次 Codex 子进程环境；未据此断言两台用户电脑的正常启动环境必然相同。
- 真实 SMB/UNC、真实双机竞争和恢复、真实模型协作、独立 B 对 0.3.20 的复核：未执行。0.3.19 的 B 审查不算 0.3.20 的 B 回执。
- B 原始审查附件跨机归档在原材料中尚未闭环。本版提供完整受测源码、测试和证据包供接收；sent_to_B=NOT_PERFORMED，B_receipt=NOT_ESTABLISHED。不能用本机文件路径代替 B 实际接收。
- 100 轮耐久检查未执行；标准 runner 明确排除 test_endurance.py。真实生产状态升级/回退未验收，只验证历史兼容的本机夹具；旧程序和备份保留不等于无损回退证明。
- 本次沿用 0.3.19 便携 ZIP 形式；未生成或验证安装器。C# 安装器模板使用同一版本源，不宣称安装器实际交付。
- GitHub API 仍返回 Forbidden，推送、标签、Release 和资产上传均未完成；网络恢复后的同步材料独立准备，并进行远端哈希回读才可标记发布成功。

双方均升级至 0.3.20。旧历史保留，升级不自动调用模型；技术中断需明确继续，不重发不确定请求。旧 included_next_request 无法凭空判断是否发送，不能批量改回 queued。回退须使用升级前一致备份，不能让 0.3.19 接管本版活动状态。详细步骤见 DEBUG-0.3.20.md。

## 交付清单与 B 接收要求

本地发行位置：C:\AgentLink-GUI\dist。便携目录 AgentLink-GUI-0.3.20 含程序、运行时、完整 source（测试/构建脚本/需求/历史报告）、许可证、README、DEBUG、交付报告和开发日志。

同目录提供：AgentLink-GUI-0.3.20-Windows-x64.zip、AgentLink-0.3.20-Verification-Evidence.zip、RELEASE-0.3.20.md、DEVELOPMENT-LOG-0.3.20.md、SHA256SUMS-0.3.20.txt、VERIFICATION-0.3.20.json。最终 ZIP 哈希只放外部清单，避免循环依赖。证据包保留开发失败/复测、最终只读和包内结果、源码清单及核验工具；真实权限预检 private-rpc 原始配置日志只留本机，不公开打包。

B 后续接收应返回：包哈希、source 清单核对、实际读取范围、独立测试命令/环境/结果、九项结论及报告/证据包的接收回执。只有完成这些动作才补充 B 独立验收状态。本轮未开发通用附件传输 UI。

构建完成、本机通过、本地发行、B 接收、真实环境验收、GitHub 发行均独立记账；本版完整验收为 false。
