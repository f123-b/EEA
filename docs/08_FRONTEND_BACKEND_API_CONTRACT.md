# Embedded Engineering Agent
## Frontend / Backend API Contract V1.3

Base REST：`/api/v1`  
WebSocket：`/ws/v1`  
OpenAPI 是唯一事实源。

# 1. 通用协议

成功：`{"success":true,"data":{},"request_id":"req_xxx"}`。失败：`error.code/message/details`。长任务返回 job_id/status_url。

Desktop local mode 使用 `Authorization: Bearer <per-launch-session-token>`；团队版使用 OIDC access token。WS 同样鉴权。

可编辑对象返回 `revision` + `ETag`，更新支持 `If-Match` / expected_revision，冲突 `409 REVISION_CONFLICT`。

重要 POST 支持 `Idempotency-Key`：create project、build、simulation、repair apply、flash、knowledge promote、repository analyze。

列表统一 `?limit=50&cursor=...`，返回 items/next_cursor。

# 2. Meta / Workspace

```http
GET /meta/version
GET /meta/compatibility
GET /meta/enums
GET /capabilities
GET /schemas
GET /schemas/{schema_name}
GET /ui/extensions
GET /dashboard
GET /workspace
PATCH /workspace
GET /workspace/recent-projects
GET /search?q=
```

# 3. Project / Import

```http
POST /projects
GET /projects
GET /projects/{project_id}
PATCH /projects/{project_id}
DELETE /projects/{project_id}
POST /projects/{project_id}/clone
GET /projects/{project_id}/overview
GET /projects/{project_id}/engineering-status
POST /projects/{project_id}/export
POST /projects/{project_id}/release

POST /projects/{project_id}/imports
GET /projects/{project_id}/imports
GET /imports/{import_id}
POST /imports/{import_id}/analyze
POST /imports/{import_id}/build
GET /imports/{import_id}/facts
GET /imports/{import_id}/ir-candidates
POST /imports/{import_id}/accept
```

# 4. Documents / Claims / Requirements

```http
POST /projects/{project_id}/documents
GET /projects/{project_id}/documents
GET /documents/{document_id}
POST /documents/{document_id}/parse
POST /documents/{document_id}/reparse
GET /documents/{document_id}/pages/{page}
GET /documents/{document_id}/search?q=

GET /projects/{project_id}/claims
GET /claims/{claim_id}
GET /claims/{claim_id}/evidence
GET /claims/{claim_id}/conflicts
POST /projects/{project_id}/claims/resolve

GET /projects/{project_id}/requirements
POST /projects/{project_id}/requirements/analyze
PATCH /projects/{project_id}/requirements
POST /projects/{project_id}/requirements/validate
GET /projects/{project_id}/requirements/missing
POST /projects/{project_id}/requirements/recommend
```

# 5. Architecture / Device / Pin

```http
POST /projects/{project_id}/architecture/generate
GET /projects/{project_id}/architecture
PATCH /projects/{project_id}/architecture

GET /devices/search?q=
GET /devices/{device_id}
GET /devices/{device_id}/pins
GET /devices/{device_id}/dma
GET /devices/{device_id}/interrupts
GET /devices/{device_id}/clocks
GET /devices/{device_id}/claims

GET /projects/{project_id}/pin-planner/requirements
POST /projects/{project_id}/pin-planner/generate
GET /projects/{project_id}/pin-planner/map
PATCH /projects/{project_id}/pin-planner/map/{assignment_id}
POST /projects/{project_id}/pin-planner/validate
GET /projects/{project_id}/pin-planner/candidates?signal=
POST /projects/{project_id}/pin-planner/assignments/{id}/lock
```

# 6. Hardware / Circuit / Schematic

```http
GET /projects/{project_id}/hardware
POST /projects/{project_id}/hardware/generate
PATCH /projects/{project_id}/hardware
GET /projects/{project_id}/components
POST /projects/{project_id}/components/recommend
GET /projects/{project_id}/circuit
POST /projects/{project_id}/circuit/generate
PATCH /projects/{project_id}/circuit
POST /projects/{project_id}/circuit/validate
POST /projects/{project_id}/schematic/generate
GET /projects/{project_id}/schematic
GET /projects/{project_id}/schematic/versions
POST /projects/{project_id}/schematic/erc
GET /projects/{project_id}/schematic/erc/latest
POST /projects/{project_id}/schematic/export
```

PCB 自动生成 V1.3 默认不可用。Reserved API 仅当 `/capabilities` 明确开启时展示，否则返回 `CAPABILITY_UNAVAILABLE`。

# 7. MCUConfig / Firmware / MotorControl / RTOS

