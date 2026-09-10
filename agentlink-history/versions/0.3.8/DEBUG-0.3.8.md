# 0.3.8 清理错误与实例隔离

0.3.7 注入 CloseHandle 失败后未检查返回值并清空句柄，遗漏错误处理。0.3.8 先 TerminateJobObject，再 QueryInformationJobObject 确认 ActiveProcesses 为零，最后检查 CloseHandle 返回值；任一失败均报错并保留句柄。RpcClient 标记 cleanup_pending，阻止 start/run_turn；NodeService 拒绝新场次准入。明确断开并成功清理后才可重新连接。

新增 terminate/query/close 失败和活动进程等待超时用例；覆盖同宿主另一服务、同机独立宿主及无关哨兵进程不受目标清理影响。保留宿主级保护、暂停创建和服务级保护。此机制是生命周期管理，不是工具权限沙箱。

协议能力仍为 live-instance-v2；新旧混版未新增安全保证。双方部署本候选后才能验证双节点行为。真实双机、SMB 中断、实际权限及 B 环境仍待独立验证，现用安装未替换。

API依据：
https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-terminatejobobject
https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-queryinformationjobobject
