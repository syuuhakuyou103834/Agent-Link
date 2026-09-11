# A 节点 0.3.15 只读交接

本轮仅封存源码并进行有限本机检查，未修改原源码，未执行修复。B 尚未独立接收或验证；由系统自动打包交接，A 未操作实际通信目录。

## 完整快照与完整性

- 原目录：`C:\AgentLink-GUI\dist\AgentLink-GUI-0.3.15\source`
- `source-snapshot/` 为全部 57 个文件的原样副本，共 411615 字节；包含 app、tests、packaging 及根目录文档。未发现重解析点。
- `source-snapshot.zip` SHA-256：`4b2502517a452ba71f51184d543e443da7220ea657557ab115662d26acfc3a6a`
- `source-manifest.json` 记录每个文件的相对路径、大小、SHA-256。
- `evidence/snapshot.json` 与 `evidence/final-integrity.json` 记录复制一致及结束时原源码、快照哈希未变。完整性结论限定于指定 source 目录，不代表构建环境或外部证据已交付。

## 本轮实际检查

Python 为本机 `C:\Program Files\Python\python_3.13\python.exe`，版本 3.13.13；PyQt5 可发现，未验证其运行或版本。rg 不可用，使用 PowerShell 只读搜索替代。未安装依赖或申请权限。

测试仅在 `test-worktree/` 副本运行，设置 PYTHONDONTWRITEBYTECODE=1、PYTHONIOENCODING=utf-8、TEMP/TMP 指向本轮 scratch/test-temp。测试创建的 Mailbox 是 scratch 内临时夹具，不是实际通信目录。命令：

```powershell
& 'C:\Program Files\Python\python_3.13\python.exe' test-worktree\tests\test_context.py
& 'C:\Program Files\Python\python_3.13\python.exe' test-worktree\tests\test_storage.py
```

| 检查 | 结果 | 证据 |
|---|---|---|
| 46 个 Python 文件 ast.parse | 通过 | evidence/static-checks.json |
| test_storage.py | 6/6 通过，退出码 0 | evidence/test_storage.py.log |
| test_context.py | 2 通过、6 ERROR，退出码 1 | evidence/test_context.py.log |
| 原源码与封存快照哈希复核 | 通过 | evidence/final-integrity.json |

日志由 PowerShell 重定向保留，包含 NativeCommandError 包装及 Python traceback；退出码单独保存在 `evidence/test-results.json`。未自动重跑失败测试。

## 发现及交 B 复核事项

**A-OBS-001：上下文测试清理失败（待定性）。** 6 个 ERROR 均发生在 tempfile.TemporaryDirectory.cleanup → shutil.rmtree → os.rmdir，错误为 WinError 145（目录不是空的），路径位于本轮 test-temp 下的 local/runs 子目录。当前日志未报告断言失败，但整套测试应判失败，不能据此宣称上下文测试通过。清理失败是否由路径长度、文件句柄、权限环境或其他原因导致尚未建立证据；不得直接认定产品上下文逻辑缺陷。原失败目录保留供复核。

B 应首先独立核对源码清单与哈希，再阅读源码、审查运行副作用并选择本机可行测试；尤其复核上述失败及 0.3.15 新增定向输入、恢复、快照验证和会话归属逻辑。本报告不替代 B 的独立审查，不要求绕过权限或补装依赖。

## 未验证与阻塞边界

未执行完整回归、GUI、构建、耐久、真实 Codex 接口、真实模型、SMB、双机或恢复验收。本轮模型请求 0。真实网络测试受 network.enabled=false 限制；B 独立结果尚待交接。未发现阻塞本轮两套本机测试的缺失依赖；其他测试依赖尚未逐项验证。源码 DEBUG 文档中的历史通过数字和外部证据路径未作为本轮证据，亦未访问该范围外证据目录。

未确立产品缺陷或修复范围。后续由 B 提交独立报告，A 再汇总并等待用户决定修复范围。

unrelated_issues: []
