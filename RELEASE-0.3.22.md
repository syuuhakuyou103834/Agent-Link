# AgentLink 0.3.22 交付报告

本地候选测试发行包已构建和验证，准备封存交付。时间：2026-09-14T00:30:03+08:00（Asia/Shanghai）。**FULL_ACCEPTANCE=false**。
这是候选测试发行；真实 SMB、双机、真实模型权限与恢复尚未验收。GitHub API 返回 Forbidden，远端发布阻塞。不能称完整验收或 GitHub 发行完成。

## 1. 版本与来源

- 开发基线：v0.3.21，提交 b6eeb6386d260f2e5663315239cae8c9280ad338；独立目录 `C:\AgentLink-release-0.3.22\source`，分支 `codex/agentlink-0.3.22`。
- 用户批准的依据：`C:\AgentLink-plans\0.3.22\UPGRADE-ROADMAP.md`；输入 handoff SHA-256：63b593a0178e6b4e2440bb44137a9b875f80149741167ed743105291683c7534。
- 原 0.3.20、0.3.21 发行源码前后逐文件哈希一致。外部 `VERIFICATION-0.3.22.json` 记录最终提交、应用/源码/包清单；ZIP 内不嵌入自身哈希。
- 本机 Windows x64，Python 3.13.13、PyQt5 5.15.11、Qt 5.15.2；使用本机已有运行时与 C# 编译器构建，未下载替代运行时。

## 2. 业务范围与验收

对应 [BR-022 / AC-022-01～10](source/docs/BUSINESS-REQUIREMENTS.md)。用户批准七项修复、恢复入口、最小异步诊断、原始源码 ZIP 接收核验及同形式发行。

| 要求 | 实际完成 | 验收状态 |
|---|---|---|
| 01 清理及归属 | 清理失败保留租约；状态复位；重启核对宿主/子进程创建身份及 Job 归属证明；先保留已收到答案 | 本地 native/mock/注入通过；真实事故恢复未执行 |
| 02 心跳 I/O | 各通道累计故障；成功只清除对应通道；保留序列/实例挑战及 12/30 秒语义 | 交错轮询、故障与恢复通过；真实 SMB 故障未执行 |
| 03 证据 | 已有索引/包丢失、null、损坏拒绝静默重建；首次构建暂存提交，旧有效证据验证后接纳 | 本地正负例通过 |
| 04 暂存 | 重复发布复用已验证原包；ZIP 内容及清单核对；回收本次暂存；失败保留外部诊断 | 本地重复、损坏、中途失败通过 |
| 05 测试 | 深路径夹具/模拟服务器文件操作修复；挑战就绪后仅由 A 发起耐久任务 | 深路径五脚本及 110 任务耐久通过；历史 B 原始超时未全部归因 |
| 06 版本 | 单一版本来源；实际 EXE/manifest、提示脚本、GUI、源码一致 | 实际 EXE 及包核验通过 |
| 07 恢复 | 明确“恢复任务”按钮与精确命令；连接就绪和任务恢复区分；用户停止不复活 | 本地 GUI/恢复工作流通过；用户原场次未代操作 |
| 08 诊断 | 本机有界队列、元数据白名单、轮转/丢弃/写入错误计数；共享 issues 读取移到工作线程 | 本地慢盘/失败注入及 GUI 测试通过 |
| 09 原始包 | 接收端保留同一 ZIP 原始字节、清单、ready 和服务校验回执；B 只读授权限定目录 | 本地交付通过；B agent 真实接收/独立测试未执行 |
| 10 发行 | 便携包、源码、需求、报告、开发日志、证据和校验清单 | 本地候选；远端上传/真实验收阻塞 |

完整监控平台、自动回传任意 B 测试附件、审查收敛规则后移至后续版本评估，未声明实现。

## 3. 变化与问题对应

