# AgentLink GUI 0.3.20 完整开发日志

记录时间：2026-09-13T04:09:37.309207+08:00，Asia/Shanghai。代码提交：7f8ffa2d9e394db9398f172f2e4dc449923c7708。阶段时间以 evidence 中各次 results.json 的 started 和耗时为准；以下为工程行动汇总，不补造逐行修改的准确时间。

1. 基线与授权：用户确认按九项计划修改并发行；阅读 AGENTS、业务需求和发行规范。复制 0.3.19 已发布 source，保存 92 文件清单并提交 Git 基线。原始版本、审查快照不改。
2. B01 前置：建立外部 fixture output_root；当前测试脚本全部转向独立目录，legacy 历史不递归执行。runner 将临时目录放 --out 下，保留旧回执，不覆盖失败。
3. 首次复现：test_upgrade020 在旧行为下七项失败；另用原 0.3.19 源码独立复现 A03 权限、B01 越界尝试。保留 baseline-failures、baseline-A03.log、baseline-B01.log。
4. A01/A02：创建前持久意图，preparing/ready 门禁，提交时重读确认、停止、暂停、pending 和关联。可证明未发送的残留取消并留档；有 claim/call 的异常不自动回收。恢复子关联保留历史。发送管道写入与停止串行，等待模型时释放锁。
5. A03：集中权限矩阵，discuss 所有阶段只读；review 保留独立测试目录写入。未扩大源码、网络或外部工具范围。
6. A06：统一长路径 I/O/枚举；保持路径规范化和目录边界。后续运行时发现测试暴露扩展前缀不应存入用户配置，修正为 I/O 使用扩展形式、对外配置使用普通形式。
7. B03：候选文本只读，ledger 一次性绑定消息集合和摘要，输入状态通过账本投影；补齐代码、统一文本和兼容文本三条路径。预检失败保持 queued，确定未发送与发送不确定分别记录。旧排序测试原本依赖提前消费行为，更新为提交前重复构造不消费、提交后不重复。
8. A05/A04：诊断定位实际执行方，缺证据 UNKNOWN；成功清理本次暂存包；失败保留最多 2048 字符错误和快照标识，清理本次重复字节。清理失败单独记录，保留有效发布。
9. B02/构建：GUI 使用 __version__；C# 模板由构建脚本生成版本；启动器加 -B。更新 README、BUILDING、BR-020、DEBUG；保留旧版文档作为源码历史。
10. 实现首次检查：曾出现 import 放在 __future__ 前的语法错误，修正后七项及守卫通过；修复旧测试预期后继续完整回归。旧 0.3.10 文案断言改为实际 0.3.20 双端要求。所有失败日志保留。
11. 实际只读源：首次 ACL 通用写拒绝造成读取误拒绝，改为具体写权限。read_allowed/write_denied 探针通过。补修 runner 在 --out 已给定时仍探测不可写默认 TEMP 的问题。38 脚本完成；首次运行时路径表示失败修复后，最终完整重跑 38/38、219 次 unittest 执行通过，源码哈希未变。
12. 实际权限环境：第一次预检因生产 GUI settings 的锁文件不可写而阻塞；预检改为独立 Settings 和已安装 CLI，不依赖生产 GUI 设置。随后 3 个真实 thread/start 均因当前 Windows restricted-token 环境不能执行 split filesystem profile 而拒绝，无 turn/start。没有放宽 sandbox。
13. 崩溃补验：两个实际子进程在 context 和 ready 切点 os._exit(73)，新服务实例收敛为一个有效新任务，旧创建失败可追踪，claim/call 均为零。不是只用抛异常替代进程退出。
14. 构建与包内：Python 3.13.13 x64 / PyQt5 5.15.11 / Qt 5.15.2 构建便携 ZIP。先前候选整体移至 archives/candidate-first，保留首次包证据。最终包内 9 脚本、68 次 unittest 执行通过；实际 EXE Win32 标题、元数据、正常退出和进程树清理通过。
15. 来源核对：原版 92 文件未改；最终应用与只读受测副本、包内 app 完全一致。发行报告、日志和单独的崩溃检查按实际执行情况补齐，不宣称这些新增材料在较早冻结副本中执行过。
16. 发布：沿用 C:\AgentLink-GUI\dist 便携目录/ZIP、完整报告/日志、SHA256SUMS、VERIFICATION 和独立证据包。外部回执记录复制和 ZIP 的最终哈希。GitHub 只读探测 Forbidden，远端同步单独保留阻塞回执和后续执行材料，不写已上传。

本次所有模型测试请求为 0；离线请求是 subprocess mock。真实 SMB、双机、模型、B 独立复核、生产回退、100 轮耐久、安装器验收未执行。最终 FULL_ACCEPTANCE=false。

## 原始证据索引

- evidence/baseline-failures、baseline-A03.log、baseline-B01.log：原版九项复现。
- evidence/fix-first、fix-second、expanded-fixes、core-final、regression-first：实现中间失败和修复后检查。
- first-readonly / final-source：实际只读环境首次及最终完整回归。
- first-package / final-package：包内首次及最终回归。
- evidence/process-crash、native-package、native-final：进程退出、实际启动器及 Win32 标题。
- evidence/permission-preflight*.log 与公开 result.json：真实权限环境阻塞；private-rpc 保留本机。
- evidence/final-checks.json、readonly-acl-check.json、原始/只读源码清单：来源和只读证据。
- evidence/github-preflight.json：只读网络失败，无远端修改。

证据 ZIP 附带实际使用的核验脚本。唯一脚本数、unittest 执行数、复跑和模型请求分开统计，未将每个矩阵子场景或 mock 消息计为真实请求。
