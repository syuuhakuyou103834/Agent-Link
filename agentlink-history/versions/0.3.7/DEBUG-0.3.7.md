# 0.3.7 进程生命周期修复

0.3.6 的 stop_process_tree 在根进程已退出时直接返回，且宿主崩溃不会执行 Python 清理。两个隔离硬终止测试均留下仍运行的模拟工具进程。

修复使用 Windows Job Object：宿主级私有句柄覆盖进程创建窗口，保留到进程退出；服务级句柄覆盖单个执行服务及其后代，出错和断开时关闭，即使根 PID 已退出也清理。服务以 CREATE_SUSPENDED 创建，加入服务 Job 后恢复初始线程，避免启动代码提前创建未归属的工具进程。归属、线程识别或恢复失败时不发送 initialize/thread/start/turn/start。

依据微软文档：https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject

范围是本机进程及其正常派生子进程；由外部服务、任务计划或其他既有代理另行创建的工作不属于已测进程树。Job 不是权限沙箱，不能代替各节点实际权限验收。宿主进程所属 Windows Job 不兼容时连接失败，不降级为无保护执行。宿主句柄在正常断开后保留一个，直到应用退出；资源测试先预热后比较。

没有改变讨论协议或混版拒绝规则；双方应部署 0.3.7。既有 0.3.4 发起混版失败继续保留。本轮未替换在用安装。
