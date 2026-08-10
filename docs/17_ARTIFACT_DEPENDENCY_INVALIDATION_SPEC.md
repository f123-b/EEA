# Embedded Engineering Agent
## Engineering Dependency & Impact Graph Specification V1.3

# 1. 目的

V1.1 的 Artifact Dependency 扩展为通用 Engineering Dependency & Impact Graph。目标是防止 Requirement、Claim、Device Fact、Pin、IR、Knowledge Snapshot 或 Artifact 上游变化后，下游仍被误认为有效。

# 2. Node

```text
DependencyNodeRef
- entity_type
- entity_id
- revision_or_version
- content_hash(optional)
```

支持 Requirement、EngineeringClaim、DeviceFact、PinAssignment、ComponentSelection、HardwareIR、CircuitIR、MCUConfigIR、FirmwareIR、DomainIR、ProtocolIR、TestIR、KnowledgeSnapshot、Artifact、BuildRun、TestResult、Decision。

# 3. Edge

source_ref、target_ref、relation、required、invalidation_policy、reason、created_by。

Relation：DERIVED_FROM、DEPENDS_ON、IMPLEMENTS、GENERATED_FROM、VERIFIED_BY、CONFIGURES、REFERENCES、USES_KNOWLEDGE、INVALIDATES。

# 4. Invalidation Policy

HARD_INVALIDATE：必须重新生成/验证。  
STALE：不保证仍有效，需 revalidate。  
REVIEW_REQUIRED：语义变化需人工/Agent Review。  
NO_PROPAGATE：明确无工程影响。

# 5. Artifact 状态

CURRENT、STALE、INVALID、DEPRECATED、ARCHIVED。Locked Artifact 仍可 STALE，但不得自动重写。

# 6. 示例：Errata

```text
Errata Claim v2
→ Pin/Peripheral Fact
→ PinAssignment
→ MCUConfigIR
→ Firmware BSP
→ Build
→ Test
```

Claim supersede 后，Impact Analyzer 只传播到实际依赖的对象。

# 7. 示例：Motor Requirement

```text
MotorControlIR.pwm_requirement
→ MCUConfigIR.PWMConfig
→ Firmware Generator
→ Firmware Artifact
→ Build/Test
```

Domain IR 不复制 realized MCU config，而通过依赖边引用。

# 8. Snapshot / Hash

Artifact 保留 content_hash、input_hash、dependency_hashes、generator/schema/tool/knowledge snapshot。非 Artifact entity 使用 revision/version/content hash 参与依赖快照。

# 9. Impact Analysis

返回 affected nodes、reason、severity、recommended order、regenerate/revalidate/manual-review action。UI 必须能解释 “why stale”。

# 10. Revalidate

Revalidate 不等于 regenerate。若当前依赖快照下 Rule/Tool/Test 重新通过，可以恢复 CURRENT；否则保持 STALE/INVALID。

# 11. API

支持 entity dependencies/dependents、project graph、impact-analysis、stale list、revalidate、regenerate plan。旧 Artifact-only endpoints 兼容映射。

# 12. Acceptance

- PinMap 变化正确传播 Circuit/Schematic/MCUConfig/Firmware。
- Errata Claim 变化能传播到真正引用它的工程对象。
- 纯 UI metadata 不传播。
- ProtocolIR 与 Pin 无关时不无条件 stale。
- Core Neutrality/ELKB Knowledge Snapshot 变化不会导致无关 Artifact 全图雪崩。

# 13. Transactional Propagation

Entity mutation 与 Outbox Event 同 SQL transaction；Impact consumer 幂等并记录 processed event。SourceRevision、DomainActivation、CommissioningProfile/SafetyLimit 也可作为 dependency node。
