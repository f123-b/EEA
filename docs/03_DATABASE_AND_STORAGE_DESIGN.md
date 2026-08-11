# Embedded Engineering Agent
## Database & Storage Design V1.3

# 1. 存储分工

SQL 保存强一致业务数据；Object/File Storage 保存 PDF/KiCad/源码/Build/Logs/Reports；Qdrant 保存向量；Git 管理项目源代码/Patch；Graph DB 不作为 V1.3 依赖，图关系先使用 SQL edge table。

# 2. SQL 表

projects、requirements、documents、document_parse_runs、engineering_claims、claim_evidence、claim_conflicts、devices、device_sources、artifacts、artifact_dependencies、artifact_invalidations、evidence、issues、engineering_decisions、traceability_edges、jobs、agent_runs、tool_runs、permissions_audit、resource_locks、budget_runs、plugin_registry、knowledge_entries、memory_entries、knowledge_conflicts、knowledge_promotions、repository_candidates、repository_knowledge、repository_versions、repository_scores、project_import_runs、imported_project_facts、test_runs、build_runs、review_runs、debug_sessions、repair_runs。

# 3. Project 关系

```text
Project
 ├─ Requirements
 ├─ Documents
 ├─ Claims
 ├─ Artifacts
 ├─ Issues
 ├─ Decisions
 ├─ Traceability
 ├─ ImportRuns
 ├─ Test/Build/Review
 ├─ DebugSessions
 └─ ProjectMemory
```

项目删除采用 soft delete/recycle bin。

# 4. Artifact Version

Artifact 不覆盖旧版本。保存 logical_name/version/content_hash/input_hash/parent_artifact/dependencies/status，支持 rollback/compare/stale propagation。

# 5. Content-addressed Storage

建议 `objects/ab/cd/<sha256>` 去重，同一 Datasheet/Build Artifact 不重复占用。

# 6. Workspace

```text
workspace/{project_id}/
├── source/
├── imported/
├── generated/
├── hardware/
├── firmware/
├── protocol/
├── tests/
├── logs/
├── reports/
├── tmp/
└── .git/
```

# 7. Document Storage

保存 raw file、parse metadata、parser version、result hash、page/table/figure mapping、extracted claim snapshot、embedding index version。Parser 升级可 reparse，但保留历史 ParseRun。

# 8. Vector Metadata

每个 chunk 必须带 source_type/source_id/project_id/organization_id/scope/document/page 或 repo_commit/path/knowledge_id/claim_ids/trust/lifecycle。检索先 scope filter，再 rank。

# 9. Memory Isolation

Query：Current Task → Current Project → User/Organization → Global Public。DB 和 Service 都要 scope guard。

# 10. Claim Storage

Claim 不原地静默覆盖；新来源/版本产生新 Claim 或 supersede relation。冲突保留 ClaimConflict。

# 11. Knowledge Version / Promotion Audit

Knowledge 保存 version/content_hash/source_version/trust/lifecycle/last_verified。Promotion 保存 from/to/evaluator/decision/reason/evidence snapshot/approved_by/timestamp。

# 12. Repository Version

RepositoryKnowledge 必须绑定 commit，增量分析基于 Git diff，不使用漂移 main 作为唯一身份。

# 13. Job / ToolRun / AgentRun

ToolRun 保存 tool/version/argv/exit_code/sanitized stdout-stderr/artifacts/duration/sandbox。AgentRun 保存 prompt/model/input-output hash/tool/artifact/issue/evidence/usage/duration，不保存私有 chain-of-thought。

# 14. Resource Lock / Budget

resource_locks 保存 resource_type/id/owner/lease/heartbeat/status。budget_runs 保存 token/cost/runtime/repo bytes/candidate/deep-analysis 等预算与消耗。

# 15. Secret

主 DB 只保存 secret reference/masked label/last_used_at，value 放 OS keyring/Vault/加密 Secret Store。

# 16. Migration / Backup / Retention

