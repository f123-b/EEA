# Embedded Engineering Agent
## Transactional Event, Outbox & Recovery Specification V1.3

# 1. 目的

EEA 同时使用 SQL、Object Storage、Git、Vector Index、Workspace 与 EventBus。为了保证 Artifact Staleness、Knowledge Index、Job、Impact Graph 在进程崩溃或重启后仍一致，本规范定义事务边界、Outbox/Inbox、幂等消费和恢复扫描。

# 2. 原则

- SQL 是核心业务状态事务边界。
- 业务状态变化与 `outbox_event` 必须在同一 SQL transaction 中提交。
- InProcess EventBus 只是传输机制，不是持久化事实源。
- Consumer 必须幂等。
- Qdrant/搜索索引必须可从 SQL/Object 重建。
- Object/Git/Tool side effect 采用 prepare/commit/reconcile 模式，不假设分布式事务。
- 崩溃恢复必须显式，不允许“重启后看起来正常”。

# 3. Outbox

`outbox_events`：

- id / aggregate_type / aggregate_id
- event_type / payload
- project_id / actor_id
- created_at / available_at
- attempt_count / last_error
- status: PENDING/SENT/FAILED/DEAD
- idempotency_key
- trace_id / job_id

示例：

```text
BEGIN
  update engineering_claims
  insert engineering_dependency_edges
  insert outbox_events(ClaimUpdated)
COMMIT
```

Outbox Worker 负责投递 EventBus；投递失败重试，超过阈值进入 DEAD 并产生 Issue。

# 4. Inbox / Consumer Idempotency

`processed_events` 或 consumer inbox 保存：

- consumer_id
- event_id
- processed_at
- result_hash

每个 consumer 先判断是否已处理；任何可重放事件必须得到同一业务结果。

# 5. Artifact Creation Transaction

```text
Generate temp
→ Compute hash
→ Put object (idempotent/content-addressed)
→ SQL transaction:
     create artifact metadata
     create dependency snapshot
     create outbox ArtifactCreated
→ commit
→ consumers:
     impact propagation
     index/update
     UI event
```

Object put 成功但 SQL 失败：Object 成为 orphan candidate，由 GC 清理。

SQL 成功但 Event 未发送：Outbox Worker 重放。

# 6. Side Effect Journal

对于 Git commit、Flash、Build、external upload 等不可简单 rollback 的动作，记录 SideEffectJournal：

- operation_id
- intended_action
- target
- before_snapshot/hash
- after_snapshot/hash
- status
- compensation/recovery_action
- tool_run_id
- idempotency_key

# 7. Recovery Manager

启动或周期恢复：

1. reclaim expired resource locks
2. mark interrupted RUNNING jobs as RECOVERING/FAILED_NEEDS_RECONCILE
3. replay pending outbox
4. reconcile partial artifacts
5. detect orphan objects
6. verify Qdrant/index generation
7. reconcile Git workspace state
8. reconcile commissioning/hardware sessions
9. create Issues for unresolved inconsistencies

# 8. Vector Index

Qdrant 不是唯一事实源。每个 collection/index 保存 `index_generation`、schema version、embedding model/version、source snapshot。

支持：

- full rebuild
- incremental replay
- dual-index migration
- health verification
- stale index detection

# 9. Event Ordering

每个 aggregate/project event 带 monotonic revision/sequence。Consumer 遇到旧 revision 不覆盖新状态。跨 aggregate 不承诺全局严格顺序，依赖 graph 使用实体 revision/hash 判断。

# 10. Job Resume

Job checkpoint 必须区分：

- pure compute step：可重跑
- idempotent tool step：凭 idempotency key 重放
- external side effect：先 reconcile，再决定 resume
- hardware side effect：默认不自动 resume actuator enable

# 11. Acceptance

必须通过 crash injection：

- SQL commit 后、Event send 前 crash
- Object put 后、SQL commit 前 crash
- Qdrant update 中 crash
- Git patch 后、metadata 前 crash
- Job cancel 中 crash
- Resource lock holder crash

恢复后不能出现：
- 上游已变更但依赖永久 CURRENT
- 同一 Event 重复产生重复 Artifact
- index 与 scope 失配
- 重复 Flash/重复 destructive Git side effect
