# Embedded Engineering Agent
## Agent Workflow Specification V1.3

# 1. Agent 清单

ProjectManagerAgent、RequirementAgent、DatasheetAgent、ClaimExtractionAgent、ClaimResolverAgent、SystemArchitectAgent、HardwareArchitectAgent、ComponentAgent、CircuitAgent、MCUConfigAgent、FirmwareArchitectAgent、MotorControlAgent、RTOSAgent、ProtocolAgent、TestAgent、ReviewAgent、DebugAgent、RepairAgent、ProjectImportAgent、RepositoryIntelligenceAgent、ArchitectureMiningAgent、PatternMiningAgent、KnowledgeGapAgent、LearningKnowledgeAgent、KnowledgeNormalizationAgent、TechnicalKnowledgeDiscoveryAgent、KnowledgeCuratorAgent。

# 2. ProjectManagerAgent

负责识别任务、检查 Project State、选择 Workflow、触发 Agent、协调审批/资源/预算、汇总结果；不负责具体 Pin/Circuit/Rule/Build 判断。

# 3. Requirement Workflow

`User Input → RequirementAgent → Schema → Completeness → Missing/Conflict → Recommendation → User Accept/Edit → Requirement Artifact`。

Recommendation 在用户接受前不得成为 locked fact。

# 4. New Design Vertical Workflow

```text
Requirement
→ ContextBuilder(Facts + ELKB + ERIS + Rules + Experience)
→ Claims/Device/Datasheet
→ SystemArchitecture
→ HardwareIR
→ PinPlanner
→ Core Rule Pre-check
→ CircuitIR
→ Electrical Rule
→ Schematic/KiCad ERC
→ MCUConfigIR
→ FirmwareIR
→ DomainExtensionRegistry
→ Active Domain IRs (0..N)
→ Code Generator
→ Build/Static Analysis
→ ProtocolIR
→ TestIR
→ Review
→ E2E Report
```

# 5. Firmware Workflow

Requirement → HardwareIR/Locked PinMap → MCUConfigIR → FirmwareArchitect → FirmwareIR → Active Domain IRs(optional, 0..N) → RTOS(optional) → Code → Build → Static Analysis。Firmware 必须读取统一 PinMap/MCUConfigIR。

# 6. Existing Project Import Workflow

```text
Source/Git/Archive
→ Sandbox Foundation / Safe Materialization
→ ProjectImportAgent
→ Build/Toolchain Detection
→ CubeMX/PlatformIO/CMake Parser
→ Source/Symbol Scan
→ Pin/Clock/Peripheral Facts
→ Claim Extraction
→ Candidate IR
→ Build(optional)
→ Consistency Review
→ Import Report
```

导入不自动覆盖用户代码。

# 7. Motor Control Workflow

MotorControl Plugin 激活后：Requirement → Motor/Encoder/CurrentSense Facts → MotorControlIR(requirements/refs) → MCUConfig cross-validation → Sign Convention Validation → PWM/ADC Timing Validation → Control Loop Structure → Generator → Build → Simulation/Hardware Test。

# 8. Test / Review

Test：Requirements → TestIR → Coverage → Run → Result → Evidence。P0 无测试覆盖 Review Fail。

Review：Schema → Claim/Evidence → Rule → Tool → Artifact Staleness → Traceability → AI Review → Deduplicate → Issue List。AI 不得覆盖 Compiler/ERC 明确失败。

# 9. Debug / Repair

Debug：Symptom → Project State → Logs/Tool → Project Memory → Device Claims → ERIS Debug → Root Causes → Verification → Probability Update → Fix Proposal。

每个 Root Cause 包含 hypothesis/confidence/why/evidence/affected_artifacts/next_verification/risk。

Repair：Issue → Fix Plan → Permission → Resource Lock(if needed) → Git Branch → Patch → Diff → Build/Test/Review → Commit 或 Rollback/Reopen。

# 10. Repository Discovery

KnowledgeGap → QueryBuilder → CandidatePool → Metadata Score → Budget Gate → Shallow Scan → License/Security → Budget Gate → Deep Analysis → ERIS Staging → Curator → Promote/Reject/Reference-only。

# 11. Knowledge Promotion

Task → Project Candidate → Project Verification → Generalization → Global Candidate → Curator → Global Trusted。

# 12. Context Builder

