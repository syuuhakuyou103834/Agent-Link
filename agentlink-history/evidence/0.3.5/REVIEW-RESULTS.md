# B评审采纳与本机补修结果

本轮交付0.3.5待验收候选，52个本机自动化用例通过；真实双机完整验收仍未完成。保留0.3.4原包、报告和封存证据。本轮实际执行补测、修复和打包，没有修改生产安装、共享目录或B电脑，没有发起真实模型请求。

## 采纳、补证与修复

- 采纳测试编号到用例、失败、请求台账、源码和ZIP哈希的关联要求：见 TRACEABILITY.json 及下表。
- T08三类准入、T17两个迟到成功结果窗口、T18原9种非法meta及合法对照、正常EXE启动/设置保留原本已有证据。本轮关联并在0.3.5回归，未把B未能读取证据误解为这些测试不存在。
- 新增重复继续/停止后继续、迟到错误、请求前取消、发布成功后确认丢失及反复故障恢复测试。迟到错误和重复继续未发现新缺陷。
- 新补充编号测试在0.3.4失败：同编号重投重复追加。0.3.5保存note_id收据，同编号同文幂等，同编号异文拒绝；不同编号相同文本保留。
- 新旧能力拒绝测试在0.3.4失败。0.3.5发起准入和接收入口检查 agentlink-safe-lifecycle-v1。缺失或非法能力声明时，本机拒绝执行。按协议能力判断兼容，不单靠版本号字符串。
- 修正证据工具：Windows输入文件CRLF与请求中的LF造成原索引仅23条关联。采用文本换行规范化后，原 **1228/1228条** 全部唯一关联；没有改写原始输入或请求台账。原索引的UNKNOWN是关联工具缺陷，不是缺失模型请求。

## 保留限定与明确失败

1. **混合版本整场零请求契约失败。** 实际加载旧0.3.4服务代码与新0.3.5服务代码，在本机隔离目录分别测试新A/旧B、新B/旧A。新版发起时零请求且无新场次；旧版发起时旧版先发1次初稿，新版接收方保持0次。新版不能改变未修改旧版的先调用行为。诊断脚本退出0表示观测完成，不表示混版验收通过。两次各1请求均为模拟。
2. 因此不能把“新版拒绝旧能力”写成“所有旧版/新版组合都能整场零请求”。这属于需要双方统一更新的兼容边界，不会降低原验收标准或追溯改判。
3. 本机故障注入只证明可控窗口下不重发/终态保护，不代替真实SMB中断、硬杀GUI/服务/进程树或实际沙盒隔离。
4. B本轮执行环境阻塞依其自报；A未独立核验B。B不能访问证据不否定A的本机实测，但双方验证状态必须分别记录。

## 用例与证据对应

| 编号 | 用例文件与名称 | 结果/修复前后 | 日志 |
|---|---|---|---|
| T08 | test_repairs.py：test_T08_running_duplicate_not_queued_and_request_id_replay_after_restart；test_T08_different_requests_simultaneous_admission_one_job_three_requests；test_T08_same_request_simultaneous_admission_one_job_three_requests | 已有修复重跑通过；终态后的合法新请求另见失败恢复每对中的正常场次 | evidence/205235-repairs.log |
| T17 | test_repairs.py：test_T17_stop_committed_before_result；test_T17_new_service_job_before_old_receiver_result | 两个成功结果屏障窗口通过 | evidence/205235-repairs.log |
| T17 | test_peer_review.py：test_T17_late_error_after_new_job_started_preserves_both_jobs | 新场次启动后释放旧错误；旧终态不变、新场正常完成、恰好5请求（旧2+新3） | evidence/205235-peer_review.log |
| T18 | test_repairs.py：test_T18_nine_invalid_meta_via_receiver_zero_claims_history_unchanged；test_T18_request_protocol_and_legal_control | 原9项非法meta及合法对照通过；scan_receiver和_perform调用同一validate_meta；请求入口另有严格协议/索引/文件名校验 | evidence/205235-repairs.log |
| T05 | test_peer_review.py：test_T05_note_id_replay_deduplicates_but_equal_text_new_id_preserved；test_T05_duplicate_resume_does_not_add_calls_or_revive_cancelled | 编号去重修复前失败（204546-peer_review.log），修复后通过；重复继续及停止后继续通过 | evidence/205235-peer_review.log |
| T11 | test_peer_review.py：test_T11_cancel_before_model_request_zero_send；test_T11_published_result_ack_lost_no_repeat | 请求前取消零发送；共享发布后丢确认保守失败且结果保留，只发送一次 | evidence/205235-peer_review.log |
| T11-T12 | test_gaps.py / test_faults.py：test_T11_claim_without_result_reports_uncertainty_zero_resend；test_T11_result_cached_shared_publish_fails_no_resend | 可能已发无结果、本机已保存共享未发布窗口通过；仍非真实共享断开/硬崩溃验收 | evidence/205235-gaps.log / 205235-faults.log |
| T07-T11-T12 | test_failure_recovery.py：test_T07_T11_T12_repeated_failures_then_valid_next_job | 新增故障恢复子集；24场48请求；每次下一场完成；讨论锁、角色锁和模拟进程清理通过 | evidence/205235-failure_recovery.log |
| T16-T18 | test_peer_review.py / package.py：test_T18_missing_safety_feature_rejected_in_both_directions | 0.3.4缺少前置能力拒绝，修复前失败；0.3.5本机拒绝通过；实际旧新服务混用整场零请求仍失败，见mixed-version-observation.json | evidence/205235-peer_review.log / package-verification.json |

