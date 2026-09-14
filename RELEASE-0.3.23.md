# AgentLink 0.3.23 交付报告

本地候选测试版构建及本机检查完成。2026-09-14T11:51:28+08:00（Asia/Shanghai）。**FULL_ACCEPTANCE=false**。远端 GitHub 发行阻塞；本地交付以外部 VERIFICATION-0.3.23.json 的回读结果为准。

## 1. 版本与来源

基线 v0.3.22 / 892e7532e7d6ac920f09eedb2b302c99a30793bb；独立开发目录 C:\AgentLink-upgrade-20260914\source，分支 codex/agentlink-0.3.23。最终提交和逐文件摘要见外部 VERIFICATION。用户已纠正编号并授权按 0.3.23 路线实施与发行。路线原件 C:\AgentLink-plans\0.3.23\UPGRADE-ROADMAP.md。

输入 .22 AgentLink-handoff.md SHA256 为 67a2452c2ff2d8c4d5912141b9871d32ef9ea46abefaa7185a4b36a455e3fea8。原 .22 源码115文件（含后加入交接文件）逐文件复核不变。环境 Windows x64、Python 3.13.13、PyQt5 5.15.11、Qt 5.15.2；使用已有本机运行时及 C# 编译器构建。

## 2. 业务范围与验收

对应 source/docs/BUSINESS-REQUIREMENTS.md 中 BR-023 / AC-023-01～08。完成五项 P2 的代码或夹具修复、三类已返回结果恢复、异步导出和详细日志、手动原证据包校验工具、同形式候选发行。未扩展正式协作轮数，未默认抓包、上传日志或唤醒模型。没有删除已公开功能；结果格式和恢复前提有变化，见第9节。

## 3. 变化与问题对应

| 问题/要求 | 最终行为 | 本机验证 |
|---|---|---|
| A022-01 null缓存 | 不存在/null/损坏/错归属/未提交/已返回但缺失分别处理；异常阻塞新执行，原件保留 | test_results023 与既有恢复回归 |
| A022-02 8MiB规则不一致 | 独立64MiB正文、小回执64KiB、摘要/长度校验；旧schema1专用读取；同结果幂等，异结果拒绝覆盖 | 超8MiB Unicode、损坏、重复保存、超限保留、拒绝访问 |
| A022-03 测试深路径 | 测试专用扩展路径I/O、清理范围校验，补齐rename/ZIP/枚举；不全局修改产品shutil | 最终中文深目录全套45脚本 |
| B022-01 GUI导出 | UTF8 BOM、同目录暂存后原子替换、独立线程，实际成功才提示已保存；关闭等待已接受写入 | 深路径/替换失败/慢写和GUI测试 |
| B022-02 详细日志 | 独立有界异步通道、扩展路径、轮转和截断、写入失败/丢弃计数可见 | 深路径/失败注入；业务错误仍保留 |
| 已返回未发布恢复 | 项目/正式文本/澄清复用本机校验结果，无重复阶段模型调用；项目额外核对源码与权限关联 | test_reuse023 五项；源码改变拒绝复用，聊天已提交不重复追加 |
| 原始附件接收 | Verify-Evidence.cmd核验用户明确交付的同一原ZIP及逐文件摘要；不执行/解压 | 有效/错误SHA/不安全条目合成包测试 |

缓存原始正文先落盘，再登记项目关联证明。新证明写入失败会保留答案并阻塞自动发布；这不能宣称所有崩溃都可自动恢复。文件读写容量受控，不宣称无限或常量内存解析。

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

## 5. 证据分层

| 层级 | 状态 |
|---|---|
| 本机单元/模拟与路径回归 | 通过上述最终套件 |
| 本机GUI与实际便携EXE | 隔离启动、Win32标题、正常退出/受控进程树清理通过；PE manifest及文件版本0.3.23.0通过 |
| 包内运行时 | 上述脚本通过；源码/应用/ZIP一致性由封存器回读 |
| 真实SMB | 本轮只读预检 Access denied，未写共享目录 |
| 真实模型 | summary/review/implement会话初始化均被Windows受限令牌沙箱拒绝；turn/start=0；未测试真实工具执行 |
| 真实双机/B独立验收 | 未执行；本机模拟B不等于独立B |
| B原始附件 | 未收到SHA为8c78e6c8191ead92d42cecee9b9540bfc0cafdaf5771c3552d71ff16f0cfe7af的原ZIP；未建立原始接收证据 |
| 安装器/旧任务升级 | 便携形式不生成安装器；未代操作用户运行中任务或验证真实旧会话迁移 |
| GitHub | 本轮正常gh repo view返回Forbidden；未上传/未核对远端tag资产 |

## 6. 计数口径

脚本数不是唯一用例数；unittest计数按每脚本实际footer求和，含复跑/组合继承，不能累计宣称唯一用例。短、深、包和专项分开。正式轮数规则不变；缓存复用记录new_model_requests=0，仍会核验并获取步骤执行资格，不能把有效复用称claim=0。所有本机回归使用mock；真实turn/start为0。无自动新增模型轮数。

## 7. 已知限制与后续验证

B需在自己的机器交付原附件与回执、运行同一源快照并记录独立读取/实际测试范围；本版工具只核验本机文件，agent_read/tests_executed仍为false。Python3.14、杀毒误杀原事故、真实SMB中断重连、双机并行冲突、模型权限及已返回未发布恢复还需真实验收。不能从空闲AppServer存活推断旧任务仍执行。详细日志磁盘失败/队列满时无法保证持久化；本版显示健康状态，不能从缺日志判断未请求模型。已检查本机Windows GUI截图，主操作和版本可见；测试窗口宽度下左侧品牌文字有裁切，本轮未调整布局，不宣称所有缩放比例均视觉验收。

## 8. 交付清单

C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.23：AgentLink.exe、runtime、app、source（含tests/packaging/docs）、licenses、README、DEBUG、RELEASE和DEVELOPMENT-LOG。同级提供 Windows-x64.zip、独立报告/日志、AgentLink-0.3.23-Verification-Evidence.zip、SHA256SUMS-0.3.23.txt、VERIFICATION-0.3.23.json、UPLOAD-RESULT-0.3.23.json。最终ZIP哈希只在外部清单，避免自引用。证据包含本机合成测试与首失败；真实RPC私有原文、账号数据及B未收到附件不随包。证据索引逐文件哈希；本机全量现场保留在 C:\AL23-*。

## 9. 升级与使用

两端都使用0.3.23（执行兼容门禁v8），先保留旧程序和本机数据备份，待正在执行的任务结束或明确中断后切换。从新目录启动AgentLink.exe，保留原连接配置。不要用新旧两版同时占用同一节点角色。

0.3.22旧结果可在64MiB受控限制内读取且不改写；但旧项目缓存没有源码/权限关联证明，不能自动发布，需核查原结果与当前基线。0.3.23新缓存不承诺被旧版读取；回退只使用保留的旧版与对应旧数据，不把新任务目录直接交给旧版续跑。恢复前须核验双方状态，未确定是否提交的请求不自动重发。导出待实际已保存再取文件。详细日志和手动证据核验用法见DEBUG-0.3.23.md。

## 10. 发布结论

本地候选测试版构建及本机检查完成。最终交付、源码对应和哈希结果见VERIFICATION；GitHub上传状态见UPLOAD-RESULT。**候选测试发行，FULL_ACCEPTANCE=false**：构建完成、本机通过不能替代真实双机、真实模型、B独立验收或远端发行完成。
