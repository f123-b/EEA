# Embedded Engineering Agent
## Resource Budget, Lock & Execution Specification V1.3

# 1. 目的

EEA 会执行 LLM、Repo Clone、Build、Simulation、Hardware Debug、Instrument、Search，必须控制成本、并发、独占资源和 runaway job。

# 2. Budget 类型

TokenBudget、LLMCostBudget、RuntimeBudget、RepoSizeBudget、CloneBytesBudget、CandidateBudget、DeepAnalysisBudget、ParallelismBudget、ToolRuntimeBudget。

示例：

```yaml
name: repository-discovery-default
max_candidates: 20
max_shallow_analysis: 10
max_deep_analysis: 3
max_clone_bytes: 500MB
max_llm_tokens: 300000
max_runtime_minutes: 30
max_parallelism: 4
```

# 3. OSDLE Budget Gate

Search → candidate metadata → score → budget check → shallow → score → budget check → deep。低分候选不进入 Deep。

# 4. Resource Types

DebugProbe、SerialPort、CANInterface、Instrument、SimulatorInstance、HardwareTarget、GitDestructiveSection。

# 5. ResourceLock

字段 resource_type/resource_id/owner_job_id/owner_session/acquired_at/heartbeat_at/lease_expires_at/status。

协议：Acquire → Validate → Execute → Heartbeat → Release。lease expiry 后可回收；force release 必须 audit。

# 6. Hardware Identity

Flash/Debug 锁不应只基于 COM 名，尽量使用 probe serial、target id、USB VID/PID、port path、detected MCU identity。

# 7. Job Cancellation / Retry

取消时 signal tool、terminate sandbox、release lock、flush logs、mark partial outputs、no duplicate side effects。资源忙返回 BLOCKED_RESOURCE，不做高频抢占重试。

# 8. Scheduler

V1.3 可单进程，但必须支持 priority、resource requirement、budget、cancellation、fairness；后续再拆 Worker Queue。

# 9. Usage Accounting

Job 保存 tokens/model cost/repo bytes/tool runtime/wall time/peak parallelism。超预算返回 BUDGET_EXCEEDED，不能静默继续。

# 10. Acceptance

Budget 超限及时停止；同一 probe 不并发；cancellation 释放 lock；app crash 后 lease 可回收；OSDLE 不无限 deep analyze。

# 11. Sandbox Budget

Sandbox Foundation / Hardening 同样受 ToolRuntimeBudget、RepoSize/CloneBytes、CPU/RAM/process/network policy 控制。任何外部 Repo、Learning Document extraction helper、Build Script 超预算都必须中止并保留 partial result，不静默继续。

# 12. Hardware Safe Cancellation

Hardware Job cancellation 必须执行 SafetyState/EmergencyStop policy、记录结果；状态未知时 quarantine HardwareTarget。Flash 与 Actuator Enable lock/permission 分离；Lock loss/heartbeat timeout 不允许继续高风险输出。