| 原问题 | 修复与当前行为 | 关键回归 |
|---|---|---|
| B021-01 P1 | `_unified_chat` 立即登记执行租约；清理异常不丢归属，确认前禁止新请求；已返回原始结果先存本机 | test_regressions022 / test_cleanup_failures / test_cleanup_admission / test_stability022 |
| A021-03 P2 | 心跳、同步、执行等故障独立计时，普通轮询不清零连续心跳失败 | test_regressions022 / test_liveness_io021 / test_stability022 |
| A021-01 P2 | 已有证据只校验，独立提交标记及先前引用检测整包丢失 | test_regressions022 / test_context_view / test_stability022 |
| A021-02 P2 | 验证原包后复用；只删除本次受控暂存，接收端保留有意的原始审查副本 | test_regressions022 / test_projects / test_stability022 |
| A021-04 P2 | 测试扩展路径独立于产品；修复 mock 的 pathlib 和内置 open；产品 stdout/stderr 日志也使用扩展路径 | 深路径五脚本；首轮失败未覆盖 |
| B021-02 P2 | 先等实例挑战完成，A 发起 10 次预热及 100 次测量，动态记录实际子进程 | test_endurance |
| B021-03 P3 | manifest 构建时替换统一版本；维修提示读取当前 app 版本 | 实际 EXE 元数据/资源与语法检查 |

新增恢复按钮和最小诊断；“审查未达成一致”细分为“需修改，尚未通过验收”等状态。共享问题目录拒绝访问由工作线程返回错误，不在 Qt 回调同步读盘。没有删除已公开功能；旧协议执行门禁升级到 v7，两端须同时升级。

## 4. 逐项验证

完整套件：43 脚本全部通过，256 次 unittest 用例执行；本次报告所用目录 `C:\AL22-sealed-source`。包内运行时：10 脚本，67 次 unittest 执行，通过。

```powershell
& 'C:\Program Files\Python\python_3.13\python.exe' -B tests/run_release_checks.py --out C:\AL22-sealed-source --keep-going --timeout 180
& 'C:\Program Files\Python\python_3.13\python.exe' -B tests/run_release_checks.py --out C:\AL22-endurance-final --names test_endurance.py --timeout 1200
& 'C:\Program Files\Python\python_3.13\python.exe' -B packaging/build.py --zip-only
```

每个子进程的实际命令、开始时间、PID、退出码、清理确认、耗时在各组 `results.json`；详细断言与错误在同名 `.log`。包内检查命令和原生启动脚本随独立证据包提供。

| 脚本 | 状态 | 秒 | unittest 执行次数 |
|---|---|---:|---:|
| test_authority.py | passed | 0.63 | 5 |
| test_cleanup_admission.py | passed | 14.89 | 2 |
| test_cleanup_failures.py | passed | 0.75 | 4 |
| test_code_gui.py | passed | 6.76 | 0 |
| test_code_workflow.py | passed | 24.3 | 6 |
| test_context.py | passed | 0.43 | 8 |
| test_context_resume_guard.py | passed | 0.22 | 1 |
| test_context_ui.py | passed | 0.31 | 1 |
| test_context_view.py | passed | 0.6 | 6 |
| test_context_workflow.py | passed | 44.35 | 7 |
| test_conversation.py | passed | 80.33 | 14 |
| test_conversation_guards.py | passed | 0.29 | 8 |
| test_failure_recovery.py | passed | 40.77 | 1 |
| test_faults.py | passed | 24.33 | 8 |
| test_freshness.py | passed | 0.51 | 7 |
| test_gaps.py | passed | 0.74 | 6 |
| test_gui.py | passed | 6.6 | 0 |
| test_integration_upgrade.py | passed | 3.11 | 6 |
| test_intervention.py | passed | 21.23 | 5 |
| test_intervention_gui.py | passed | 0.22 | 0 |
| test_liveness021.py | passed | 6.32 | 12 |
| test_liveness_io021.py | passed | 0.27 | 3 |
| test_mcp_overrides.py | passed | 0.16 | 4 |
| test_peer_recovery.py | passed | 37.41 | 10 |
| test_peer_review.py | passed | 19.61 | 6 |
| test_peer_ui.py | passed | 0.3 | 1 |
| test_process_job.py | passed | 7.29 | 3 |
| test_projects.py | passed | 0.36 | 13 |
| test_read_memory.py | passed | 0.14 | 2 |
| test_regressions022.py | passed | 0.75 | 6 |
| test_repairs.py | passed | 20.8 | 9 |
| test_review_fix_gui.py | passed | 0.28 | 0 |
| test_review_fix_integration.py | passed | 10.41 | 2 |
| test_review_fixes.py | passed | 0.96 | 17 |
| test_runtime_components.py | passed | 0.19 | 6 |
| test_runtime_discovery.py | passed | 0.19 | 5 |
| test_stability022.py | passed | 0.49 | 13 |
| test_storage.py | passed | 1.24 | 8 |
| test_system.py | passed | 34.02 | 6 |
| test_ui022.py | passed | 0.25 | 3 |
| test_upgrade020.py | passed | 1.22 | 21 |
| test_waiting.py | passed | 11.92 | 11 |
| test_windows_startup.py | passed | 0.89 | 0 |


