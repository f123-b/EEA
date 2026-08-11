# Embedded Engineering Agent
## Domain Model & Schema 规范 V1.3

# 1. 原则

Stable ID、Schema Version、Evidence-friendly、Claim-oriented、Engineering-computable、Migratable、Diff-friendly、Third-party independent。

# 2. EntityBase

```python
class EntityBase(BaseModel):
    id: UUID
    schema_version: str
    revision: int
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = {}
```

`revision` 用于 Optimistic Lock。

# 3. Requirement

字段：project_id、code、title、requirement_type、priority、statement、rationale、acceptance_criteria、source_evidence_ids、status。

# 4. EngineeringValue

字段：unit、nominal、minimum、typical、maximum、tolerance_percent、condition、evidence_ids。核心可计算字段禁止只保存 `24V` 字符串。

# 5. EngineeringClaim

```python
class EngineeringClaim(EntityBase):
    subject_ref: str
    predicate: str
    value: Any
    applicability: dict[str, Any]
    evidence_ids: list[UUID]
    verification_levels: list[VerificationLevel]
    confidence: float
    source_priority: int
    source_version: str | None
    lifecycle: ClaimLifecycle
```

用于 Pin/AF/Electrical/Peripheral/Errata/Repository pattern/Imported fact。

# 6. ClaimConflict

字段：claim_a_id、claim_b_id、conflict_type、overlapping_applicability、resolver、resolution、selected_claim_id、reason、status。

# 7. Document / DocumentIR

Document：project_id、filename、document_type、vendor、product、version_label、content_hash、storage_uri、parse_status。  
DocumentIR：pages、sections、tables、figures、extracted_claim_ids，必须保留 page/section/table 定位。

# 8. Device

manufacturer、family、model、revision_label、category、packages、memory、peripherals、pins、clocks、dma、interrupts、electrical、claim_ids。

Pin：device_id、name、package、package_pin、voltage_domain、five_v_tolerant、functions、claim_ids。

# 9. SystemArchitectureIR

project_id、blocks、interfaces、decisions、requirement_ids、evidence_ids、source_artifact_ids。

# 10. HardwareIR

modules、device_instances、power_domains、interfaces、pin_requirements、constraints、requirement_ids、evidence_ids。

# 11. PinRequirement / Assignment

PinRequirement：signal_name、required_peripheral、required_function、direction、electrical_requirements、hard_constraints、preferred_constraints、timing_constraints。  
PinAssignment：requirement_id、device_id、pin_name、function、locked、score、claim_ids、evidence_ids。

# 12. Component / Selection

Component：manufacturer、mpn、category、package、ratings、characteristics、lifecycle_status、availability、claim_ids。  
Selection：requirement、selected_component_id、alternatives、engineering_margin、reason、evidence_ids、risk。

# 13. CircuitIR

components、nets、power_nets、constraints、requirement_ids、evidence_ids。Net 保存 endpoints、signal_type、voltage_domain、criticality、constraints、evidence_ids。

# 14. MCUConfigIR

```python
class MCUConfigIR(EntityBase):
    project_id: UUID
    device_instance_id: UUID
    clock: ClockIR
    gpio: list[GPIOConfig]
    peripherals: list[PeripheralConfigIR]
    dma: list[DMAIR]
    interrupts: list[InterruptConfigIR]
    memory: MemoryConfigIR | None
    debug: DebugConfigIR | None
    evidence_ids: list[UUID]
```

# 15. ClockIR / PeripheralConfigIR

ClockIR 表达 source、PLL、AHB/APB、peripheral clock、target/derived frequency、tolerance、evidence。

PeripheralConfigIR：instance、mode、pins、clock、parameters、dma_refs、interrupt_refs、trigger_refs。

PWMConfig：timer、channel、complementary_channel、center_aligned、switching_frequency、deadtime、polarity、break_input、update_event。

ADCConfig：instance、channels、sampling_time、trigger_source、trigger_edge、conversion_mode、injected_or_regular、dma、expected_range。

DMAIR：controller、channel/stream、request、direction、width、mode、priority、circular、buffer。

InterruptConfigIR：source、irq、priority、subpriority、max_execution_us、allowed_operations、communicates_with_tasks。

# 16. FirmwareIR

