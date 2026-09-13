# AgentLink 0.3.22 开发日志

执行者：本机 Codex；测试 B 为本机模拟服务，不是独立 B 审查。环境 Windows x64 / Python 3.13.13 / Qt 5.15.2；时间为 Asia/Shanghai。日志记录公开工程行为，未将用户授权实现等同于验收通过。

## 按实际时间记录


- 2026-09-13T23:40:24+08:00 | 本机 Windows / Python 3.13.13 | BR-022：用户批准实施七项修复、恢复入口、最小诊断及 0.3.22 发行；克隆独立分支 codex/agentlink-0.3.22；封存 0.3.20/0.3.21 发行源码哈希与输入回执。原始 B005 ZIP 未独立收到，本机复现另计。

- 2026-09-13T23:41:57+08:00 | 本机 Windows / Python 3.13.13 | 复现：C:\AL22-before 六项定向负例全部按预期失败；P1 独立进程获得租约时旧 mock 子进程仍活，计时/索引/暂存问题均本机复现。首轮探针 GBK 解码噪声保留并改为 UTF-8。实现 P1：租约先登记到服务，记录写入纳入 try，清理无论成功与否都复位 chat_active，只有确认清理后释放租约。

- 2026-09-13T23:49:39+08:00 | 本机 Windows / Python 3.13.13 | 阶段 2/3：心跳故障改为分通道累计、本机经过时间；已有证据使用外部提交记录和完整校验，首次创建暂存提交；重复快照复用原始 ZIP 并回收本次暂存。C:\AL22-core2 定向回归全部通过。core1 暴露新提交目录未创建，已修正，首轮日志保留。

- 2026-09-14T00:01:12+08:00 | 本机 Windows / Python 3.13.13 | UI 共享问题读取拒绝访问已本机注入复现（gui-issue-before），改为服务线程读取及格式检查；恢复按钮和精确别名已加入。补充有界异步运行诊断、原始接收包只读交付与 v7 双端门禁。GitHub gh repo view 返回 Forbidden，远端同步阻塞，未绕过网络限制。

- 2026-09-14T00:05:24+08:00 | 本机 Windows / Python 3.13.13 | 新增边界测试全部通过：stability 11、GUI 3、审查回归 6、清理门禁 2；深路径首批五脚本通过。耐久完成 110 任务/330 mock 请求，内存中位数增长 3.101%，句柄 0%。真实 Codex 三种权限预检均被 Windows sandbox 初始化拒绝，turn/start=0；默认 SMB 只读访问拒绝。以上限制已保存，未降级权限或绕过。

- 2026-09-14T00:21:33+08:00 | 本机 Windows / Python 3.13.13 | 最终全套 C:\AL22-final 43 脚本全部通过；最终耐久 110 任务/330 mock 请求，内存中位数 +3.7831%，句柄 0%。最终六项回归应用于未改 0.3.21 均按预期失败；首次补查因 unittest 未注册模块导致零测试，保留日志并修正外部验证助手。更深路径暴露模拟服务器两处内置 open 未加扩展路径，及产品 stderr 文件普通路径丢失诊断，均修正；保留 deep20 与 deep20-fix 原始失败，五脚本 deep20-final 复测通过；重新执行封存前全套。

- 2026-09-14T00:30:03+08:00 | 本机 Windows / Python 3.13.13 | 封存前检查完成：最终完整源套件 43 脚本通过；包内 10 脚本通过；实际 EXE 隔离启动/标题/退出/进程树清理通过；PE 内嵌 manifest 与 FileVersion/ProductVersion 均为 0.3.22.0。已查看恢复界面截图，中文布局及按钮正常。GitHub 远端保持 Forbidden 阻塞，准备本地候选交付和完整哈希核对。

- 2026-09-14T00:30:03+08:00 | 封装阶段 | 生成同版报告与日志；源套件 43 脚本通过；包内与实际 EXE 验证通过，准备封存本地候选。

## 逐项实现与证据

