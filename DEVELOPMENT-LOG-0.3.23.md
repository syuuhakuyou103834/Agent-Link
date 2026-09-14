# AgentLink 0.3.23 开发日志

执行者：本机Codex，Windows x64 / Python3.13.13；没有独立B执行本次代码。时间为Asia/Shanghai。


- 2026-09-14T11:10:20+08:00 | 本机 Windows / Python 3.13.13 | 用户纠正发行编号并授权按 0.3.23 路线实施和发行。独立分支开发；封存原 .22、计划和交接哈希；既有九项复核在 C:\AL23-review-20260914，首次失败保留。

- 2026-09-14T11:20:20+08:00 | 本机 Windows / Python 3.13.13 | 结果存储改为 schema 2 回执与正文分离，64 MiB 专用容量；旧 schema 1 明确兼容，null/错误归属/未提交均阻塞。项目、文本、澄清结果已保存后故障的三项真实本地服务/mock恢复通过，重复阶段调用为0。导出改为独立原子写入，详细日志改异步独立健康状态。夹具 AST 助手首轮括号替换语法错误未写入源文件，已修正；new1 两个新测试构造长度不足260，先决断言失败，已加深并保留首次日志。path1 原两恢复脚本通过；启动完整深目录回归。

- 2026-09-14T11:33:14+08:00 | 本机 Windows / Python 3.13.13 | 完整深目录回归首次确认剩余 TemporaryDirectory 清理、rename、ZipFile 及固定262字符夹具问题；规范化测试清理并先校验删除范围。助手 repeat/repeated 参数错误导致 fixes2 清理错误，已修正，fixes3通过。结果复用增加源码/权限关联回执，缺证拒绝套用旧分析；澄清消息提交成功而尝试记录失败时避免重复追加。真实 Codex、SMB、GitHub 本轮重新预检仍阻塞；未绕过。

- 2026-09-14T11:49:19+08:00 | 本机 Windows / Python 3.13.13 | log 最终受测应用和测试哈希已冻结；短目录45脚本、中文深目录45脚本均通过，包内绝对运行时10脚本通过。实际EXE隔离启动、标题、退出和受控子进程树通过，PE三个版本0.3.23.0。包测试首轮相对解释器路径导致WinError2及就绪超时，已中止保留AL23-package，绝对路径同包复跑通过；查询进程CIM被拒绝，未绕过。Verify-Evidence启动帮助首次误用packaging子目录，改为发行根目录后通过。查看Windows GUI截图确认版本/主操作可见，测试窗宽左侧品牌文字有裁切，未改布局。源/深/包套件结束后单独启动110任务耐久。

- 2026-09-14T11:51:28+08:00 | 本机 Windows / Python 3.13.13 | 串行耐久111.55秒通过：10预热+100测量任务、330mock请求，内存中位数增长5.6415%，句柄312到312，模拟子进程退出。90秒faulthandler定时栈为诊断快照，任务随后正常推进及完成，非脚本超时。最终源/深各45脚本271次unittest，包内10脚本56次。封存前再次核对受测应用/测试哈希未变；将提交本地v0.3.23并回读新交付目录，实际提交/哈希/复制结果由外部VERIFICATION记录，GitHub仍阻塞。

## 验证入口和保留现场

## 4. 逐项验证及证据

最终短目录 45 脚本 / 271 次 unittest 执行；中文深目录 45 脚本 / 271 次；包内运行时 10 脚本 / 56 次。草稿中0表示尚未结束，不是通过。

| 脚本 | 状态 | 秒 | unittest执行次数 |
|---|---|---:|---:|
| test_authority.py | passed | 0.65 | 5 |
| test_cleanup_admission.py | passed | 15.06 | 2 |
| test_cleanup_failures.py | passed | 0.72 | 4 |
| test_code_gui.py | passed | 6.79 | 0 |
| test_code_workflow.py | passed | 25.2 | 6 |
| test_context.py | passed | 0.44 | 8 |
| test_context_resume_guard.py | passed | 0.21 | 1 |
| test_context_ui.py | passed | 0.29 | 1 |
| test_context_view.py | passed | 0.59 | 6 |
| test_context_workflow.py | passed | 46.76 | 7 |
| test_conversation.py | passed | 79.94 | 14 |
| test_conversation_guards.py | passed | 0.3 | 8 |
| test_failure_recovery.py | passed | 40.67 | 1 |
| test_faults.py | passed | 22.0 | 8 |
| test_freshness.py | passed | 0.52 | 7 |
| test_gaps.py | passed | 0.76 | 6 |
| test_gui.py | passed | 6.53 | 0 |
| test_integration_upgrade.py | passed | 3.21 | 6 |
| test_intervention.py | passed | 23.68 | 5 |
| test_intervention_gui.py | passed | 0.22 | 0 |
| test_liveness021.py | passed | 3.96 | 12 |
| test_liveness_io021.py | passed | 0.27 | 3 |
| test_mcp_overrides.py | passed | 0.16 | 4 |
| test_peer_recovery.py | passed | 39.18 | 10 |
| test_peer_review.py | passed | 18.08 | 6 |
| test_peer_ui.py | passed | 0.29 | 1 |
| test_process_job.py | passed | 7.34 | 3 |
| test_projects.py | passed | 0.37 | 13 |
| test_read_memory.py | passed | 0.14 | 2 |
| test_regressions022.py | passed | 0.74 | 6 |
| test_repairs.py | passed | 19.94 | 9 |
| test_results023.py | passed | 0.64 | 10 |
| test_reuse023.py | passed | 19.49 | 5 |
| test_review_fix_gui.py | passed | 0.28 | 0 |
| test_review_fix_integration.py | passed | 10.6 | 2 |
| test_review_fixes.py | passed | 0.94 | 17 |
| test_runtime_components.py | passed | 0.2 | 6 |
| test_runtime_discovery.py | passed | 0.19 | 5 |
| test_stability022.py | passed | 0.51 | 13 |
| test_storage.py | passed | 1.19 | 8 |
| test_system.py | passed | 35.34 | 6 |
| test_ui022.py | passed | 0.26 | 3 |
| test_upgrade020.py | passed | 1.19 | 21 |
| test_waiting.py | passed | 10.75 | 11 |
| test_windows_startup.py | passed | 0.89 | 0 |