Alembic，每次 Schema 变化必须 migration + forward test + release note。单机 SQLite/Object/Qdrant snapshot；服务端 PostgreSQL backup/Object versioning/Qdrant snapshot。

长期保留 Project/Decision/Issue/Claims/Verified Test/Promotion Audit/Release Snapshot；可清理 Task context/Sandbox/candidate clone/build intermediates/cache。

# 17. Artifact 一致性事务

```text
generate temp → hash → object storage → metadata transaction → dependencies → ArtifactCreated → invalidation propagation
```

# 18. Optimistic Concurrency

所有可编辑核心对象带 revision。PATCH 带 expected_revision/If-Match，冲突返回 `409 REVISION_CONFLICT`。

# 19. ELKB Storage

优先复用统一 `knowledge_entries`，并通过 subtype/detail table 保存 LearningKnowledge 专有字段。新增或扩展：

- learning_documents
- learning_document_candidates
- learning_knowledge_details
- engineering_equations
- knowledge_relations
- knowledge_source_licenses
- authority_metadata

`Document raw storage != Knowledge storage`：Document 是 Source；KnowledgeEntry/LearningKnowledge 是提取、归一化、带 Evidence/Authority/Trust 的工程知识对象。

# 20. Vector Metadata

Qdrant metadata 至少增加：knowledge_type、domain、authority_level、trust_level、verification_level、source_type、source_id、publisher、license、scope、lifecycle、freshness。检索必须先 Scope/Lifecycle/Applicability filter，再 rank。

# 21. Engineering Dependency & Impact Graph

SQL 以 `engineering_dependency_nodes` + `engineering_dependency_edges` 表达跨对象依赖；不再只用 `artifact_dependencies`。

示例：

```text
EngineeringClaim
→ PinAssignment
→ MCUConfigIR
→ FirmwareArtifact
→ BuildRun
→ TestResult
```

Claim supersede、Requirement revision、Knowledge Snapshot change 均可触发 Impact Analysis。Artifact Staleness 继续作为落地状态，但传播源不限于 Artifact。

# 22. Learning Source License

保存 source_license、usage_policy、storage_policy、quotation_policy、retrieval_policy、evidence_link。无法合法长期保存全文的来源只保存 Metadata、Structured Summary、Knowledge Extraction、Evidence Link、短引用。

# 23. V1.3 Reliability Tables

新增/正式化：`outbox_events`、`processed_events`、`side_effect_journal`、`source_revisions`、`patch_proposals`、`domain_activations`、`commissioning_sessions`、`commissioning_step_results`、`safety_limits`、`emergency_stop_events`、`users`、`organizations`、`memberships`、`project_roles`。

业务 mutation 与 outbox insert 必须同一 SQL transaction。Qdrant/搜索索引属于可重建派生数据。Object Storage 采用 content-addressed put；orphan object 由 GC 清理。启动 Recovery Manager 重放 Outbox、回收过期 Lock、协调 interrupted Job、检测 partial Artifact/Source workspace。

# 24. Source Workspace Authority

Git Working Tree 是源码字节 SSOT；SQL 保存 SourceRevision/状态，不复制一套可编辑源码数据库。Build/Test/Review 保存精确 tree hash/commit SHA。

# 25. Backup / Restore

Project export manifest 包含 schema/plugin/domain versions、SourceRevision、Artifact hashes、Knowledge/Device/Rule snapshots 与 Object refs；Restore 必须 hash verify + compatibility check + migration dry-run。

# 26. ESCR / Dependency Lock Storage

M12A 新增 `software_components`、`software_component_releases`、`dependency_locks`、`dependency_lock_components`、`component_materializations`。Release 的 source revision、manifest hash、content hash、files、submodule commits 与 verified/yanked 状态不可被浮动版本替代；lock join 保存解析后的组件 revision 与 hashes。

DEVICE 构建只读取 `component-cache/<content_hash>/<manifest_hash>`，构建阶段不联网、不解析浮动版本。缓存命中前必须验证 manifest/content hash；缺失或不匹配返回 blocked/unavailable 并保留 BuildRun 诊断。