layers、modules、tasks、interrupts、shared_resources、mcu_config_id、build_target、requirement_ids、evidence_ids。

M12R/M12A 增加：`build_target.profile`（`HOST_SMOKE`/`DEVICE`）、`dependency_lock_id`、`dependency_lock_hash`、`component_refs`、`platform_adapter_id/version`。`FirmwareIR.input_hash` 必须覆盖 MCUConfigIR、target、board、generator、adapter 与 lock hash。

`DependencyLock` 保存 requirements、resolved immutable releases、resolver/policy version、MCUConfig identity 与 lock hash。`ResolvedComponent` 必须有 verified release、source revision、manifest/content hash；reference-only、无 license 或不兼容组件不得进入 production closure。

FirmwareModule：name、layer、responsibility、public_api、dependencies、timing、state、errors、testability、requirement_ids。

# 17. DomainIRRef / DomainIREnvelope

DomainIRRef：
- project_id
- domain_id
- domain_ir_id
- domain_schema_version
- plugin_id
- plugin_version
- revision

DomainIREnvelope：
- ref: DomainIRRef
- requirement_ids
- evidence_ids
- core_ir_refs
- extension_payload_ref

Core 只保存 Domain IR 的统一引用/封装，不定义 MotorControlIR、EtherCATIR、RoboticsIR 等具体领域字段。

具体 MotorControlIR 仅定义在 `16_MOTOR_CONTROL_DOMAIN_SPEC.md` 以及 `plugins/builtin/motor_control/`。

# 18. RTOS

Task：name、period_us、deadline_us、priority、stack_bytes、execution_budget_us、queues、mutexes、resources。  
Interrupt：source、priority、maximum_execution_us、allowed_operations、communicates_with_tasks。

# 19. ProtocolIR

transports、messages、version_label、requirement_ids。ProtocolField 包含 bit_offset/length/endian/signed/scale/offset/unit/min/max。

# 20. TestIR

TestCase：code、title、type、requirement_ids、preconditions、setup、inputs、steps、expected、timeout、pass_condition、cleanup、automation_level。

# 21. Evidence

类型：DOCUMENT、DEVICE_DB、REPOSITORY、RULE、TOOL、SIMULATION、HARDWARE_TEST、USER_CONFIRMATION、IMPORTED_PROJECT。Locator 支持 page/section/table/repo_commit/path/line_range/symbol/rule/tool/test/import run。

# 22. Artifact

project_id、logical_name、artifact_type、version_label、content_hash、input_hash、storage_uri、dependency_ids、dependency_hashes、created_by、source_job_id、generator_version、tool_versions、knowledge_snapshot、status。

# 23. ArtifactDependencyEdge

upstream_artifact_id、downstream_artifact_id、relation、required、invalidation_policy。

# 24. Issue / Decision / Traceability

Issue 增加 claim_ids。Traceability Relation：IMPLEMENTS、DERIVED_FROM、VERIFIED_BY、AFFECTS、DEPENDS_ON、GENERATED_FROM、INVALIDATES。

# 25. Knowledge / Memory

KnowledgeEntry：knowledge_type、title、summary、content、domains、tags、evidence_ids、claim_ids、trust_score、trust_level、verification_levels、lifecycle、scope、source_version、last_verified_at。  
MemoryEntry：knowledge_id、memory_level、scope、project_id、lifecycle、trust_level。

# 26. RepositoryCandidate / RepositoryKnowledge

Candidate 增加 estimated_analysis_cost、analysis_level。RepositoryKnowledge 必须绑定 analyzed_commit，并保存 architecture/modules/patterns/debug_cases/test_patterns/license/quality/evidence/claims。

# 27. ProjectImportRun

project_id、import_type、source_uri、detected_build_systems、detected_mcu、detected_toolchain、discovered_artifacts、extracted_claim_ids、generated_ir_refs、issues、status。

# 28. RuleResult

rule_id、rule_version、status、severity、affected_objects、message、recommendation、evidence_ids、measured_values、threshold。UNKNOWN 不等于 PASS。

# 29. Job

project_id、job_type、status、progress、phase、result_ref、error_code、error_message、budget_usage、resource_lock_ids。

# 30. Migration

所有主要对象带 schema_version。旧项目必须经过 migration。Agent 不得自行创造未注册字段直接入库。