输入 project_id/task_type/query/token_budget/required_domains/selected refs/scope。默认融合层：

```text
Project Locked Facts
→ Project Verified Memory
→ Official Datasheet
→ Device Facts
→ Engineering Rules
→ ELKB Trusted Knowledge
→ ERIS Trusted Reference
→ Lower Trust Sources
→ AI Inference
```

实际排序按 task_type 动态调整。所有返回项保留 Evidence、Authority、Trust、Verification、Applicability、Scope。ELKB 回答“为什么/原理/算法/方法”，ERIS 回答“成熟工程怎么实现”，Rules 负责确定性判断。

# 13. Retry / Fallback

仅 structured parse failure、transient provider/tool error 做有限 retry。工程判断不通过不能“多问几次直到 PASS”。默认 structured retry=2、repair round=3。

Fallback 必须标 Degraded Mode。KiCad 不可用可生成 CircuitIR，但不能标 ERC_VERIFIED；Device 数据不完整时 Pin validation 必须 UNKNOWN/blocked，禁止猜测 PASS。

# 14. Human Approval

FLASH、HARDWARE_CONTROL、DELETE、destructive Git、private credential、扩大 Knowledge Scope、override CRITICAL、Release finalize、untrusted plugin install 都需要审批。

# 15. Resource Lock / Budget

硬件动作执行 Acquire → Validate target → Execute → Heartbeat → Release。资源忙返回 BLOCKED_RESOURCE。

Workflow 声明 max_tokens/max_cost/max_runtime/max_repo_bytes/max_candidates/max_parallelism，超限返回 BUDGET_EXCEEDED。

# 16. Agent Output Contract

```json
{
  "status": "SUCCESS",
  "artifact_refs": [],
  "issue_refs": [],
  "evidence_refs": [],
  "claim_refs": [],
  "assumptions": [],
  "warnings": [],
  "next_actions": []
}
```

# 17. Cancel / Resume

Cancellation 清理 Sandbox、释放 Lock、标记 partial artifacts；Resume 使用 checkpoint + Idempotency-Key 避免重复 side effect。

用户 Lock 的 Artifact/Decision/PinAssignment/Selection/Requirement 不允许后续 Agent 静默覆盖；如果依赖变化导致 stale，保留锁并要求 compare/regenerate/keep。

# 18. ELKB Ingestion Workflow

```text
Learning Document
→ Safe Materialization
→ DocumentParser
→ DocumentIR / Semantic Chunks
→ LearningKnowledgeAgent
→ Concept/Principle/Algorithm/Formula/Guideline extraction
→ KnowledgeNormalizationAgent
→ Evidence + Authority + License
→ ELKB Staging
→ KnowledgeCurator
→ Scoped KnowledgeEntry
```

新来源不能直接 GLOBAL_TRUSTED。用户上传学习资料默认 USER_PRIVATE 或 PROJECT_PRIVATE。

# 19. Technical Knowledge Discovery

作为统一 Discovery Provider 架构中的 `document discovery` capability：

```text
Knowledge Gap
→ TechnicalKnowledgeDiscoveryAgent
→ Candidate Document Pool
→ Authority / License / Quality
→ Budget Gate
→ Parser / Extraction
→ ELKB Staging
→ Curator
```

不构造与 OSDLE 重复的抓取、Budget、Curator、Provider 基础设施。

# 20. Hardware Commissioning Workflow

`Build/Static Analysis → Safety Pre-check → Permission/ResourceLock → Target Identity → Flash → Reset → SafeState → Sensor/Current/Encoder Sanity → Low-power Test → Sign/Phase Verification → Closed-loop Limited Test → User Approval → Normal Operation`。

Agent 不得把 `Flash SUCCESS` 直接解释为 `Hardware Run SUCCESS`。Crash/Cancel/Heartbeat loss 后执行 SafeState 并 reconcile。

# 21. Source Edit Workflow

AI edit：Context → PatchProposal(base SourceRevision) → Diff → Impact → Approval → Apply → SourceChanged Outbox → Build/Test/Review。Stale PatchProposal 禁止 apply。

# 22. Persistent Event Workflow

业务 mutation 与 Outbox Event 同事务；Resume 前区分 pure compute、idempotent tool、external side effect、hardware side effect，硬件 side effect 默认不自动 resume。