附加检查：六个最终负例用于未改 0.3.21，六项全部按预期失败；同六例在 .22 通过。深中文路径五脚本全部通过；完整回归中的正式/补充聊天、停止、恢复和 Windows 原生进程树场景均通过。实际 EXE 窗口标题、包内 pythonw 路径、正常退出及受控进程树清理：通过。

耐久：110 任务（10 预热+100 测量）、330 mock 请求；前后各 20 个测量任务中位数比较，private bytes 40,980,480 → 42,530,816，增长 3.7831%；句柄 312 → 312，增长 0%；阈值均为 20%。这是本机两个服务及模拟 App Server 子进程，不是真实双机/模型；90 秒 faulthandler 栈打印是周期诊断，最终退出码和结果为通过。

## 5. 证据分层

| 层次 | 结果 | 边界 |
|---|---|---|
| 本机单元/模拟/本地文件锁 | 通过 | 43 脚本；native 子进程存在性与独立锁探针不代表真实模型并发已验收 |
| GUI / Windows Qt | 通过 | 测试窗口与恢复状态；完整 DPI/多屏/睡眠唤醒未执行 |
| 便携 EXE 和包内运行时 | 通过 | 隔离数据启动；无真实账户/任务操作 |
| 真实 SMB | 阻塞 | 默认共享只读访问 Access denied；未写入共享目录 |
| 真实双机 / B 独立原包接收审查 | 未执行 | 本地模拟交付哈希不替代 B agent 阅读/测试 |
| 真实 Codex 权限/模型 | 阻塞 | summary/review/implement 三次 thread/start 初始化被 Windows sandbox 拒绝；turn/start=0 |
| 用户原场次升级/恢复/回退 | 未执行 | 本地历史/恢复兼容测试通过，不修改正在运行的用户任务 |
| 安装器 | 不适用 | 沿用 0.3.21 便携 ZIP 形式，未生成 Setup.exe |
| GitHub | 阻塞 | gh repo view 的 GraphQL 请求返回 Forbidden；未推送、未建远端 Release |

## 6. 计数口径

43 是不同脚本数；256 是 unittest footer 中的执行次数，含继承复跑，不冒充唯一方法数；没有汇总去重后的唯一方法数量。0 footer 的脚本使用独立断言。全套、深路径、包内和耐久是分开的运行，不累加为唯一覆盖率。六个旧版负例失败是复现成功，不计入新版通过数。真实模型 turn/start=0；330 为耐久 mock 请求，其他功能测试 mock 调用另见各运行账本，未声称 330 是本轮所有模拟请求总数。

## 7. 首次失败与限制

