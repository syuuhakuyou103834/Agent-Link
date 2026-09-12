# AgentLink 0.3.19 交付报告

发布日期：2026-09-12T23:33:11+0800（Asia/Shanghai）。结论：便携版构建完成、本机验证通过，发行到 `C:\AgentLink-GUI\dist`。尚未交付给 B 独立验收，完整验收 `false`。

## 版本与来源

- 基线：已发行 0.3.18 ZIP，SHA-256 `75f08b6e2b6841bc544ad95ff0282e040bf213a838a7e6cd84ad166ba3347c68`；其中 87 个源码文件已核对。原版本、原审查场次及冻结证据未覆盖。
- 受测源码：`C:\AgentLink-release-0.3.19\source`。本次接续沿用该目录已有产品实现，补完验证与交付；接续阶段对产品 app 文件没有修改。
- 受测代码清单：`code-manifest.json`，77 个 Python/C# 文件，清单 SHA-256 `c10a394fc8e95b0c60aa1ab63a44ae5302d94e994adb148f1d748d50ef2c72d1`。完整源码清单另含文档，见证据包 `source-manifest.json` 及外部 `VERIFICATION-0.3.19.json`。
- Windows x64；Python 3.13.13；PyQt5 5.15.11 / Qt 5.15.2。包内运行时实际执行通过；EXE FileVersion / ProductVersion 均为 `0.3.19.0`，源码及界面显示 `0.3.19`。
- 依据：[原任务对话](https://chatgpt.com/s/cx_6aa56895a31c8191a0835b0dd3450c79)、`source/docs/BUSINESS-REQUIREMENTS.md` 和 `source/docs/RELEASE-PROCESS.md`。

## 解决的问题与实际行为

0.3.18 在心跳或实例校验失败时，将技术中断写成 cancelled；界面允许“继续”，恢复入口却只接受 failed，造成流程无法接续。本版区分技术中断与用户主动停止，并对符合严格证据条件的旧记录开放明确恢复。

| 需求 | 实现及本机验收 |
|---|---|
| AC-019-01 | 技术中断保存 failed 及诊断；用户停止仍为停止，迟到错误不覆盖原终态。通过。 |
| AC-019-02 | 旧 cancelled 仅在固定旧错误、节点错误一致且 control.cancelled=false 时可恢复；原 state/error/已完成成果保持不变。通过。 |
| AC-019-03 | 关联恢复继承 A 已完成成果及原快照，只接续 B 未完成步骤；模拟两端服务重启后也通过。 |
| AC-019-04 | 已发送或不确定请求不会自动重试；明确继续复用 B 原本机任务并保留尝试记录。通过。 |
| AC-019-05 | 保存观察节点、心跳时间差、实例、执行阶段、请求状态；顶栏时间有效性与守卫对齐。通过。 |
| AC-019-06 | context UI 测试改用本机共享路径；回归隔离、超时栈、进程清理、源码/包/文档校验完成。通过。 |

保留单一对话入口、A 发起/B 审查权限、只读范围、快照交付、原上下文、轮数和显式恢复规则；没有删除用户功能。心跳阈值仍为 -1 秒至不足 12 秒，实例绑定及角色锁仍有效。其他历史审查项没有被宣称全部修复。

## 逐项验证

源码命令：在 source 目录执行 `python -B tests/run_release_checks.py --out <新的证据目录>`。默认每脚本 240 秒超时，90 秒起保留线程栈；Windows Job Object 负责本次测试子进程清理。全部 37 个脚本通过，清理回执全部 confirmed。

| 源码脚本 | 结果 | 秒 |
|---|---|---:|
| `test_authority.py` | 通过 | 0.92 |
| `test_cleanup_admission.py` | 通过 | 11.26 |
| `test_cleanup_failures.py` | 通过 | 0.66 |
| `test_code_gui.py` | 通过 | 7.17 |
| `test_code_workflow.py` | 通过 | 16.06 |
| `test_context.py` | 通过 | 0.77 |
| `test_context_resume_guard.py` | 通过 | 0.23 |
| `test_context_ui.py` | 通过 | 0.28 |
| `test_context_view.py` | 通过 | 0.77 |
| `test_context_workflow.py` | 通过 | 35.66 |
| `test_conversation.py` | 通过 | 62.06 |
| `test_conversation_guards.py` | 通过 | 0.41 |
| `test_failure_recovery.py` | 通过 | 40.67 |
| `test_faults.py` | 通过 | 14.20 |
| `test_freshness.py` | 通过 | 0.93 |
| `test_gaps.py` | 通过 | 1.05 |
| `test_gui.py` | 通过 | 7.03 |
| `test_integration_upgrade.py` | 通过 | 1.16 |
| `test_intervention.py` | 通过 | 12.38 |
| `test_intervention_gui.py` | 通过 | 0.21 |
| `test_mcp_overrides.py` | 通过 | 0.16 |
| `test_peer_recovery.py` | 通过 | 31.42 |
| `test_peer_review.py` | 通过 | 15.89 |
| `test_peer_ui.py` | 通过 | 0.28 |
| `test_process_job.py` | 通过 | 7.46 |
| `test_projects.py` | 通过 | 0.43 |
| `test_read_memory.py` | 通过 | 0.14 |
| `test_repairs.py` | 通过 | 12.94 |
| `test_review_fix_gui.py` | 通过 | 0.41 |
| `test_review_fix_integration.py` | 通过 | 8.39 |
| `test_review_fixes.py` | 通过 | 1.83 |
| `test_runtime_components.py` | 通过 | 0.18 |
| `test_runtime_discovery.py` | 通过 | 0.17 |
| `test_storage.py` | 通过 | 1.29 |
| `test_system.py` | 通过 | 20.69 |
| `test_waiting.py` | 通过 | 9.97 |
| `test_windows_startup.py` | 通过 | 1.11 |

包内命令：`runtime\python.exe -B source\tests\run_release_checks.py --out <新的目录> --names <下表脚本>`。使用包内 Python 和源码，11 个不同脚本通过；复跑不重复计数。

| 包内脚本 | 结果 | 秒 |
|---|---|---:|
| `test_peer_recovery.py` | 通过 | 35.71 |
| `test_repairs.py` | 通过 | 13.89 |
| `test_intervention.py` | 通过 | 15.43 |
| `test_windows_startup.py` | 通过 | 1.68 |
| `test_peer_ui.py` | 通过 | 0.73 |
| `test_code_gui.py` | 通过 | 7.81 |
| `test_conversation.py` | 通过 | 69.26 |
| `test_context_view.py` | 通过 | 1.21 |
| `test_context_workflow.py` | 通过 | 40.49 |
| `test_context_ui.py` | 通过 | 0.76 |
| `test_context_resume_guard.py` | 通过 | 0.72 |

此外：`runtime\python.exe -B main.py --data-dir <隔离目录> --preview <PNG>` 退出码 0；Windows 原生 Qt 插件、主窗、设置窗和恢复提示测试通过。实际查看了主窗与恢复提示截图，中文及 0.3.19 版本显示正常。此项证明包内 main.py 及 GUI 启动；没有把 EXE 元数据检查表述为已独立操作 launcher 的交互验证。

真实故障冻结复制件命令：`python -B tests/replay_peer_incident.py <冻结目录> <新的本机目录>`。结果 `PASS_COPY_PLAN_ONLY`：目标 B、索引 1、继承 A 一条成果，原文件哈希未变，服务和模型未启动。它只证明恢复计划，不代表真实 B 已接收或原任务已经恢复。

## 首次失败、修正与证据边界

1. 先前源码 `test_repairs.py` 与包内 `test_peer_recovery.py` 超时原日志保留。接续后精确失败用例单跑通过；最终源码及包内完整对应脚本均通过。原偶发超时未再次复现，根因 UNKNOWN；没有把重新通过写成根因修复。
2. 一次计划八次的诊断复跑只观察到四次通过后工具调用遭网络策略错误中断；记录为未完成，不计作八次成功或完整通过。
3. 本轮首个全回归中 `test_intervention.py` 失败：测试在 B 尚未绑定任务时发定向命令；重现事件为 NoneType 任务编号。测试现等待 B 接入再发送，保留原目标及去重断言；源码和包内复测通过。产品的“提交时绑定任务”行为保持不变。
4. 加深日志/夹具目录后，源码及包内快照断言失败。保留的文件路径达到 260 字符，普通 glob 返回空；扩展路径读取成功且原 job completed。修正测试运行器为短路径隔离夹具后，同一源码和包内测试通过。没有将此夹具查询误报归为产品未发布快照。

首次记录及后续结果均未覆盖。原 76 个证据文件哈希核对不变。原心跳失效缺少完整原始时间值，网络、共享 I/O 延迟或时钟偏差的具体原因仍未确定。

## 计数与分层

- 源码 37 个不同测试脚本；最终日志中 185 次具名方法执行，按 Class.method 去重 185 个。脚本中的额外断言不另造“用例数”；重复执行与包内复跑均不增加唯一用例。
- 新增心跳/恢复专项为 10 个独立用例，已包含在上述源码结果中。包内验证为 11 个不同脚本，另有版本查询及主窗预览。
- 本轮验证真实模型请求为 0；App Server 均为本机子进程 mock。全历史 mock 请求不作未经核实的累计数。定向恢复断言：未发送 B 的恢复为 A=3/B=1（含 A 澄清及总结），已发送 B 的明确恢复为 A=3/B=2；均不是正式协作轮数。

| 层级 | 状态 |
|---|---|
| 本机单元、两个模拟节点、进程隔离、GUI、包内运行时 | 通过 |
| 冻结记录复制件恢复计划、旧证据哈希、ZIP/目录/源码一致性 | 通过 |
| 真实 SMB、真实双机故障恢复、B 独立源码/运行审查、真实模型 | 未执行 |
| 生产数据升级/真实历史接续、真实 launcher 交互操作、100 轮耐久 | 未执行 |
| 安装器、GitHub 上传、向 B 发送发布材料 | 未执行；本版沿用便携 ZIP 发行 |

## 交付物与证据索引

发行目录 `C:\AgentLink-GUI\dist`：

- `AgentLink-GUI-0.3.19\AgentLink.exe`：便携启动程序；同目录包含 runtime、app、licenses、DEBUG 说明及完整 source（代码、测试、构建脚本、需求、报告和开发日志）。
- `AgentLink-GUI-0.3.19-Windows-x64.zip`：可复制到另一台电脑的便携包。
- `RELEASE-0.3.19.md`、`DEVELOPMENT-LOG-0.3.19.md`：顶层、程序目录、source 和 ZIP 内副本一致。
- `SHA256SUMS-0.3.19.txt`、`VERIFICATION-0.3.19.json`：最终文件 SHA-256、完整源码及目录清单哈希、验证分层和发布回执。
- `AgentLink-0.3.19-Verification-Evidence.zip`：包含最终及首次失败日志、JSON 回执、截图、代码差异和清单。解压后看 `INDEX.md`。

本机完整受控原件：`C:\AgentLink-release-0.3.19\evidence\resume-20260912-231017`。源码首次快照、旧候选构建、真实故障完整原始材料和较大的模拟任务目录仅留本机；公开证据包仅含复制件的验证结果及索引，不包含真实场次全文或原始项目快照。ZIP 不嵌入自身最终哈希；外部校验清单避免循环依赖。

## 升级、原任务接续与回退

两端先确认没有任务在运行，再退出旧 AgentLink，分别解压 0.3.19 到新目录，运行 AgentLink.exe，沿用原数据与共享目录设置。两端都升级后，在 A 选择原中断对话并明确输入“继续”。升级、重连本身不会自动重发模型请求。

原任务审查对象仍是原 0.3.18 源码；不要改成 0.3.19 源码，不要新建同题任务、删除 state/claim/锁或用“停止”代替退出升级。若证据不匹配、已有恢复子场次、用户主动停止、范围或本地清理状态异常，保留提示并核查。详细诊断和操作见包内 `DEBUG-0.3.19.md`。

旧程序和旧 ZIP 保留，可退出新程序后重新启动旧程序；真实生产数据向旧版回退未验证，旧版也不具备本次修复，不应让旧实例接管新恢复场次。实际双机恢复及 B 独立审查仍由两端后续执行，本次没有操作原生产场次。