```http
GET /projects/{project_id}/mcu-config
POST /projects/{project_id}/mcu-config/generate
PATCH /projects/{project_id}/mcu-config
POST /projects/{project_id}/mcu-config/validate

GET /projects/{project_id}/firmware
POST /projects/{project_id}/firmware/generate
PATCH /projects/{project_id}/firmware
POST /projects/{project_id}/firmware/code/generate
GET /projects/{project_id}/firmware/files
GET /projects/{project_id}/firmware/files/content?path=
PUT /projects/{project_id}/firmware/files/content
POST /projects/{project_id}/firmware/files/ai-edit
GET /projects/{project_id}/firmware/diff

GET /projects/{project_id}/motor-control
POST /projects/{project_id}/motor-control/generate
PATCH /projects/{project_id}/motor-control
POST /projects/{project_id}/motor-control/validate
GET /projects/{project_id}/motor-control/timing
GET /projects/{project_id}/motor-control/sign-convention

GET /projects/{project_id}/rtos
POST /projects/{project_id}/rtos/generate
GET /projects/{project_id}/rtos/tasks
POST /projects/{project_id}/rtos/validate
```

# 8. Build / Protocol / Test / Review

```http
POST /projects/{project_id}/build
GET /projects/{project_id}/builds
GET /builds/{build_id}
GET /builds/{build_id}/logs
POST /projects/{project_id}/analysis/static

GET /projects/{project_id}/protocol
POST /projects/{project_id}/protocol
PATCH /projects/{project_id}/protocol
POST /projects/{project_id}/protocol/generate
POST /projects/{project_id}/protocol/validate

GET /projects/{project_id}/tests
POST /projects/{project_id}/tests/generate
GET /projects/{project_id}/tests/cases
POST /projects/{project_id}/tests/run
GET /projects/{project_id}/tests/results
GET /projects/{project_id}/tests/coverage
GET /projects/{project_id}/traceability

POST /projects/{project_id}/review
GET /projects/{project_id}/reviews
GET /projects/{project_id}/issues
GET /issues/{issue_id}
POST /issues/{issue_id}/resolve
POST /issues/{issue_id}/ignore
```

# 9. Artifact / AI / Debug / Repair

```http
GET /projects/{project_id}/artifacts
GET /artifacts/{artifact_id}
GET /artifacts/{artifact_id}/versions
GET /artifacts/{artifact_id}/dependencies
GET /artifacts/{artifact_id}/dependents
GET /projects/{project_id}/artifacts/stale
POST /artifacts/{artifact_id}/revalidate

POST /projects/{project_id}/conversations
POST /conversations/{conversation_id}/messages
POST /conversations/{conversation_id}/cancel
POST /projects/{project_id}/debug/sessions
POST /debug/sessions/{session_id}/analyze
GET /debug/sessions/{session_id}/root-causes
POST /issues/{issue_id}/repair
GET /repairs/{repair_id}/diff
POST /repairs/{repair_id}/apply
POST /repairs/{repair_id}/validate
POST /repairs/{repair_id}/rollback
```

# 10. Knowledge / Repository / Tools

```http
GET /memory/search
GET /projects/{project_id}/memory
POST /memory/{memory_id}/promote
GET /knowledge
GET /knowledge/gaps
GET /references/projects

GET /repositories/candidates
POST /repositories/discover
POST /repositories/candidates/{candidate_id}/shallow-analyze
POST /repositories/candidates/{candidate_id}/deep-analyze
POST /repositories/candidates/{candidate_id}/approve
GET /repositories/candidates/{candidate_id}/budget

GET /tools
GET /tools/{tool_id}/health
GET /plugins
POST /plugins/install
POST /plugins/{plugin_id}/enable
POST /plugins/{plugin_id}/disable
GET /settings
PATCH /settings
```

# 11. Jobs / Hardware / Permission / Lock

```http
GET /jobs/{job_id}
POST /jobs/{job_id}/cancel
GET /jobs/{job_id}/logs
GET /jobs/{job_id}/budget
GET /hardware/debug-probes
GET /hardware/serial-ports
GET /hardware/can-interfaces
POST /projects/{project_id}/hardware/flash
POST /hardware/reset
POST /hardware/halt
POST /hardware/run
GET /permissions/requests
POST /permissions/requests/{request_id}/approve
POST /permissions/requests/{request_id}/reject
GET /resource-locks
POST /resource-locks/{lock_id}/release
```

`POST /hardware/run` 仅表示恢复 MCU CPU/debug target 运行，不等价于执行器/PWM enable。 真正 actuator enable 必须通过 Commissioning/Safety API。

# 12. WebSocket Envelope / Replay

