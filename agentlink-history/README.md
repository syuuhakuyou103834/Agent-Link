# AgentLink 版本源码归档

收录本机已有的 **0.3.0–0.3.10，共 11 个版本**，重点保留 0.3.4、0.3.9、0.3.10 的源码、构建文件、说明与测试。归档日期：2026-09-11。

`versions/<版本>/` 直接提取自该版本 Windows ZIP 中的 `source/`，文件字节未修改；来源 ZIP 的 SHA-256 和本机来源路径记录在 [provenance/versions.json](provenance/versions.json)。目录编号不是 Git 历史重建，也不代表每版都已通过真实双机验收。

| 版本 | 源码目录文件数（含说明和测试） | tests/ 文件数 |
|---|---:|---:|
| [0.3.0](versions/0.3.0/README.md) | 17 | 5 |
| [0.3.1](versions/0.3.1/README.md) | 20 | 7 |
| [0.3.2](versions/0.3.2/README.md) | 22 | 8 |
| [0.3.3](versions/0.3.3/README.md) | 23 | 9 |
| [0.3.4](versions/0.3.4/README.md) | 25 | 10 |
| [0.3.5](versions/0.3.5/README.md) | 29 | 15 |
| [0.3.6](versions/0.3.6/README.md) | 30 | 16 |
| [0.3.7](versions/0.3.7/README.md) | 33 | 18 |
| [0.3.8](versions/0.3.8/README.md) | 34 | 19 |
| [0.3.9](versions/0.3.9/README.md) | 35 | 20 |
| [0.3.10](versions/0.3.10/README.md) | 40 | 25 |

## 主要版本关系

| 版本 | 主要内容 | 已知边界 |
|---|---|---|
| 0.3.4 | 无时限等待、执行活动显示、未完成输出导出、协议 2 历史续接 | 缺少后续 0.3.9 的部分进程归属及执行锁保护 |
| 0.3.9 | 加强 Windows Job、执行锁、清理失败、实例绑定及时效校验 | 曾回退 0.3.4 的部分长等待、展示及历史能力；是整合前冻结版本 |
| 0.3.10 | 整合 0.3.9 的保护与 0.3.4 的有用功能；恢复设置迁移、活动显示、部分导出与历史续接 | 两端需使用兼容版本；真实双机、SMB 中断及实际权限验收仍未完成 |

详细依据：[0.3.4 与 0.3.9 独立比较](evidence/0.3.4-vs-0.3.9/REPORT.md)、[0.3.10 整合报告](evidence/0.3.10/REPORT.md)、[0.3.10 修改说明](versions/0.3.10/DEBUG-0.3.10.md)。

## 从源码运行与构建

在 Windows x64、Python 3.13 环境中，为开发安装 PyQt5 5.15.11，然后切换到所需版本，例如：

```powershell
cd agentlink-history/versions/0.3.10
python -m pip install PyQt5==5.15.11
python main.py
# 构建需要 Windows 自带 .NET Framework C# 编译器：
python packaging/build.py --zip-only
```

应用实际使用本机已登录的 Codex。源码归档不附带 Python/PyQt/Codex 二进制、账号登录文件、生产设置或用户讨论数据库。

历史文件按原始字节保留，包括部分 `BUILDING.txt` 遗留的旧版本标题。版本身份以 `app/__init__.py` 和来源清单为准；没有为了上传改写历史源码。

## 测试与证据

常规测试在各版本 `tests/` 中，例如从版本目录运行 `python tests/test_storage.py`、`python tests/test_system.py`。`check_real_protocol.py` 需要本机 Codex，`smb_probe.py` 需要明确的共享测试目录；它们不是可无条件批量运行的离线测试。

本次上传准备只进行来源、哈希、文本和 Python 语法检查，未重跑应用验收，也未新增真实模型请求。

- 0.3.10 原整合批次：19 个脚本入口通过，其中 16 个 unittest 入口共 90 项；耐久 110 场、330 次模拟请求。见 [最终批次](evidence/0.3.10/20260911-023032/results.json) 和 [耐久结果](evidence/0.3.10/endurance-result.json)。
- 早期失败及中断日志一并保留，不能与最终通过批次混计。
- `evidence/0.3.6-acceptance/` 保存 ZIP 之后的补充测试版本，与 `versions/0.3.6/` 冻结源码分开。
- `evidence/` 中的历史运行器可能引用原本机绝对路径，需要据实际目录调整。报告提到的完整原始日志集合仍在原机，本归档收录测试源码、报告及选定结果，不冒称包含全部原始证据。
- 源码与已有日志通过本机核验不等于真实双机、真实 SMB 或 B 节点独立验收通过。

在归档根目录运行 `python tools/verify_archive.py` 核验全部归档文件。`SHA256SUMS.json` 对除清单自身以外的文件逐一计数与校验；原始文件另有 [provenance/files.json](provenance/files.json) 记录来源。
