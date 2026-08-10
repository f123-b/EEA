# Embedded Engineering Agent
## Non-Functional Requirements & Reliability Specification V1.3

# 1. 范围

定义性能、可靠性、恢复、可观测性、容量、数据完整性和安全降级指标。功能正确但无法恢复、资源失控或大项目不可用，同样不能 Release。

# 2. Reliability SLO

V1.3 单机目标：

- 核心项目元数据写入：无静默丢失
- Outbox pending event：重启后可恢复
- Job crash：进入 RECOVERING/FAILED_NEEDS_RECONCILE，不长期 RUNNING
- ResourceLock：lease 到期可恢复
- Artifact：content hash 校验
- Qdrant：可重建，不作为唯一事实源
- Project export/backup：可验证恢复

# 3. Capacity Profiles

定义 minimal / foc-dev / full / ci profile 的：

- maximum project file count
- repository size
- document size/page count
- concurrent jobs
- vector entries
- log retention
- object storage quota
- maximum single tool runtime

超限必须返回明确错误或 Degraded Mode，不允许 OOM/无限等待。

# 4. Performance Benchmarks

至少记录：

- cold start
- project open
- search latency
- API p50/p95
- event propagation latency
- pin validation latency
- build queue latency
- large repo import
- large PDF parse
- ContextBuilder retrieval latency
- UI large-list rendering

性能阈值由 release profile 固化，可随版本调整但必须有回归基线。

# 5. Failure Injection

CI/Benchmark 加入：

- process kill
- DB locked
- disk full
- object write failure
- vector DB unavailable
- LLM timeout/rate-limit
- tool missing
- sandbox crash
- corrupted cache
- network unavailable
- resource lock holder crash
- WebSocket disconnect/replay failure

# 6. Backup / Restore

Project Export 必须包含 manifest/hash/schema versions/source revision/required object refs/knowledge snapshot refs。Restore 做 compatibility validation、hash verify、migration dry-run。

# 7. Observability

Structured log + metrics + traces 统一关联：

request_id / project_id / job_id / agent_run_id / tool_run_id / import_run_id / commissioning_session_id / event_id / source_revision。

禁止敏感内容进入普通日志。

# 8. Renderer/Desktop Security NFR

Tauri/WebView：

- CSP
- sanitize untrusted Markdown/HTML
- deny arbitrary remote navigation
- external links isolated
- minimal Tauri capability allowlist
- no token exposure to untrusted rendered content
- no arbitrary remote JS extension
- localhost backend auth mandatory

# 9. Team Identity NFR

服务端模式必须具备 User/Organization/Membership/ProjectRole 的稳定身份边界；所有 Audit/Permission/Promotion/Export 记录 actor identity。Project/Knowledge/Vector/Object scope 均能映射到 authorization context。

# 10. Canonical Unit NFR

工程计算统一 canonical unit/dimension normalization。输入可接受 V/mV/kV 等表示，但 Rule/Claim/Equation 比较使用标准单位和 dimension；非法 dimension 直接拒绝。

# 11. Release Gate

不存在未经说明的 P0；所有 hard gate skip 必须标 FAIL/SKIPPED，不得转 PASS。性能退化超过阈值需 Release Report 说明。
