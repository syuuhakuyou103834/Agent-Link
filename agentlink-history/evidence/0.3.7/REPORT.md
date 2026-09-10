# AgentLink 0.3.7：A 本机修复与剩余验收

已发现并修复一个上轮未覆盖的确定缺陷：0.3.6 宿主或执行服务被强制终止后，模拟工具子进程仍运行。0.3.7 的 A 本机回归通过；尚未获得 B 对本版的核验与完成意见，不能宣称两位 agent 已同意全部完成。

本轮只操作 A 获准工作区内的副本与独立测试进程，未替换在用安装、未改变 B 电脑、未操作生产共享。没有额外发起真实模型请求或子代理调用；11 次讨论调用的全局计数仍由外层调度掌握，模拟请求不能折算该预算。

## 修复及证据

| 项目 | 修复前 | 最终代码结果 | 证据 |
|---|---|---|---|
| T12 宿主／服务硬终止 | 0.3.6 两个窗口均留下仍运行的工具子进程 | 两窗口均退出；另测创建后归属前强杀宿主，暂停的服务也退出 | evidence/baseline-results.json → evidence/frozen-results.json；crash_probe.py |
| 启动归属与清理遗漏 | 根 PID 已退出时清理函数直接返回；宿主死亡不能执行 finally | 宿主 Job + 服务 Job；服务暂停创建后加入 Job 才运行；失败零接口请求；20 次启动/关闭句柄稳定 | source/tests/test_process_job.py；evidence/221929-process_job.log |
| T11–T12 四个持久化窗口 | 上轮无真实强杀记录 | 请求前 0 次，执行中／保存后／发布后各 1 次；重启均不重发，非终态阻止新场次，显式停止后新场各 3 次；旧终态不变 | evidence/frozen-restart-results.json；restart_probe.py |
| 自动化回归 | 沿用历史失败用例 | 最终冻结代码 67 个 unittest 测试执行全部通过；不是 T01–T19 整项通过数 | evidence/221929-checks.json；对应日志 |
| T19 最新候选耐久 | 早期本轮运行对应中间实现，保留但不计最终验收 | 最终代码 110 场、330 次；每场 A/B 顺序、步骤、turn ID 双向匹配；内存 4.18%，句柄 0% | evidence/final-endurance-index.json；source/test-output/end-1eeeed9d |
| 故障后下一场 | 不替代硬崩溃 | 最终 failure_recovery 12 对故障/恢复，共 48 次模拟请求；包含在 67 个测试中的 1 项 | evidence/221929-failure_recovery.log；测试原始目录 |
| GUI／Windows／ZIP | 首次包验证的 WMI 子进程发现超时 | 原生进程枚举重验：两次正常 EXE 启动、窗口、设置保留、进程退出通过；128 个包文件与解压一致 | evidence/package-first-failure.json；evidence/package-verification.json |

耐久沿用 10 场预热、100 场测量、首末各 20 场中位数、20% 阈值；统计为两个服务线程的宿主加两个模拟执行服务进程。宿主级 Job 句柄固定保留 1 个直到应用退出，预热后纳入统计。所有本轮原始日志及中间结果保留；最终验收仅采用 221929 批次和 frozen 命名的硬终止结果。

Job 句柄为私有且不可继承；宿主保护使子进程创建时即归属于保护范围，服务级保护负责独立关闭。它管理进程生命周期，不提供工具权限沙箱。由外部服务、计划任务或既有代理另行创建的工作不在本轮已测树范围内。实现依据 [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects) 及 [AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)。

## 交付与复跑

- ZIP：dist/AgentLink-GUI-0.3.7-Windows-x64.zip
- SHA-256：`5924f1d9164c30e12ca6d37abdc6d3bb46113a3a9e67460247402310fe2601e4`
- 源码与测试冻结映射：evidence/frozen-source.json；综合对应表：TRACEABILITY.json。
- 原 0.3.6 ZIP 当前哈希核对一致，未覆盖旧证据。
- 在本目录执行 `python run.py storage system context repairs faults gaps peer_review freshness authority process_job read_memory failure_recovery endurance gui windows_startup` 可运行回归；硬终止脚本只创建并清理其独立测试进程。再次执行时 crash_probe 的标签须为新值，restart_probe 也须使用新标签，以保留先前证据。
- 冻结源码对应现有 ZIP，未声称已经部署到任一正在使用的实例。

## 未完成项与 B 交接

| 剩余事项 | 当前状态／边界 |
|---|---|
| B 执行环境、版本与候选核验 | 本轮尚无 B 当前结果。历史缺少 codex-code-mode-host.exe 仅作为 B 先前自报，不当作当前已核验事实。A 无权修复对端。 |
| 真实双机 A→B→A、B→A→B 及 GUI 控制 | 未执行。当前讨论与本机模拟不能替代独立双向真实模型验收。 |
| 真实 SMB 竞争／中断与恢复 | 未执行。本轮四窗口使用本地文件和真实进程强杀，不是网络中断。 |
| 各节点实际允许／拒绝路径及对端提示注入 | 未完成。A 工作区写入成功不证明受限路径拒绝；未越过当前沙箱做禁止写入。 |
| 硬崩溃环境覆盖 | 本轮完成 A 本机服务宿主、执行服务及模拟工具子进程窗口；尚不等同真实 GUI 崩溃、真实 Codex 工具树及 B 节点验证。 |
| 兼容性 | 保留旧 0.3.4 发起混版失败。0.3.7 没有改协议字段，仍用 live-instance-v2，0.3.6 能通过能力检查但没有新进程保护。部署前要求双方使用 0.3.7；本轮未声称新增混版矩阵通过。 |
| T02 真实休眠／时钟、其他未执行子项 | 沿用未执行状态；不以本轮结果隐含通过。 |

B 下一轮重点核对本次确定缺陷、Windows 嵌套 Job 的本机兼容性、冻结源码与 ZIP 的对应；有执行能力时先验包及隔离硬终止测试。未具备真实双机或权限证据前，A 的结论是“本机新增修复及回归完成，完整双机验收未完成”。