```json
{
  "event_id": "evt_...",
  "sequence": 1204,
  "timestamp": "...",
  "channel": "job:123",
  "type": "job.progress",
  "project_id": "...",
  "job_id": "...",
  "payload": {}
}
```

支持 `/ws/v1?resume_after=evt_xxx`。后端保留短窗口 Event Buffer；无法 replay 时发送 `stream.resync_required`，前端重新拉 REST state。

Channels：project/agent、job、build、test、serial、can、debug、repository、artifact。

# 13. Error Codes

PROJECT_NOT_FOUND、DOCUMENT_PARSE_FAILED、CLAIM_CONFLICT、DEVICE_NOT_FOUND、PIN_CONFLICT、PIN_FUNCTION_INVALID、INVALID_REQUIREMENT、REVISION_CONFLICT、BUILD_FAILED、ERC_FAILED、STATIC_ANALYSIS_FAILED、TOOL_UNAVAILABLE、CAPABILITY_UNAVAILABLE、AI_PROVIDER_UNAVAILABLE、PERMISSION_REQUIRED、RESOURCE_BUSY、BUDGET_EXCEEDED、KNOWLEDGE_SCOPE_DENIED、REPOSITORY_UNTRUSTED、JOB_CANCELLED、SCHEMA_VERSION_UNSUPPORTED、AUTH_REQUIRED。

# 14. ELKB / Learning API

```http
GET /learning/knowledge
GET /learning/knowledge/{knowledge_id}
GET /learning/domains
GET /learning/concepts
GET /learning/algorithms
GET /learning/guidelines
GET /learning/formulas
GET /learning/knowledge/{knowledge_id}/relations

POST /projects/{project_id}/learning/documents
GET /projects/{project_id}/learning/documents
POST /learning/documents/{document_id}/extract

POST /learning/discovery
GET /learning/candidates
GET /learning/candidates/{candidate_id}
POST /learning/candidates/{candidate_id}/analyze
POST /learning/candidates/{candidate_id}/approve
POST /learning/candidates/{candidate_id}/reject
```

所有 Learning API 遵守 Scope/Authority/Trust/License policy。私有 Learning Document 的查询必须带 project/user scope context。

# 15. Engineering Dependency API

```http
GET /projects/{project_id}/dependencies
GET /entities/{entity_type}/{entity_id}/dependencies
GET /entities/{entity_type}/{entity_id}/dependents
POST /entities/{entity_type}/{entity_id}/impact-analysis
POST /artifacts/{artifact_id}/revalidate
```

原 Artifact dependency endpoint 保持兼容，但后端统一映射 Engineering Dependency & Impact Graph。

# 16. V1.3 Domain Composition API

```http
GET  /projects/{project_id}/domains
GET  /projects/{project_id}/domains/available
POST /projects/{project_id}/domains/{domain_id}/activate
POST /projects/{project_id}/domains/{domain_id}/deactivate
GET  /projects/{project_id}/domains/{domain_id}/state
GET  /projects/{project_id}/domains/{domain_id}/schema
POST /projects/{project_id}/domains/{domain_id}/validate
GET  /projects/{project_id}/domains/{domain_id}/artifacts
POST /projects/{project_id}/domains/resolve-composition
```

固定 `/motor-control` 仅作为 builtin compatibility alias。

# 17. Source / Patch API

```http
GET  /projects/{project_id}/source/status
GET  /projects/{project_id}/source/revision
GET  /projects/{project_id}/source/files/content?path=
POST /projects/{project_id}/source/patch-proposals
GET  /patch-proposals/{proposal_id}/diff
POST /patch-proposals/{proposal_id}/apply
POST /projects/{project_id}/source/commit
```

文件读取返回 ETag/content_hash；apply/write 必须带 If-Match 或 expected SourceRevision。旧 firmware files write API 映射 Source Service。

# 18. Commissioning / Safety API

```http
GET  /projects/{project_id}/commissioning/profiles
POST /projects/{project_id}/commissioning/sessions
GET  /commissioning/sessions/{session_id}
POST /commissioning/sessions/{session_id}/preflight
POST /commissioning/sessions/{session_id}/flash
POST /commissioning/sessions/{session_id}/step/{step_id}/run
POST /commissioning/sessions/{session_id}/approve
POST /commissioning/sessions/{session_id}/abort
POST /commissioning/sessions/{session_id}/emergency-stop
GET  /commissioning/sessions/{session_id}/evidence
```

# 19. Recovery API

`GET /system/recovery/status`、`GET /system/outbox/status`、`POST /system/recovery/reconcile`、`GET /projects/{project_id}/consistency`。