# 31. ClaimPredicateDefinition

```python
class ClaimPredicateDefinition(EntityBase):
    predicate: str
    value_schema_ref: str
    applicability_schema_ref: str | None
    unit_dimension: str | None
    conflict_strategy: str
    validator_ref: str | None
```

EngineeringClaim 写入、比较、Rule 计算前必须 normalize。

# 32. KnowledgeType 扩展

新增或正式化：

`DEVICE`、`DATASHEET_FACT`、`CONCEPT`、`PRINCIPLE`、`ALGORITHM`、`FORMULA`、`DESIGN_GUIDELINE`、`BEST_PRACTICE`、`REFERENCE_PROJECT`、`REFERENCE_ARCHITECTURE`、`MODULE`、`PATTERN`、`ANTI_PATTERN`、`DEBUG_CASE`、`TEST_PATTERN`、`RULE`、`PROJECT_EXPERIENCE`。

# 33. LearningKnowledge

```python
class LearningKnowledge(KnowledgeEntry):
    topic: str
    knowledge_type: LearningKnowledgeType
    domains: list[str]
    definition: str | None
    explanation: str | None
    principles: list[str]
    prerequisites: list[str]
    applicable_conditions: list[str]
    limitations: list[str]
    example_ids: list[UUID]
    equation_ids: list[UUID]
    related_knowledge_ids: list[UUID]
    related_rule_ids: list[str]
    related_debug_case_ids: list[UUID]
    authority_level: AuthorityLevel
```

复用 KnowledgeEntry 的 Evidence、Trust、Verification、Lifecycle、Scope，不创建平行生命周期体系。

# 34. EngineeringEquation

```python
class EngineeringEquation(EntityBase):
    name: str
    expression: str
    variables: list[EquationVariable]
    assumptions: list[str]
    applicability: list[str]
    limitations: list[str]
    evidence_ids: list[UUID]
```

变量必须带 symbol/name/unit/dimension/description；禁止只保存公式字符串。

# 35. AuthorityLevel

`T0_STANDARD_OFFICIAL`、`T1_OFFICIAL_TECHNICAL`、`T2_TRUSTED_ACADEMIC`、`T3_MATURE_ENGINEERING_REFERENCE`、`T4_HIGH_QUALITY_COMMUNITY`、`T5_UNVERIFIED_COMMUNITY`、`T6_AI_INFERENCE`。

Authority 与 Trust 分离：Authority 描述来源级别，Trust 描述当前知识对象在 Evidence/Verification/Freshness/Conflict 下的可信状态。

# 36. LearningDocumentCandidate / SourcePolicy

LearningDocumentCandidate 保存 source_url、source_type、title、publisher、author、published/updated、domains、authority_level、quality_score、license_info、storage_allowed、extraction_allowed、lifecycle。

SourcePolicy 包含 SourceLicense、UsagePolicy、StoragePolicy、QuotationPolicy、RetrievalPolicy。

# 37. KnowledgeRelation

关系至少支持：PREREQUISITE_OF、EXPLAINS、IMPLEMENTED_BY、VALIDATED_BY、CONTRADICTS、APPLIES_TO、RELATED_TO、DERIVED_FROM、USED_BY_RULE、HAS_DEBUG_CASE。

V1.3 先用 SQL edge table，不引入 Graph DB 作为依赖。

# 38. DomainDescriptor

```python
class DomainDescriptor(BaseModel):
    domain_id: str
    version: str
    schema_refs: list[str]
    rule_pack_ids: list[str]
    generator_ids: list[str]
    ui_contributions: list[str]
    capabilities: list[str]
```

一个 Project 可激活 0..N Domain Plugin。

# 39. V1.3 Reliability Entities

新增核心对象：SourceRevision、PatchProposal、DomainActivation、OutboxEvent、ProcessedEvent、SideEffectJournal、HardwareCommissioningSession、CommissioningProfile、SafetyLimit、EmergencyStopEvent；服务端模式增加 Organization/User/Membership/ProjectRole。

EngineeringValue 增加 canonical_unit、dimension、normalized_nominal/minimum/typical/maximum。

DomainDescriptor 增加 requires_domains、optional_domains、conflicts_with、provided_capabilities、required_capabilities、priority、rule_phases、generator_phases、migration_provider。