完整结构化映射见 TRACEABILITY.json。本轮原始模拟请求索引共227条，唯一关联227条；包括修复前、开发补测、最终回归和混版诊断，不能当成单次最终回归调用总数。

## 最终代码回归与失败后恢复

最终回归日志批次205235：52个unittest用例全部通过，另有GUI和Windows Qt脚本通过。列表见 verification.json。混版两方向FAIL单列，不并入上述通过数量。

失败恢复先固定预热3对、测量9对：每对含一次超时/停止/发布失败，随后一次合法单轮。共12次故障加12次正常恢复，48次模拟请求；每个故障场次1次、随后正常场次3次。首末各3个测量对资源中位数增长阈值20%。

- 私有内存增长：0.46%；句柄增长：0.00%。
- 两个NodeService线程包含在测试进程统计内，加上两个当前模拟子进程；测试事件列表在采样前清空，避免把测试记录累积算作产品缓存。
- 每对释放讨论锁且下一场通过，旧终态不变；断开后角色锁可重新取得，所有已记录模拟进程退出。
- 原始结果：source/test-output/989164c538b34b7a89dcaff5bc1d92d8/recovery-result.json，同目录保留baseline、samples和请求记录。正常保持连接时的两个App Server进程不被误称为残留进程。

## 原0.3.4耐久的统计补证

重新核对110场的330次请求：逐场匹配job_id、step、role、thread_id、turn_id、台账行和请求ID，每步骤恰好一次。并检查发起方初稿先于其修订的本机请求顺序。见 evidence/prior-endurance-per-job.json。

增长确实使用 samples[10:30] 与 samples[90:110]，即去掉10场预热后的首末各20场中位数。重新计算内存2.12%、句柄0%，与原始结果一致。统计范围是含两服务线程的测试进程和两个模拟子进程。这是0.3.4原运行的补证，**不转记为0.3.5正常110场耐久实测**。

## 交付绑定

- 版本：0.3.5；Launcher FileVersion/ProductVersion实测0.3.5.0。
- ZIP：dist/AgentLink-GUI-0.3.5-Windows-x64.zip
- SHA-256：f41d6f085f3a299ae174b78b8c119a4de61ecf468fbf8e63ac4e2cd7ecffb7f1
- 123个包条目校验一致，包内两份app源码与本轮受测源码哈希一致。正常AgentLink.exe入口在隔离LOCALAPPDATA启动/关闭两次，设置哈希不变；预览与原生Qt检查通过。
- 旧0.3.4包哈希本轮复核仍为dbd97d62f10a5aea7ea296822f1fabb37e2d8b7493b2c5f47aea334971712754。旧版源码关键哈希也复核一致。

## 下一步与剩余工作

先由双方各自在本机部署相同候选并核对实际入口/角色/权限，禁止以旧新混用作为正式讨论环境；本轮只在工作区交付ZIP，未替换现用安装。B恢复本机工具后，开展真实双机SMB/共享中断、实际权限隔离、硬崩溃执行者隔离与T03/T04真实模型验收。时钟偏差/休眠、全部近同时取消等原覆盖表中的未完成项仍保留。0.3.5正常110场耐久未在本轮重复运行，需与发布验收计划明确绑定。

未核实全局模型预算，且未新增真实模型测试。原“最多9次”属于历史场次，不用模拟请求或本次工具次数倒推。