- 原始 B005 ZIP 未在本轮独立接收。讨论中的历史 27 通过/7 失败/6 超时保留；本地成功不抹去 B 的第一次失败。详见开发日志的逐脚本对应表。
- 首轮 6 负例全部失败；P1 首次辅助进程 GBK 解码噪声保留。core1 新实现漏建提交标记父目录，修正后 core2 通过。
- 额外旧版复查助手首轮未把 unittest 类注册到主模块，跑了 0 个测试；保留该无效记录，第二轮 6 个真实失败才作为证据。
- 最深布局暴露 mock 两处内置 open 及产品 stderr 诊断普通路径遗漏；首次日志和 stderr 原因保留，修复后五脚本通过。不能把全部 B 超时都归因于长路径。
- 未确认先前 B 退出是否由杀毒软件造成；用户事故根因仍 UNKNOWN。本版未关闭心跳、放宽阈值或禁用杀毒软件。
- 本机 `received-results` 保留已返回的原始答案，尚未经验证/发布的结果不能自动升级为正式成果。明确恢复时可读取原结果，仍可能需要模型完成未验证步骤；不确定请求不自动重发。
- 旧执行宿主/子进程归属无法确认、记录损坏或访问拒绝时继续阻止执行；不会仅用 PID 或盲删锁文件解除保护。
- 日志仅为本机诊断，不会自动抓包、上传或唤醒 Codex。新增事件白名单不包含提示正文/凭据；既有 App Server 原始日志可能含任务内容，仅留本机，分享前另行检查。

下一步由 A/B 两台实际测试机依据 [真实验收清单](source/docs/REAL-ACCEPTANCE-0.3.22.md) 验证权限、SMB 断连、强制退出、恢复和独立原包接收；取得证据后再决定正式稳定验收。

## 8. 交付清单与校验

位置：`C:\AgentLink-GUI\dist`。便携目录 `AgentLink-GUI-0.3.22`、`AgentLink-GUI-0.3.22-Windows-x64.zip`、完整 source/运行时/许可证/需求、RELEASE、DEVELOPMENT-LOG、DEBUG；外部 `SHA256SUMS-0.3.22.txt`、`VERIFICATION-0.3.22.json`、`UPLOAD-RESULT-0.3.22.json`、`AgentLink-0.3.22-Verification-Evidence.zip`。

证据包保存本轮首次失败、回归/包内/深路径/耐久运行记录，基线清单、构建/原生检查和发布助手。真实 Codex 的 private-rpc、缓存及直接列出的 .env 文件不进入公开证据；测试 ZIP 可能包含验证排除规则所需的假凭据夹具，不包含真实账号资料。受控原件保留原机。它不包含未收到的 B005 ZIP，也不冒称 A 已收齐 B 原始证据。

最终外部清单核对 ZIP CRC、应用与包内 source 一致、源码完整性、原始 .20/.21 未改、报告内外一致。Git 提交及 tag 和 ZIP SHA 以外部 VERIFICATION 为准，避免报告自引用循环。

## 9. 升级与使用

保留正在运行的 0.3.21；在两端确认当前请求状态、正常退出后，分别解压独立 0.3.22 目录并启动 AgentLink.exe。两端必须同为 .22，使用原通信目录，等待实例挑战就绪。原设置/账号留在各自机器，不随包迁移账号。

选择原历史任务，核查已完成的 A/B 结果，再使用“恢复任务”或精确输入“继续”。“继续执行”“恢复任务”按明确命令处理；普通长句不误触发。连接就绪不等于任务已恢复。清理受阻时先正常断开核查；不得手动删锁强行重发，不确定请求需核对原结果。

新诊断位于本机数据目录 logs 下的 `runtime-events.jsonl` 和 `runtime-state.json`，默认通常为 `%LOCALAPPDATA%\AgentLinkGUI\logs`，以实际配置为准。队列最多 256 项；4 MiB 轮转、4 个备份；写盘失败/溢出计数可见。记录不等同全量数据库快照。

保留旧版目录便于回看；未执行真实生产数据回退验收，不保证新协议现场可直接用旧版续跑。旧版应配套运行，禁止混用节点；现有用户任务未被本轮自动恢复、停止或迁移。

## 10. 发布结论

七项修复及限定的恢复/诊断改进已实现并通过本地验证；便携包和实际 EXE 已通过隔离检查。本地交付封存以外部 VERIFICATION 的完成记录为准。**B 独立复核、真实 SMB/双机/模型与 GitHub 远端发行没有完成；FULL_ACCEPTANCE=false。**