包内检查：

| 脚本 | 状态 | 秒 | unittest执行次数 |
|---|---|---:|---:|
| test_results023.py | passed | 1.29 | 10 |
| test_reuse023.py | passed | 24.16 | 5 |
| test_cleanup_failures.py | passed | 2.32 | 4 |
| test_cleanup_admission.py | passed | 15.28 | 2 |
| test_context_workflow.py | passed | 47.5 | 7 |
| test_projects.py | passed | 0.84 | 13 |
| test_process_job.py | passed | 11.69 | 3 |
| test_integration_upgrade.py | passed | 2.84 | 6 |
| test_code_workflow.py | passed | 30.26 | 6 |
| test_windows_startup.py | passed | 1.25 | 0 |


精确每脚本命令、开始时间、PID、退出码、受控子进程清理和 stdout/stderr 在证据 ZIP 的 final-source/final-package 及 runs 目录 results.json 和 *.log。最终源执行入口：Python -B tests/run_release_checks.py --out C:\AL23-sealed-source --keep-going --timeout 240。深路径相同入口，out 为 C:\AL23-sealed-deep 下19次“中文项目测试目录-”加run；源和深路径回归并行，耐久单独串行。

首次失败保留：new1 两项新测试长度不足260为夹具前提错误；full1 GUI导出测试在异步完成前读取；deep1 45脚本38通过7失败，包含普通路径清理/rename/ZIP和硬编码262字符夹具；fixes2 新夹具助手repeat参数错误，修正为repeated；后续回归通过。包内首轮命令误用相对Python路径，子进程切换目录后WinError2；该轮中止保留，使用同一包的绝对Python路径复跑，未改产品。这些是本机可归因记录，不能用来解释B历史全部9失败和超时。最初 .22 九项探针记录在 review-baseline。

串行耐久结果：{"status": "PASS", "spec": {"warmup": 10, "measured": 100, "rounds": 1, "stream_delay_seconds": 0.002, "topic_sha256": "1d07374ecd8ac002ee2a6aa322ff7df8eba6dcb0ba67d3777ecf1389d8febd83", "metric": "sum of private bytes and handle counts for harness + 2 mock subprocesses", "growth_threshold": 0.2, "compare": "medians of first/last 20 measured jobs", "layer": "local two services, local filesystem, offline App Server subprocesses"}, "requests": 330, "growth": {"private_bytes": {"first_median": 41820160.0, "last_median": 44179456.0, "growth": 0.05641527913809985}, "handles": {"first_median": 312.0, "last_median": 312.0, "growth": 0.0}}, "mock_processes_exited": true}。预期110个本机模拟任务、330 mock请求、内存和句柄增长不超过20%，子进程退出；运行原始result和samples随证据。


## 发行与未决事项

## 7. 已知限制与后续验证

B需在自己的机器交付原附件与回执、运行同一源快照并记录独立读取/实际测试范围；本版工具只核验本机文件，agent_read/tests_executed仍为false。Python3.14、杀毒误杀原事故、真实SMB中断重连、双机并行冲突、模型权限及已返回未发布恢复还需真实验收。不能从空闲AppServer存活推断旧任务仍执行。详细日志磁盘失败/队列满时无法保证持久化；本版显示健康状态，不能从缺日志判断未请求模型。已检查本机Windows GUI截图，主操作和版本可见；测试窗口宽度下左侧品牌文字有裁切，本轮未调整布局，不宣称所有缩放比例均视觉验收。

## 8. 交付清单

C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.23：AgentLink.exe、runtime、app、source（含tests/packaging/docs）、licenses、README、DEBUG、RELEASE和DEVELOPMENT-LOG。同级提供 Windows-x64.zip、独立报告/日志、AgentLink-0.3.23-Verification-Evidence.zip、SHA256SUMS-0.3.23.txt、VERIFICATION-0.3.23.json、UPLOAD-RESULT-0.3.23.json。最终ZIP哈希只在外部清单，避免自引用。证据包含本机合成测试与首失败；真实RPC私有原文、账号数据及B未收到附件不随包。证据索引逐文件哈希；本机全量现场保留在 C:\AL23-*。

## 9. 升级与使用

两端都使用0.3.23（执行兼容门禁v8），先保留旧程序和本机数据备份，待正在执行的任务结束或明确中断后切换。从新目录启动AgentLink.exe，保留原连接配置。不要用新旧两版同时占用同一节点角色。

0.3.22旧结果可在64MiB受控限制内读取且不改写；但旧项目缓存没有源码/权限关联证明，不能自动发布，需核查原结果与当前基线。0.3.23新缓存不承诺被旧版读取；回退只使用保留的旧版与对应旧数据，不把新任务目录直接交给旧版续跑。恢复前须核验双方状态，未确定是否提交的请求不自动重发。导出待实际已保存再取文件。详细日志和手动证据核验用法见DEBUG-0.3.23.md。

## 10. 发布结论

本地候选测试版构建及本机检查完成。最终交付、源码对应和哈希结果见VERIFICATION；GitHub上传状态见UPLOAD-RESULT。**候选测试发行，FULL_ACCEPTANCE=false**：构建完成、本机通过不能替代真实双机、真实模型、B独立验收或远端发行完成。
