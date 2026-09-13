# AgentLink 0.3.21 交付报告

时间：2026-09-13T15:14:35.693486+08:00。基线：0.3.20；依据用户确认的心跳修复策略实施。源码：C:\AgentLink-release-0.3.21\source。

结论：心跳修复与本机回归完成，本地便携发行包已验证。FULL_ACCEPTANCE=false。真实双机、独立B和真实模型运行尚未验收；当前环境SMB访问拒绝，Codex权限预检阻塞，GitHub API返回Forbidden，未完成GitHub远端发行。

## 最终行为

- 本机经过时间、递增序号和双方实例绑定的挑战应答共同确认存活；墙上时间差只用于诊断。重放原−1.098秒，以及正负钟差和时间跳变，不再仅因时差拒绝执行。
- 首次、重连和采样长间隔重新确认；遗留文件、旧应答、重复/倒退序号不能延续执行资格。身份、归属和角色锁检查保留。
- 不足12秒正常；12～不足30秒响应延迟，阻止新请求并等待重新确认；达到30秒技术中断。实例改变、锁释放及明确离线立即阻止。已发送请求仍接收已有结果，不自动重发。
- 调度、快照收发、恢复及GUI状态统一；turn/start与turn/steer均守卫实际发送，停止先提交时发送为零。尚未写管道的实时补充保留queued；实际写入后未知结果保持uncertain。
- 握手期间的明确上下文恢复指令保留待处理；用户停止不复活。关联恢复保留旧场次/A成果，不直接改旧participants。
- 测试入口允许显式project-tests隔离根，仍拒绝生产数据及UNC；长路径夹具动态构造，context_view临时目录用扩展路径清理。测试修复单列，不冒充其他产品缺陷修复。

Windows存活计时使用包含休眠时间的Win32 uptime，依据[Microsoft Windows Time](https://learn.microsoft.com/en-us/windows/win32/sysinfo/windows-time)；真实机器睡眠唤醒未执行，长采样间隔/重新握手由注入测试验证。

## 验证

- 最终完整离线回归：40个脚本全部通过，234次unittest用例执行。脚本内重复继承/复跑不充当唯一用例数；0计数脚本有独立断言，详见日志。
- 包内运行时复验：8个脚本，59次用例执行；通过。
- 实际EXE/Win32标题/正常退出和拥有的子进程树清理：通过；产品和文件版本核对另见证据。
- 独立本地进程：强制结束对端后遗留心跳被角色锁检查立即拒绝；持锁停止心跳约12.172秒进入迟滞、30.203秒不可用。两项claim=0/model=0；未把本地独立进程称为真实双机。
- 等深目录的5脚本通过（50次unittest执行，准确计数见deep-layout/receipt）。实际AppData/project-tests新目录写入被拒绝；验证使用C盘独立目录模拟同样布局并重定向LOCALAPPDATA，不能称真实AppData入口已通过。
- 0.3.20原始发布源码99文件逐文件SHA-256保持一致。最终应用、包内app及source对照由VERIFICATION记录。
- 本机两服务、真实本地文件锁/快照、mock Codex子进程经过正式工作流与明确恢复测试；这是本机模拟双节点，不是两台电脑。
- 真实Codex权限预检3次thread/start均被本工具环境的Windows sandbox初始化阻止，turn/start=0；没有绕过限制。
- 真实SMB只读访问拒绝；真实双机/B独立审查/真实模型任务未执行。GitHub API Forbidden，未推送或创建远端Release。

| 脚本 | 结果 | unittest执行数 |
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
| test_liveness021.py | 通过 | 12 |
| test_liveness_io021.py | 通过 | 3 |
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

完整命令、首次失败与复测日志见独立验证证据包和本机evidence。深project-tests验证及附加门禁探针以各自receipt为准，未与完整套件混计。

## 首次失败、范围与限制

首次权属测试失败来自旧夹具没有挑战应答，更新模拟对端后复验。首次上下文升级恢复失败暴露了握手期间“继续”被消费，修复为保留明确指令等待。其他首次失败与最终复验保持独立目录，不覆盖失败记录。详见开发日志及每次results.json。

设计细化：首次握手完成后才取得新任务的讨论租约；运行中的短时等待继续保留整场discussion/execution租约，避免另一场接管。握手处理不申请这些锁，生命周期锁内不阻塞等待响应。此处细化草案中笼统的“不持discussion锁等待”，保持既有整场执行归属边界。

保留已知的A020-02证据索引缺失/null重建、A020-03重复发布端暂存残留；未声称本版修复这些独立问题。针对旧A020-04/05仅修复验证所需测试入口/夹具。心跳证明可响应性，不是密码学认证，也不能绝对消除发送瞬间对端退出的竞态；请求账本及不自动重试继续约束后果。

## 升级和恢复

两端都换用0.3.21并连接，等待双方显示就绪。旧版可看历史但不参与新协议执行。程序沿用既有本机账号/设置/历史，不复制账号到对方。

当前0.3.20中断任务：保留A初审和原始记录；两端升级后选择原任务，明确输入“继续”。程序验证父场次、快照和实际请求记录，建立关联恢复场次，接续未完成的B步骤。若请求已发送或证据不足，按原不确定恢复规则处理，不自动重跑A或B。实际用户场次恢复未在本次环境代为执行。

交付：AgentLink-GUI-0.3.21目录、Windows-x64.zip、完整源码/测试/需求、RELEASE、DEVELOPMENT-LOG、SHA256SUMS和VERIFICATION；验证证据另包。原0.3.20保留，不覆盖旧发行。