| 阶段 | 起因与实现 | 验证 / 状态 / 下一步 |
|---|---|---|
| 封存 | 独立克隆 .21，保留原 .20/.21 源码和 handoff；记录计划及基线哈希 | evidence/baseline-020.json、baseline-021.json、input-receipt.json、020-to-021-files.txt；B005 ZIP 接收仍未建立 |
| B021-01 | conversation 的 finally 先 close 导致后续租约和状态丢失；改为立即登记、统一清理、持久化未确认状态、进程身份核对 | AL22-before / AL22-p1 / regression、cleanup、stability；真实模型进程退出未验收 |
| A021-03 | 普通轮询清 share_lost；改分通道、同一经过时间源、对应成功恢复 | core2 及 liveness_io021；40 秒模拟交错失败与正对照；真实 SMB 故障未执行 |
| A021-01 | 旧索引丢失/null 被补写；改提交标记、先前引用与完整校验 | core1 首次漏建 .committed 父目录失败；修正后 core2 / regression / context_view / stability 通过 |
| A021-02 | 相同包重复 staging 留存；改原包校验复用和本次暂存 finally；接收保留一份有意原始审查包 | regression / projects / stability；故障证据置于暂存外，接收回执区分服务与 agent |
| A021-04 | 独立 fs 包装测试操作和模拟服务；补产品 stdout/stderr 长路径日志 | 首次 helper 造成 CRCRLF，修正换行；mock runpy 需 tests 路径导入 fixture_paths；deep/deep20 首次失败保留，deep20-final 五脚本通过 |
| B021-02 | connected 不等于 challenge ready，旧耐久仍由 B 发起；等待实例挑战并 A 发起 | endurance1 与 endurance-final 各 110 任务/330 mock 请求独立保存，不混计；最终资源增长合格 |
| B021-03 | 文案/manifest 写死旧版本；从统一 app 版本构建 | 维修脚本仅解析语法、未执行维修；实际 EXE 资源/标题检查见 native-* |
| 恢复/诊断 | 共享 issues 同步 UI 读取注入 PermissionError；改 worker 命令；精确恢复按钮/别名、异步有界诊断 | gui-issue-before / ui022 / stability；慢写/失败只影响诊断健康计数；用户现场未操作 |
| 结果保存 | 清理前本机保留已返回答案；拒绝覆盖不同结果；明确恢复可读取原件 | stability 与正式/聊天回归；原件未验证不自动升级为发布成果，不自动重发不确定请求 |
| 真实预检 | 三种 Codex thread/start sandbox 初始化拒绝，SMB 只读拒绝，GitHub API Forbidden | 实际 model turn/start=0，未绕过策略；完整验收/上传阻塞 |
| 最终回归 | 全套、深路径、耐久、包内、原生 EXE 分开执行 | 各 complete/results、stdout 与 PID 清理记录；后续真实双机矩阵待测试机执行 |

## 历史失败与超时逐项对应

这是 B 报告与本轮测试的对应表，不是事后改写 B 日志。B 原始 ZIP 未收到，无法给全部历史失败下唯一根因结论。

| B 历史脚本 | B 记录 | 本轮结果/秒 | 归因边界 |
|---|---|---|---|
| test_context.py | 失败 | passed / 0.43 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_integration_upgrade.py | 失败 | passed / 3.11 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_peer_recovery.py | 失败 | passed / 37.41 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_projects.py | 失败 | passed / 0.36 | 已确认普通路径夹具会误报/阻止注入；本轮短/深路径均通过；不代表原 WinError 145 全部归因 |
| test_review_fixes.py | 失败 | passed / 0.96 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_system.py | 失败 | passed / 34.02 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_waiting.py | 失败 | passed / 11.92 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_code_gui.py | 超时 | passed / 6.76 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_code_workflow.py | 超时 | passed / 24.3 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_context_workflow.py | 超时 | passed / 44.35 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_conversation.py | 超时 | passed / 80.33 | 本轮单脚本约 80 秒，超过 B 首轮 60 秒上限；仅支持上限可贡献超时，不证明所有超时原因 |
| test_intervention.py | 超时 | passed / 21.23 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |
| test_review_fix_integration.py | 超时 | passed / 10.41 | B 原始日志未收到，全部历史根因未建立；保留首次记录 |


## 运行索引与首次失败

- `C:\AL22-before`：未改 .21 的六项失败；`AL22-p1`：P1 修复后及其余待修；`AL22-core1`：提交目录遗漏；`AL22-core2`：定向通过。
- `AL22-workflows1`、`AL22-integrated2`、`AL22-new-boundaries1`：阶段性工作流/边界；`AL22-full1` 和 `AL22-final`：中间完整回归，后续又修长路径日志/mock 写入，不冒充最终冻结树。
- `AL22-deep`、`AL22-deep20`、`AL22-deep20-fix`、`AL22-deep20-final`：逐渐加深目录、首次失败/诊断恢复/最终通过；每次独立目录。
- `AL22-baseline-recheck`：辅助 unittest 模块错误，0 测试，无效；`AL22-baseline-recheck2`：最终六回归用于旧源码，6 个真实失败。
- `AL22-sealed-source`：最终 43 脚本；`AL22-package`：包内运行时；`AL22-endurance-final`：最终耐久；实际 launcher 见 `evidence/native-final`。
- `AL22-real-preflight`：三次真实预检被拒绝；公开仅 result.json，private-rpc 原始日志留原机。真实模型请求为零。

原始测试命令由 results.json 保存；发布助手 release.py、原生校验助手和 journal 随证据包提供。首次日志不覆盖；整理后的报告不能替代原始证据。构建、SHA、源码对应、Git 提交/tag 和本地交付终态在外部 VERIFICATION 中核实；远端上传状态单独在 UPLOAD-RESULT 记录。
