# EEA COMPLETE DOCUMENTATION V1.3

> Architecture Freeze 合订本。各分文件仍是维护单元。


---

<!-- FILE: 00_MASTER_PLAN.md -->

# Embedded Engineering Agent
## AI 嵌入式研发智能体平台完整项目方案 V1.3

**项目简称：** EEA  
**定位：** AI Embedded Engineering Operating System  
**开发方式：** Frontend / Backend / Engineering Tools 三层解耦  
**核心原则：** Core Self-Owned + IR + Evidence + Rule + Tool Verification + Adapter + Plugin + Controlled Learning

# 1. 项目愿景

EEA 不是嵌入式聊天机器人，也不是单一代码生成器、原理图生成器或 RAG 系统。目标是把嵌入式研发全过程统一为可验证、可追踪、可版本化的工程对象。

```text
用户需求 / 现有项目 / 实机故障
        ↓
Requirement / Project Import
        ↓
Engineering Claims / Datasheet / Device / ERIS
        ↓
SystemArchitectureIR
        ↓
HardwareIR / CircuitIR / MCUConfigIR / FirmwareIR / Active Domain IRs
        ↓
Rule Pre-check
        ↓
Schematic / Code / Protocol / Test
        ↓
ERC / Build / Static Analysis / Rule / Simulation
        ↓
Issue / Evidence / Traceability
        ↓
Debug / Repair / Verification
        ↓
Project Experience
        ↓
Controlled Memory Promotion
```

# 2. V1.3 首要目标

V1.3 以一个真实工程闭环为第一优先级：

> STM32G431 + DRV8323 + AS5047 + 24V + 10A + PMSM + FOC + CAN + UART。

必须做到：需求结构化、Datasheet/Device 事实可追溯、Pin/AF/Package 合法、Hardware/Circuit/MCU/Firmware/Motor IR 可表达、Rule 能拦截确定性错误、Schematic 能 ERC、Firmware 能真实 Build、Protocol 可生成、Review 有 Evidence、上游变化能使下游 Artifact STALE、已有工程可导入、私有知识不泄漏。

# 3. 非 V1.3 重点

- 自动 PCB Placement/Route；
- 完整 HIL 平台；
- 企业 PLM；
- 全 MCU 厂商；
- 全量 GitHub 主动扫描。

这些能力保留接口，但不得影响 V1.3 FOC E2E。

# 4. 用户模式

1. **从零设计**：Requirement → Architecture → HW/FW/Protocol/Test → Verification。
2. **已有硬件**：导入 KiCad/BOM/PinMap/Datasheet/.ioc，检查 HW/FW 一致性。
3. **已有 Firmware**：导入 Git/CMake/PlatformIO/Keil/CubeIDE，形成 Reverse Engineering Package。
4. **实机 Debug**：Symptom + Logs + Waveform + Existing Project → hypothesis/evidence/test/fix。

# 5. 一级模块

Project Platform、Project Import、AI Provider Foundation、Agent Runtime、Requirement Intelligence、Datasheet Intelligence、Engineering Claim Platform、Device Intelligence、ELKB、ERIS、OSDLE/Technical Knowledge Discovery、Knowledge & Memory、Hardware Engineering、Firmware Engineering、Domain Extension Platform、Protocol & PC Tool、Test & Traceability、Rule Engine、Review、Debug & Repair、Tool Integration、Simulation/Hardware/HIL、Engineering Dependency & Impact Graph、Security/Permission/Lock、Plugin、Frontend Workspace。

# 6. 总体架构

```text
┌──────────────────────────────────────────────────────┐
│ Tauri + React + TypeScript                         │
│ Project / IR / Evidence / Review / Debug / AI     │
└─────────────────────┬────────────────────────────────┘
                      │ REST + WebSocket
┌─────────────────────▼────────────────────────────────┐
│ Backend Application Layer                          │
│ Project / Job / Artifact / Permission / Lock      │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│ Agent Runtime                                       │
│ Context / Workflow / Approval / Retry / Resume     │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│ Engineering Domain                                 │
│ Requirement/Claim/Device/HW/MCU/FW/Test + Domain │
└─────────────────────┬────────────────────────────────┘
                      │ Ports
┌─────────────────────▼────────────────────────────────┐
│ Adapters / Plugins                                  │
│ LLM/PDF/Vector/Git/EDA/Build/Debug/CAN            │
└─────────────────────┬────────────────────────────────┘
                      │
┌─────────────────────▼────────────────────────────────┐
│ KiCad/SKiDL/CMake/PlatformIO/Cppcheck/pyOCD/...   │
└──────────────────────────────────────────────────────┘
```

依赖方向：`UI → API/Application → Domain → Ports ← Adapters/Plugins`。

# 7. 核心自研资产

Core 自研资产：Requirement DSL、EngineeringClaim、EngineeringValue、Device/Pin Capability、SystemArchitectureIR、HardwareIR、CircuitIR、MCUConfigIR、FirmwareIR、ProtocolIR、TestIR、Evidence、Engineering Dependency & Impact Graph、Traceability、Rule Engine、ELKB/Knowledge Trust/Lifecycle/Promotion、Reference Architecture DB、Pattern/Anti-Pattern DB、Debug Case DB、Engineering Score、Project Experience。MotorControlIR 属于官方 Built-in Domain Plugin，不属于 Core Schema。

# 8. Engineering Claim

关键事实尽量原子化：

```text
subject + predicate + value + applicability + evidence + verification
```

用于解决多来源、Errata、Revision、Package、Operating Condition 的冲突。

# 9. Datasheet / Device

支持 Datasheet、Reference Manual、Errata、Application Note、User Manual、Design Guide。

STM32 第一阶段应融合：vendor structured data / stm32-data 类数据、CMSIS-SVD、CMSIS-Pack、Datasheet、Reference Manual、Errata。**禁止将 CMSIS-SVD 视为完整 Pin/AF/Package 数据源。**

默认事实优先级：Errata > Datasheet/Reference Manual > Vendor structured source > Pack/SVD > Curated Community > Repository Reference > AI Inference。

# 10. Pin Planner

```text
PinRequirement
→ Device Capability DB
→ Hard Constraint Solver
→ Candidate PinMap
→ Rule Pre-check
→ AI Preference Ranking
→ Lock / Validate
```

关键 Pin 不允许依赖 LLM 猜测。

# 11. Hardware / Schematic

HardwareIR 表达模块/器件/电源域/接口；CircuitIR 表达元件/Pin/Net/Protection/Filter/Rating。

V1.3 原理图路线：

```text
Requirement → HardwareIR → CircuitIR → Rule → SKiDL → KiCad → ERC → Issue
```

LLM 不直接写复杂 `.kicad_sch` 作为事实源。PCB 自动生成默认 capability unavailable。

# 12. EngineeringValue

可计算值支持 unit、nominal、min、typ、max、tolerance、condition、temperature、evidence。禁止核心计算字段只保存 `"24V"`。

# 13. MCU / Firmware

增加 MCUConfigIR、ClockIR、PeripheralConfigIR、DMAIR、InterruptConfigIR、BoardSupportIR，使系统能表达 Timer→ADC Trigger→DMA/ISR→Control Loop→CCR Update 的实时拓扑。

Firmware 默认 Application / Middleware / Driver / BSP / Platform。

# 14. Domain Extension / MotorControl Built-in Plugin

MotorControl 是 EEA 首个官方 Built-in Domain Plugin，而不是 Core Domain。Core 只提供 DomainExtensionRegistry、DomainIR envelope、Rule/Generator/UI hook 与 Capability 接口。

MotorControlIR 结构化 Motor、Inverter、Encoder、CurrentSenseRequirement、PWMRequirement、ADCSamplingRequirement、ElectricalAngle、SignConvention、Startup、Current/Velocity/Position Loop、Limits/Faults。实际 Timer/PWM/ADC/DMA/IRQ 配置只保存在 MCUConfigIR，MotorControlIR 通过引用和约束关联，禁止重复成为第二事实源。

# 15. Protocol / Test / Review

ProtocolIR 是 MCU C/Python/DBC/Docs/Codec Test/PC Tool 的唯一事实源。

P0 Requirement 必须有 implementation link 和 verification link。

Review 固定：Schema → Claim/Evidence → Rule → Tool → Staleness → Traceability → AI Review。

# 16. Artifact Staleness

Artifact 记录 input_hash、dependency_hashes、generator/schema/tool/knowledge snapshot。状态：CURRENT / STALE / INVALID / DEPRECATED / ARCHIVED。上游变化必须传播失效。

# 17. Memory / ERIS / OSDLE

Memory：Task / Project / Global。

Promotion：`TASK_ONLY → PROJECT_CANDIDATE → PROJECT_VERIFIED → GLOBAL_CANDIDATE → GLOBAL_TRUSTED`。

ERIS 保存 commit-bound architecture/modules/patterns/tests/debug/license/evidence，不只保存代码 chunks。

OSDLE：Knowledge Gap → Search → Candidate → Metadata → Shallow → License/Security → Deep → Staging → Curator。必须有 Budget。

# 18. Existing Project Import

V1.3 最少支持 Git、Local folder、CMake、PlatformIO、Makefile、STM32CubeMX `.ioc`、KiCad、raw source。导入后形成 Import Report、Claims、IR Candidates、Consistency Issues。

# 19. Security

外部 Repository 默认 Untrusted。Sandbox no host home/no SSH/no secrets/no user project mount/restricted network/resource limit。

Desktop sidecar：loopback-only、随机端口、每次启动随机 bearer token、REST/WS 鉴权、deny broad CORS。

FLASH/HARDWARE_CONTROL 需要 Permission + Resource Lock。

# 20. Tool Platform

首批：LangGraph、LiteLLM、Docling、Qdrant、SKiDL、KiCad CLI、CMake、PlatformIO、CMSIS-Toolbox、Cppcheck、pyOCD、OpenOCD、pySerial、python-can、cantools、Renode、sigrok。全部经 Port/Adapter。

# 21. 前端

Tauri + React + TypeScript。主要页面：Dashboard、Import、Project、Requirements、Documents、Architecture、Hardware、Pin Planner、Circuit、Schematic、MCUConfig、Firmware、Motor Control、Protocol、Tests、Review、Debug、Knowledge、Repository Discovery、Settings。提供 Simple/Expert Mode。

# 22. 开发策略

```text
Foundation
→ AI Provider Foundation
→ Device/Claim/Document
→ Sandbox Foundation
→ Requirement/Pin/Rule
→ Circuit/Schematic
→ MCUConfig/Firmware/Static Analysis
→ Domain Extension Infrastructure
→ MotorControl Built-in Plugin
→ Protocol/Test/Review/Impact Graph
→ Transactional Recovery / Domain Composition / Source Authority / Commissioning Safety / NFR
→ FOC Minimal E2E
→ Core Neutrality Smoke
→ Desktop UI
→ Existing Project Import
→ ELKB MVP + ContextBuilder Integration
→ Agent Runtime/Memory
→ ERIS/Repository Intelligence
→ OSDLE + Technical Knowledge Discovery
→ Debug/Repair/Hardware
→ Gateway/Robot
```

FOC 是第一个 Reference Benchmark，不是 Core 特化。FOC E2E 通过后必须立即运行 Core Neutrality Smoke，验证不加载 MotorControl Plugin 时，普通 MCU + UART/CAN/SPI/RTOS 项目仍可完成核心闭环。

# 23. 最终成功标准

需求可追踪、Claim 可追溯、Pin 可信、HW/FW 一致、原理图/代码可生成、ERC/Build/Static Analysis 可验证、Artifact 失效可传播、Test/Issue/Patch 可追踪、Existing Project 可导入、实机经验可沉淀、公共知识可持续更新且不污染私有项目。

# 24. Embedded Engineering Intelligence Engine（V1.3）

EEA Knowledge Platform 正式统一为五类知识：

```text
Facts       = Datasheet Intelligence + Device Intelligence
Theory      = ELKB
Practice    = ERIS
Rules       = Engineering Rule Engine
Experience  = Project Memory / Verified Debug Cases
```

ELKB（Embedded Learning Knowledge Base）是一级知识能力，负责 Concept、Principle、Algorithm、Formula、Design Guideline、Best Practice 等“为什么这样设计”的理论与工程方法。ELKB 不替代 Datasheet/Device Fact，不替代 ERIS 的真实工程实现，也不替代 Rule Engine 的确定性判断。

ContextBuilder 根据任务动态融合 Project Facts、Official Datasheet、Device Facts、Rules、ELKB、ERIS、Project Experience，并保留 Evidence、Authority、Trust、Applicability、Scope。

# 25. Architecture Freeze 规则

1. Core 不硬编码 MotorControl/EtherCAT/ROS2/BMS 等垂直领域。
2. Built-in Domain Plugin 与第三方 Plugin 使用同一扩展契约。
3. 外部 Repo/Archive/Build 在进入执行链前必须经过 Sandbox Foundation。
4. FOC Release Gate 前必须具备真实 Build + Static Analysis + Core Firmware Rules。
5. MCUConfigIR 是 MCU 硬件配置唯一事实源；Domain IR 只表达需求、约束和引用。
6. 依赖传播覆盖 Requirement/Claim/IR/Artifact/Knowledge Snapshot，不限于 Artifact→Artifact。
7. ELKB 不允许退化成“PDF→Chunk→Embedding”的普通 RAG，也不以自动 Fine-tuning 作为主动学习机制。

# 26. V1.3 Reliability & Safe Execution Freeze

V1.3 保持 IR-first / Evidence / Rule / Plugin 主干不变，但把以下能力升级为正式开工硬前置：

1. Hardware Commissioning & Safety：Flash 与执行器使能分离，PWM/Actuator 默认 SafeState。
2. Transactional Outbox & Recovery：SQL mutation + Outbox Event 同事务，Consumer 幂等，Qdrant 可重建。
3. Domain Composition：0..N Domain 的依赖、冲突、Capability、Rule/Generator DAG、Migration 正式化。
4. Source Authority：Git Working Tree 为源码字节 SSOT；IR 表达设计意图；Artifact 是不可变快照/生成物。
5. NFR/Reliability：Crash、disk full、backup/restore、大 Repo/PDF、Renderer Security、Team Identity、Canonical Unit 进入 Release Gate。

# 27. V1.3 Architecture Freeze Rules

8. Flash 成功不得直接等价于允许执行器运行。
9. SQL 业务状态变化与 Outbox Event 必须原子提交。
10. 多 Domain 组合不得依赖 import/load 顺序。
11. AI 源码修改必须先 PatchProposal，再基于 SourceRevision/ETag apply。
12. Tauri/WebView 渲染外部内容必须 sanitize + CSP + navigation isolation。
13. 工程计算统一 canonical unit + dimension normalization。
14. FOC Release Gate 必须先通过 recovery/domain/source/commissioning/NFR hard gates。


---

<!-- FILE: 01_TECHNICAL_SPEC.md -->

# Embedded Engineering Agent
## 技术实现规格书 V1.3

# 1. 技术基线

Backend：Python 3.12+、FastAPI、Pydantic v2、SQLAlchemy 2.x、Alembic、pytest、ruff、mypy。  
Frontend：Tauri、React、TypeScript、TanStack Query、Zustand、React Router。  
Data：SQLite → PostgreSQL；Qdrant；Local FS → S3/NAS。  
Agent：`AgentRuntime` Port，初始 LangGraph Adapter。  
LLM：`AIProvider` Port，初始 LiteLLM Adapter。  
Document：`DocumentParser` Port，初始 Docling Adapter。

# 2. 仓库结构

```text
embedded-engineering-agent/
├── apps/{backend,desktop,cli}
├── core/
├── domain/{common,requirement,claim,device,hardware,firmware,protocol,test,review}
├── application/
├── agents/
├── memory/
├── knowledge/
├── discovery/
├── importers/
├── rules/
├── ports/
├── adapters/
├── runtimes/
├── plugins/
├── schemas/
├── migrations/
├── prompts/
├── benchmarks/
├── tests/
├── examples/
└── docs/
```

# 3. 依赖方向

`UI → API/Application → Domain → Ports ← Adapters/Plugins`

Domain 禁止直接依赖 LangGraph、LiteLLM、Qdrant、SKiDL、pyOCD、PlatformIO。

# 4. Core Ports

AIProvider、DocumentParser、RetrievalService、ClaimProvider、DeviceProvider、RepositoryProvider、ProjectImporter、SchematicBackend、EDAService、BuildService、StaticAnalysisService、DebugProbeService、SerialService、CANService、SimulatorService、InstrumentService、StorageService、SandboxService、SecretService、ResourceLockService、BudgetService。

# 5. Application Services

Project、Artifact、ArtifactDependency、Evidence、Claim、ClaimResolver、Issue、Decision、Traceability、Job、Permission、ResourceLock、Budget、Requirement、Document、Device、PinPlanner、Architecture、HardwareDesign、CircuitDesign、MCUConfig、FirmwareDesign、MotorControl、Protocol、Test、Review、Debug、Repair、Memory、Knowledge、Discovery、RepositoryIntelligence、ProjectImport、Plugin、ToolRegistry。

# 6. Agent Runtime

```python
class EngineeringAgent(Protocol):
    name: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    async def run(self, context, input): ...

class AgentRuntime(Protocol):
    async def execute(self, workflow_id, input, context): ...
    async def cancel(self, run_id): ...
    async def resume(self, run_id): ...
    async def get_state(self, run_id): ...
```

AgentRun 保存 prompt/model/input-output hash/tool/artifact/issue/evidence/usage/duration，不保存私有 chain-of-thought。

# 7. Job

状态：QUEUED、RUNNING、BLOCKED_PERMISSION、BLOCKED_RESOURCE、SUCCESS、FAILED、CANCELLED。

PDF parse、Repository analyze、Import、Schematic/ERC、Build、Review、Test、Simulation、Debug/Repair 全部 Job 化。

# 8. Artifact

至少记录：id、project_id、logical_name、artifact_type、version、schema_version、content_hash、input_hash、dependency_ids、dependency_hashes、created_by、source_job、generator_version、tool_versions、knowledge_snapshot、storage_uri、status。

# 9. Claim / Evidence

EngineeringClaim：subject_ref、predicate、value、applicability、evidence_ids、verification_levels、confidence、source_priority、source_version、lifecycle。

Evidence Locator 支持 page/section/table/repo_commit/path/line/symbol/rule/tool/test/import run。

# 10. EngineeringValue

```python
class EngineeringValue(BaseModel):
    unit: str
    nominal: float | None = None
    minimum: float | None = None
    typical: float | None = None
    maximum: float | None = None
    tolerance_percent: float | None = None
    condition: dict[str, Any] = {}
    evidence_ids: list[UUID] = []
```

# 11. EventBus

初期 InProcess，未来 Redis/NATS。事件包含 ProjectCreated、ImportCompleted、ClaimUpdated、PinMapUpdated、ArtifactCreated、ArtifactMarkedStale、BuildCompleted、IssueCreated、RepairCompleted、KnowledgePromoted。

# 12. Prompt Registry

每个 Agent Prompt 声明 purpose、version、model_policy、allowed_tools、input/output schema、evidence requirements、fallback、max_steps、budget_policy。

# 13. Schema Versioning

Requirement、EngineeringClaim、HardwareIR、CircuitIR、MCUConfigIR、FirmwareIR、MotorControlIR、ProtocolIR、TestIR、KnowledgeEntry、PluginManifest 均带 schema_version。Breaking change 使用新 major + migration。

# 14. API / Frontend

REST `/api/v1`，WS `/ws/v1`。Backend OpenAPI 是唯一事实源，生成 TypeScript SDK。Server state 用 TanStack Query，UI local state 用 Zustand。Mutation 使用 revision/If-Match，长任务使用 Job + WS。

# 15. Tool Registry / Degraded Mode

ToolInfo：id、version、capabilities、permissions、health、available、degraded_reason、platform、path。工具不可用时能力降级，禁止假成功。

# 16. Permission / Lock / Budget

Permission：READ、WRITE、BUILD、NETWORK、SECRET_USE、FLASH、DEBUG、HARDWARE_CONTROL、DELETE、PLUGIN_INSTALL、KNOWLEDGE_PROMOTE、EXPORT_PRIVATE。

ResourceLock 对 DebugProbe/Serial/CAN/Instrument/HardwareTarget 等独占资源做 lease/heartbeat/audit。

Budget 支持 max_tokens、max_llm_cost、max_repo_size、max_clone_bytes、max_candidates、max_deep_analysis、max_runtime、max_parallelism。

# 17. Secret

Secret 不进入 Prompt、Memory、Artifact、普通日志、Export。使用 OS keyring/Vault/加密 Secret Store。

# 18. Desktop Local Backend

Tauri 启动 FastAPI sidecar：loopback-only、random ephemeral port、per-launch random bearer token、前端通过 Tauri IPC 获取、REST/WS 强制鉴权、broad CORS 默认关闭。

# 19. Quality Gate

Python：ruff、mypy、pytest、architecture tests。TypeScript：typecheck、lint、component/API contract tests。核心 Domain coverage ≥80%。

# 20. Definition of Done

Schema/Error/Test/Migration 明确；第三方经 Adapter；关键结果有 Evidence；Artifact dependency 正确；Permission/Lock/Budget 正确；无关键 TODO；Mock 不冒充真实集成；通过对应里程碑验收。

# 21. AI Provider Foundation 与 Full Agent Runtime 分层

`AIProvider`、Secret handling、Prompt Registry、StructuredGenerationService、schema validation 必须在 Requirement/Architecture 等 AI 能力之前实现。LangGraph/checkpoint/resume/multi-agent orchestration 属于后续 Full Agent Runtime。

```text
Early:
AIProvider Port → LiteLLM Adapter → Structured Output → Schema Validation

Later:
AgentRuntime → Workflow → Checkpoint → Resume → Tool Orchestration → Human Approval
```

禁止前期 Agent/Service 偷偷直连模型 API，避免 M18 再重构一套临时 AI 层。

# 22. Sandbox Foundation

在首次处理外部 Git/Archive/Build Script 前必须具备 SafePath、archive traversal/symlink 防护、隔离工作目录、no-secret execution、CPU/RAM/time/process 限制与默认 network deny。后续可演进成 Container/VM Sandbox Hardening。

# 23. Domain Extension Infrastructure

Core 提供：

- `DomainExtensionRegistry`
- `DomainDescriptor`
- `DomainIRRef`
- `DomainRuleProvider`
- `DomainGeneratorProvider`
- `DomainUIContribution`
- `DomainCapability`
- `DomainContextContributor`

MotorControl 安装在 `plugins/builtin/motor_control/`。API/Frontend 通过 Domain Registry 动态发现，不允许 Core 通过固定 import 依赖 MotorControl。

# 24. ELKB Services / Ports

新增 Application Services：

- `LearningKnowledgeService`
- `LearningDocumentService`
- `KnowledgeNormalizationService`
- `TechnicalKnowledgeDiscoveryService`

优先复用现有 DocumentParser、KnowledgeEntry、Evidence、Scope、Trust、Lifecycle、RetrievalService，不复制 Document/Memory 基础设施。

必要扩展 Port：

```python
class LearningKnowledgeProvider(Protocol):
    async def search(self, query, context): ...
    async def get(self, knowledge_id): ...

class TechnicalKnowledgeSourceProvider(Protocol):
    async def discover(self, query, budget): ...
    async def inspect(self, candidate_id): ...
```

# 25. Claim Predicate Registry

EngineeringClaim 不允许长期依赖完全自由的 `value: Any`。引入 `ClaimPredicateRegistry`，每个 predicate 声明 value schema、applicability schema、unit dimension、conflict strategy、validation policy。原型期可兼容 Any，但写入时必须经过 registry normalization。

# 26. Static Analysis Baseline

Cppcheck + Core Firmware Rules 属于 FOC Minimal E2E 前置能力，不再放在 E2E 之后。最少规则：APP_DIRECT_HAL_CALL、ISR_BLOCKING、DEPENDENCY_CYCLE、MCUCONFIG_FIRMWARE_MISMATCH。

# 27. V1.3 Execution Reliability

新增 Core Service/Port：`EventOutboxService`、`RecoveryService`、`IndexRebuildService`、`SourceWorkspaceService`、`PatchProposalService`、`DomainCompositionService`、`HardwareCommissioningService`、`SafetyStateService`、`UnitNormalizationService`；团队模式增加 `IdentityAuthorizationService`。

EventBus 初期仍可 InProcess，但只负责传输持久化 Outbox 事件，不承担唯一持久一致性。

# 28. Canonical Unit

EngineeringValue 写入时保存 canonical_unit、dimension 与 normalized value。Rule/Claim conflict/Equation 运算只使用 normalized 值；dimension 不一致直接 validation error。

# 29. Source Authority

FirmwareIR/MCUConfigIR 表达工程意图；Git Working Tree 是用户源码字节 SSOT；Artifact 不可变。BuildRun/TestRun/ReviewRun 均绑定 SourceRevision。AI edit 先生成 PatchProposal，再 apply。

# 30. Desktop Renderer Security

Repository/README/ELKB 等不可信内容必须 sanitize；强制 CSP、remote navigation deny、external-link isolation 与最小 Tauri capability allowlist。


---

<!-- FILE: 02_DOMAIN_MODEL_AND_SCHEMA.md -->

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

FirmwareModule：name、layer、responsibility、public_api、dependencies、timing、state、errors、testability、requirement_ids。

# 17. MotorControlIR

至少：motor、inverter、encoder、current_sense、pwm、adc_sampling、electrical_angle、loops、sign_convention、startup、limits、faults。详见 16 文档。

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


---

<!-- FILE: 03_DATABASE_AND_STORAGE_DESIGN.md -->

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


---

<!-- FILE: 04_AGENT_WORKFLOW_SPEC.md -->

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


---

<!-- FILE: 05_KNOWLEDGE_MEMORY_SPEC.md -->

# Embedded Engineering Agent
## Knowledge & Memory Specification V1.3

# 1. 定位

EEA 的“学习”默认不是修改模型参数，而是建立可控、可追溯、可更新、可删除、可冲突、可审计、可按 Scope 隔离的外部工程知识系统。

# 2. 三层记忆

**Global Engineering Memory**：Datasheet Fact、Device Knowledge、Reference Architecture、Pattern、Anti-Pattern、Verified Debug Case、Test Pattern、Rule、Public Reference Project。  
**Project Memory**：Requirement、Claim、Architecture、PinMap、Hardware/Circuit/MCU/Firmware/Motor IR、ADR、Issue、Build/Test、Debug History、User Confirmed Facts。  
**Task Working Memory**：current goal、temporary snippets、candidate repos、tool output、hypotheses、alternatives、unverified assumptions；任务结束默认清理。

# 3. Scope

GLOBAL_PUBLIC、USER_PRIVATE、PROJECT_PRIVATE、ORGANIZATION_PRIVATE。Query 必须显式带 scope context。

# 4. Promotion

`TASK_ONLY → PROJECT_CANDIDATE → PROJECT_VERIFIED → GLOBAL_CANDIDATE → GLOBAL_TRUSTED`

Task finding 不自动保存；Project Candidate 只在当前项目；Project Verified 需要明确验证；Global Candidate 需要通用化；Global Trusted 需要 Curator/Policy；Private → broader scope 必须 privacy/license/redaction/approval。

# 5. Verification

AI_INFERRED、REFERENCE_SUPPORTED、DOCUMENT_VERIFIED、RULE_VERIFIED、TOOL_VERIFIED、SIMULATION_VERIFIED、HARDWARE_VERIFIED、USER_CONFIRMED、IMPORT_VERIFIED。

# 6. Trust / Lifecycle / Freshness

Trust Score 0~1，考虑 source reliability/priority、independent sources、verification、hardware/tool validation、maturity、freshness、conflict、applicability。  
TrustLevel：UNTRUSTED/LOW/MEDIUM/HIGH/TRUSTED。  
Lifecycle：CANDIDATE/ACTIVE/TRUSTED/STALE/CONFLICTED/DEPRECATED/ARCHIVED/REJECTED。  
记录 created_at/updated_at/last_verified_at/source_version/source_commit/source_release/freshness_score。

# 7. Claim-aware Knowledge

结构化事实优先进入 EngineeringClaim；Architecture/Pattern/DebugCase 等高层知识进入 KnowledgeEntry。避免所有知识都降级成自由文本 chunk。

# 8. Conflict

冲突不直接删除，记录 context、applicability、tradeoff、source version、device revision、selected resolution，形成 Context-Aware Knowledge。

# 9. ERIS

保存 Repository metadata、commit、Architecture、Modules、Patterns、Anti-Patterns、Tests、Debug Cases、License、Quality、Evidence、Claims，不只是 raw code chunks。

Repository Knowledge Package：

```yaml
project: {name: null, repository: null, commit: null, license: null}
domains: []
architecture: {layers: [], data_flow: [], control_flow: [], scheduling: null, error_model: null}
modules: []
patterns: []
anti_patterns: []
tests: []
debug_cases: []
claims: []
quality: {}
evidence: []
```

# 10. OSDLE

Provider 支持 GitHub/GitLab/Gitee/Vendor/Local，V1.3 初始 GitHubProvider。OSDLE 只负责发现和候选，不直接修改 Global Trusted。

KnowledgeGap 按 domain 统计 source count、trusted count、verified claims、reference architecture、debug cases、test patterns、freshness、stale ratio。

# 11. Candidate Lifecycle

`DISCOVERED → SCREENING → SHALLOW_ANALYZED → SANDBOXED → DEEP_ANALYZED → REVIEWED → APPROVED → PRODUCTION`，也可 REJECTED/DEPRECATED。

# 12. 分级分析

Level 0 Metadata：language/update/license/release/size。  
Level 1 Shallow：tree/build/docs/module folders/tests/symbol sampling。  
Level 2 Deep：AST/dependency/architecture/pattern/issue-PR/test-debug mining。  
仅高分项目进入 Deep。

# 13. Quality Score

初始权重：domain relevance 20、architecture 15、docs 10、tests 10、hardware validation 10、maintenance 10、reproducibility 5、release 5、community 5、security 5、license clarity 5。通过 Benchmark 调整。

# 14. License-aware Retrieval

记录 detected license、evidence、code reuse policy、architecture reference policy、attribution、commercial risk。“参考架构”和“复制代码”必须分开。

# 15. Issue Mining

优先提取 `Issue → linked PR → merged commit → regression test → released fix`。DebugCase 可信度由 maintainer confirmation/merge/test/release/reproduced 提升。

# 16. Project Experience

真实项目 Issue/Fix/Test/Root Cause/ADR/Hardware Result 首先只进入 Project Memory，经通用化和 Curator 才可成为 Global Candidate。

# 17. Retrieval Ranking

Scope Filter → Lifecycle Filter → Applicability Filter → semantic relevance + project relevance + trust + verification + freshness + domain fit。

# 18. Context Compression

deduplicate、claim merge、evidence merge、rank、summarize、respect token budget；结构化 Claim 优先于自由文本摘要。

# 19. Forget / Deprecate / Privacy

支持删除 Task Memory、归档 Project Memory、Deprecate Global Knowledge、Revoke bad source、Re-index source update、Errata 触发 Claim invalidation。严禁用户私有代码自动进入公共 ERIS，必须有 cross-project leakage tests。

# 20. Curator / Budget

Curator 负责 deduplicate、claim conflict、evidence、license、generalization、trust、promotion。OSDLE 必须配置 max_candidates/max_clone_bytes/max_repo_size/max_deep_analysis/max_llm_tokens/max_cost/max_runtime，禁止无限自动学习。

# 21. Engineering Knowledge Platform V1.3

```text
Engineering Knowledge Platform
├── Datasheet Intelligence   # Hardware/Device Facts
├── Device Intelligence      # Structured Device Facts
├── ELKB                     # Theory/Principle/Algorithm/Guideline
├── ERIS                     # Real Engineering Reference
├── Engineering Rules        # Deterministic Validation
├── Project Experience       # Verified Local Experience
└── Memory & Knowledge Lifecycle
```

职责边界：

- Datasheet：器件实际上能做什么。
- Device：如何机器可读表示器件能力。
- ELKB：为什么这样设计、背后的理论/原理/算法/工程方法。
- ERIS：成熟工程通常怎么实现。
- Rule Engine：当前方案是否违反确定性规则。
- Project Experience：过去真实项目发生了什么。

# 22. ELKB Knowledge Types

核心类型：CONCEPT、PRINCIPLE、ALGORITHM、FORMULA、DESIGN_GUIDELINE、BEST_PRACTICE。

ALGORITHM 至少记录 Inputs、Outputs、Assumptions、Steps、Applicable Conditions、Limitations；FORMULA 记录变量、单位、假设、适用条件、限制、Evidence。

# 23. ELKB Domain Taxonomy

第一阶段重点：MCU Fundamentals、ARM Cortex-M、STM32、FreeRTOS、Communication、Motor Control、Power Electronics、Embedded Firmware Architecture、Debugging、Testing。

第二阶段：Embedded Linux、EtherCAT、ROS2、Robotics、USB、Ethernet、OTA。

完整 Taxonomy 可扩展 CPU/MCU Architecture、Peripheral、Control Theory、Hardware Design、PCB/EMC、Boot/OTA、Reliability/Safety 等，但 V1.3 不要求一次填满。

# 24. Authority + Trust + Verification

AuthorityLevel：T0 Standard/Official → T6 AI Inference。Authority 与 Trust 不同；同一来源可以 Authority 高但因版本过期而 Freshness/Trust 下降。

Retrieval 先做 Scope/Lifecycle/Applicability Filter，再综合：
Semantic Relevance + Authority + Trust + Verification + Freshness + Project Relevance + Domain Applicability。

# 25. ELKB 不是普通 RAG

`PDF → Chunk → Embedding` 只是 Retrieval 基础层。正式链路必须包含 Knowledge Extraction、Normalization、Concept/Principle/Algorithm/Guideline、Evidence、Authority、Trust、Lifecycle。

EEA 的“主动学习”仍然指外部可控知识系统，不默认修改模型权重，不自动 Fine-tuning。

# 26. Copyright / License

技术知识发现必须记录 SourceLicense、UsagePolicy、StoragePolicy、QuotationPolicy、RetrievalPolicy。不能无差别复制受版权保护教材全文；必要时仅保存 metadata、结构化摘要、knowledge extraction、evidence link 和合规短引用。

# 27. Private ELKB

用户学习资料默认 USER_PRIVATE/PROJECT_PRIVATE；跨 Scope Promotion 必须 privacy/license/redaction/approval。Project A 私有资料不得被 Project B 检索。

# 28. Multi-source Fusion

设计/Review/Debug 的 ContextBuilder 应能组合：

Device Facts + Datasheet + ELKB Theory + ERIS Practice + Rules + Project Experience。

例如 FOC current sensing 同时需要 MCU ADC/Timer facts、PWM synchronous sampling principle、current reconstruction algorithm、VESC/ODrive implementation、ADC range/timing rules 和本项目 offset/noise Debug history。


---

<!-- FILE: 06_RULE_ENGINE_SPEC.md -->

# Embedded Engineering Agent
## Rule Engine Specification V1.3

# 1. 定位

Rule Engine 是确定性工程验证层。LLM 负责候选/解释/排序/Debug 假设；Rule 负责合法性、边界计算和确定性 Issue。

# 2. 执行阶段

PRE_GENERATION、POST_GENERATION、PRE_TOOL、POST_TOOL、RELEASE_GATE。

示例：PinPlanner 前检查 device/package/peripheral 能力，PinPlanner 后检查 conflict/AF/debug pin；Schematic 后执行 electrical rules + ERC。

# 3. Rule Schema

```yaml
id: HW_POWER_MOSFET_VDS_MARGIN_001
version: "1.1"
stage: PRE_GENERATION
domain: POWER
severity: CRITICAL
inputs: [bus_voltage_max, transient_voltage, mosfet_vds_rating]
parameters:
  required_margin: {default: 1.2}
condition: {implementation: python}
evidence_requirements: [bus_voltage_source, mosfet_datasheet]
```

复杂规则优先 Python，避免过早复杂 DSL。

# 4. Interface / Result

Rule 不直接查数据库，Context 由 RuleEngine 构造。Result 状态 PASS/FAIL/NOT_APPLICABLE/UNKNOWN，UNKNOWN ≠ PASS，并输出 severity/affected/measured/threshold/evidence/recommendation/claim refs。

# 5. Rule Packs

CoreMCUPack、STM32Pack、MotorControlPack、PowerElectronicsPack、CANPack、RTOSPack、FirmwareArchitecturePack、SafetyPack、ImportConsistencyPack、CompanyPack、ProjectPack。

# 6. Priority

Project mandatory > Organization > Device/vendor > Domain > Core default。Override CRITICAL 必须 reason + approval + audit。

# 7. MCU / Pin Rules

PIN_CONFLICT、PIN_FUNCTION_INVALID、PIN_PACKAGE_MISSING、DEBUG_PIN_CONFLICT、BOOT_PIN_RISK、GPIO_VOLTAGE_EXCEEDED、FIVE_V_TOLERANCE_INVALID、ADC_CHANNEL_INVALID、PWM_CAPABILITY_MISSING、COMPLEMENTARY_PWM_MISSING、TIMER_CHANNEL_CONFLICT、CLOCK_SOURCE_INVALID、DMA_REQUEST_INVALID、IRQ_PRIORITY_CONFLICT。

# 8. Power Rules

INPUT_VOLTAGE_RANGE、LDO_DROPOUT、LDO_POWER_DISSIPATION、BUCK_INPUT_RANGE、BUCK_OUTPUT_CURRENT_MARGIN、MOSFET_VDS_MARGIN、MOSFET_CURRENT_MARGIN、GATE_DRIVER_VOLTAGE、POWER_DOMAIN_MISMATCH、DECOUPLING_MISSING、TRANSIENT_MARGIN。

# 9. Communication Rules

CAN：TRANSCEIVER_REQUIRED、TERMINATION、COMMON_GROUND_OR_ISOLATION、BITRATE_CLOCK_FEASIBILITY、TX_RX_PIN_VALID。  
RS485：TRANSCEIVER_REQUIRED、TERMINATION、BIASING、DE_CONTROL。  
SPI：CLOCK_LIMIT、MODE_COMPATIBILITY、VOLTAGE_LEVEL、CS_UNIQUENESS。  
I2C：PULLUP_REQUIRED、VOLTAGE_COMPATIBILITY、ADDRESS_CONFLICT。

# 10. Motor Rules

PHASE_PWM_COUNT、COMPLEMENTARY_PWM、DEADTIME_REQUIRED、CURRENT_SENSE_REQUIRED、CURRENT_SENSE_ADC_RANGE、BUS_VOLTAGE_SENSE、ENCODER_INTERFACE_COMPATIBILITY、GATE_DRIVER_FAULT_CONNECTION、EMERGENCY_PWM_DISABLE_PATH、CURRENT_LOOP_TIMING_BUDGET、ADC_TRIGGER_ALIGNMENT、SIGN_CONVENTION_COMPLETE、SPEED_FEEDBACK_SIGN_CONSISTENT、ELECTRICAL_ANGLE_DIRECTION_CONSISTENT、PI_OUTPUT_SATURATION_LIMIT、STARTUP_ALIGNMENT_REQUIRED。

# 11. Firmware / RTOS Rules

APP_DIRECT_HAL_CALL、DRIVER_DEPENDENCY_CYCLE、GLOBAL_MUTABLE_STATE_EXCESS、MODULE_API_MISSING、ERROR_HANDLING_MISSING、TIMEOUT_MISSING、HARDWARE_PIN_DUPLICATED_DEFINITION、MCUCONFIG_FIRMWARE_MISMATCH。  
ISR_BLOCKING_API、MUTEX_IN_ISR、PRIORITY_INVERSION_RISK、DEADLOCK_CYCLE、TASK_CPU_OVER_BUDGET、STACK_TOO_SMALL、LONG_CRITICAL_SECTION、UNBOUNDED_QUEUE、STARVATION_RISK。

# 12. Import Consistency Rules

IOC_PIN_CODE_MISMATCH、IOC_CLOCK_CODE_MISMATCH、SCHEMATIC_PIN_FIRMWARE_MISMATCH、BUILD_TARGET_MCU_MISMATCH、PROTOCOL_ID_CONFLICT、DUPLICATE_PIN_SOURCE_OF_TRUTH。

# 13. Evidence / Version / Test

Rule 输入必须可追溯；缺输入返回 UNKNOWN。行为变化 bump version，Issue 保存 rule id/version/input snapshot。每条 Rule 至少 positive/negative/boundary/missing input/applicability mismatch 五类测试。

# 14. ELKB 与 Rule 的边界

ELKB 可为 Rule 提供解释、公式来源、设计原理和 Evidence，但不能把“高相似度检索结果”直接当成确定性 PASS/FAIL。Rule 的输入仍必须来自结构化 Claim/IR/EngineeringValue/Tool Result。

Rule 可通过 `USED_BY_RULE` 关系引用 LearningKnowledge/EngineeringEquation，用于解释“为什么这条规则存在”，但 Rule 执行结果不由 LLM/ELKB 自由文本替代。

# 15. V1.3 Safety & Unit Rules

Core Rule 新增 ACTUATOR_ENABLE_WITHOUT_COMMISSIONING、SAFETY_LIMIT_MISSING、TARGET_IDENTITY_UNVERIFIED、SAFE_STATE_UNDEFINED、UNIT_DIMENSION_MISMATCH、SOURCE_REVISION_MISMATCH、DOMAIN_COMPOSITION_CONFLICT。

Core Safety Rule 不得被 Domain Plugin 降级；Domain 只能增加更严格规则或专项验证。


---

<!-- FILE: 07_SECURITY_PERMISSION_SPEC.md -->

# Embedded Engineering Agent
## Security & Permission Specification V1.3

# 1. 威胁模型

EEA 会读源码、Clone Repo、运行编译器、解析文档、执行 Build Script、连串口/CAN、烧录 MCU、控制仪器、保存 API Key。假设外部仓库/文件可恶意、README 可 Prompt Injection、Build Script 可执行任意命令、Plugin 可越权、多项目可泄漏、本机其他进程可攻击 local backend。

# 2. 原则

Least privilege、deny by default、explicit permission、sandbox untrusted execution、secrets never in prompts、project isolation、auditable side effects、resource locking、human confirmation。

# 3. Permission / Risk

Permission：READ、WRITE、BUILD、NETWORK、SECRET_USE、FLASH、DEBUG、HARDWARE_CONTROL、DELETE、PLUGIN_INSTALL、KNOWLEDGE_PROMOTE、EXPORT_PRIVATE。

LOW：读公开数据/纯验证。MEDIUM：修改项目/trusted build。HIGH：sandbox network/private credential/flash/memory write/hardware control/delete/global promotion/destructive Git。

# 4. Secret

LLM API Key、Git token、SSH、private registry、instrument credential。前端仅显示 configured + masked。AgentContext 默认不含 Secret，Backend 在 Tool Adapter 执行时注入，LLM 不看到真实值。

# 5. Repository Prompt Injection / Sandbox

Repository content 永远作为 untrusted data。Sandbox 默认 no host home/no SSH agent/no API token/no user project mount/read-only base/writable temp/process+CPU+RAM+timeout limit/network off or allowlist。

公共 Repo 的 Make/CMake/Python hook 不可信，依赖下载走 controlled resolver/allowlist/cache。

# 6. Path / Shell / Upload

防 `../`、absolute breakout、symlink escape、UNC/Windows drive escape、archive traversal。禁止 Agent 自由 `shell=True`，优先 structured argv/predefined command template。Upload 做 MIME/extension/size/archive bomb/filename normalize/safe extraction。

# 7. Plugin Security

Manifest 声明 permissions/network/filesystem/dependencies/entrypoint/publisher，未声明能力不得调用。企业可禁止未签名 Plugin。

# 8. Knowledge Privacy / Logs

Private → broader scope 必须 policy/redaction/license/approval。日志禁止 API key/token/private key/secret env/proprietary full source；必要时保存 hash/reference。

# 9. Hardware Safety

FLASH/HARDWARE_CONTROL 必须显示 target/device identity/firmware hash/probe/expected effect，并要求 Permission Token + Resource Lock + timeout。仪器后续增加 voltage/current hard limits、emergency stop、watchdog。

# 10. Destructive Git

Hard reset、force push、delete unmerged branch、clean、overwrite user changes 必须确认。AI Repair 默认新 branch。

# 11. Desktop Local Backend Security

Tauri + FastAPI sidecar 必须：仅绑定 loopback；动态随机端口；每次启动 256-bit session secret；前端通过 Tauri IPC 获取；REST Bearer；WS 握手鉴权；broad CORS 关闭；不监听 LAN；token 不写日志；退出即失效。

# 12. Resource Lock

FLASH/DEBUG/HARDWARE_CONTROL 前 acquire → verify target → execute → release。同一 probe/device 不允许并发控制。

# 13. Auth/RBAC / Audit

团队版 OIDC/OAuth + Organization + Project Role：Viewer/Engineer/Maintainer/Admin。审计 permission、flash、hardware control、secret use、plugin install、global promotion、destructive Git、export、force lock release、override critical。

# 14. Security Tests

覆盖 repository prompt injection、path traversal、symlink escape、secret log leak、cross-project leak、sandbox secret access、permission bypass、malicious plugin、idempotency replay、local backend unauthorized access、WS auth bypass、resource lock bypass。

# 15. Plugin Trust Tier

- Bundled Trusted Plugin：可在受控策略下 In-Process。
- Signed Trusted Plugin：按组织策略决定 In-Process/Out-of-Process。
- Community/Untrusted Plugin：必须 Out-of-Process + Sandbox，不能仅靠 Manifest Permission 作为安全边界。

V1.3 首发只要求 Bundled Trusted Domain Plugin 完整可用；第三方 Marketplace 不作为 Release 必需能力。

# 16. ELKB Source Safety / Copyright

Learning Document、课程资料、论文、Blog 同样视为外部不可信输入，防 Prompt Injection/恶意文件。用户私有资料不进入公共索引；Technical Knowledge Discovery 必须检查 license/storage/extraction policy。

# 17. Desktop Renderer / WebView Security

EEA 渲染 README、Repository docs、ELKB、Issue/Log 等不可信内容时必须 sanitize Markdown/HTML、strict CSP、deny arbitrary remote navigation、external URL isolation、最小 Tauri capability allowlist、禁止 remote JS plugin，并隔离 backend token/secret。

# 18. Actuator Safety Permission

新增 `ACTUATOR_ENABLE` 或等价高风险 capability。FLASH 与 ACTUATOR_ENABLE 分离；Emergency Stop 后重新使能需重新通过审批/策略检查。


---

<!-- FILE: 08_FRONTEND_BACKEND_API_CONTRACT.md -->

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


---

<!-- FILE: 09_FRONTEND_UX_SPEC.md -->

# Embedded Engineering Agent
## Frontend UX Specification V1.3

# 1. 定位

前端是工程 IDE，不是聊天 UI。AI 是右侧持续辅助能力，中央区域管理真实工程对象。

# 2. Simple / Expert Mode

Simple：New Project、Import Project、上传资料、输入需求、AI Design、AI Check、AI Debug。  
Expert：Requirement DSL、Claims、Device Facts、Pin Planner、Hardware/Circuit/MCU/Firmware/Motor IR、RTOS、Rules、Evidence、Artifacts、Agent Runs、Memory、Repository Intelligence、Dependency Graph。

# 3. App Shell

顶部：Project / Branch / Build / Search / Active Jobs / Settings。左侧导航工程对象，中间 Workspace，右侧 AI Assistant/Evidence/Actions/Issues。

# 4. Dashboard

New Project、Import Project、Recent Projects、Active Jobs、Critical/High Issues、Tool Health、Stale Artifacts、Knowledge Updates。

# 5. New Project / Import

New Project：Name/Type → Stage → MCU/SoC → optional source → Tool capability check → Create。  
Import：Git URL/Local folder/Archive/.ioc/KiCad；显示 detected build system/MCU/toolchain/files/facts/conflicts/IR candidates/build issues；用户 Accept/Compare/Ignore/Lock fact。

# 6. Project Overview

Requirement completeness、Device/Pin status、HW/FW status、Build status、Test coverage、Review issues、Verification、Stale count、Engineering Score、Current Stage、Recommended Next Action。

# 7. Documents / Claims / Requirements

Documents：左列表，中 PDF/Text，右 extracted claims/evidence/conflicts/AI question。  
Claims：subject/predicate/value/applicability/source/verification/conflict，可打开 source locator。  
Requirements：表格+Form，Analyze/Extract/Validate/Missing/Recommendation Accept/Edit。

# 8. Architecture / Pin Planner

Architecture block diagram 支持 regenerate/lock/explain/compare/stale marker。  
Pin Planner 左 required signals，中 package/pin view，右 candidates/hard constraints/conflicts/evidence；支持 auto/manual/lock/validate/export。非法 Pin 必须后端 reject。

# 9. Hardware / Circuit / Schematic

Hardware Tabs：System、Power、Components、Interfaces、PinMap、Circuit、Schematic、BOM。  
Circuit 显示 Net/critical nets/power nets/EngineeringValue/Evidence，Expert 可编辑 IR。  
Schematic 显示 version/backend/ERC/dependency status/stale reason/compare/export；V1.3 不自研完整 EDA 编辑器。

# 10. MCUConfig / Firmware / MotorControl

MCUConfig：Clock tree、GPIO、Timer/PWM、ADC、DMA、IRQ、Debug，每项可定位 Device Claim/Evidence。  
Firmware：Architecture、Modules、MCU Config、RTOS、Code、Build、Static Analysis；Code View tree/diff/AI edit/build error jump/stale marker。  
Motor Control：Motor params、Encoder、Current sense、PWM、ADC timing、Electrical angle、Sign convention、Current/Velocity/Position loops、Limits/Faults。

# 11. Protocol / Tests / Review / Debug

Protocol 表格编辑 Message/ID/Direction/Period/Fields，实时显示 CAN Payload 与 C/Python/DBC generator status。  
Tests 显示 Plan/Coverage/Cases/Runs/Results，失败 Case 一键 Create Debug Session。  
Review Issue Board 显示 evidence/claim/rule/tool/recommendation/repair。  
Debug 左 Symptom/Logs/Attachments，中 Root Cause/Verification Plan，右 AI/Evidence/Related MCU/Motor objects。

# 12. Knowledge / Repository

Knowledge Center：Global、Project Memory、Reference Projects、Patterns、Anti-Patterns、Debug Cases、Candidates、Gaps、Claims。  
Repository Candidate Card 显示 repo/domain/score/freshness/license/analysis level/estimated cost/status，支持 shallow/deep/project reference/global candidate/reject。

# 13. AI Panel / Evidence

Context chips：project、module、issue、claim、document、code、artifact。Actions：Explain、Review、Generate、Compare、Fix、Create Test、Why stale?。Evidence icon 可定位 Datasheet page/Device claim/Rule/Repo commit/Tool result/Hardware test/Import source。

# 14. Staleness / Long Job / Permission

Artifact 显示 CURRENT/STALE/INVALID、stale cause、old/new hash、recommended regenerate order。  
Job 显示 status/progress/phase/logs/budget/cancel。  
危险操作显示 target/firmware hash/risk/expected effect/resource lock/Confirm。  
Resource Busy 显示 owner job/operation/lock expiry，不静默抢占。

# 15. Style

简约高级、专业工程工具、高信息密度、清晰层级、深浅色、中文默认、i18n 预留，不用巨型聊天气泡主导。

# 17. Knowledge Center / Learning Knowledge

Knowledge Center：

```text
Overview
Device Knowledge
Datasheet
Learning Knowledge
Reference Projects
Architectures
Patterns
Debug Cases
Knowledge Gaps
Candidates
```

Learning Knowledge 页面：Domain Navigation、Search、Knowledge Type、Authority、Trust、Source、Related Concepts/Algorithms/Rules/Debug Cases。

Detail：Definition、Explanation、Applicable Conditions、Limitations、Formula、Examples、Source、Authority、Trust、Verification、Relations。

ELKB 主要消费者仍是 Engineering Agent；V1.3 不把前端做成在线课程系统。Explain/Learning/Interview Mode 仅作为后续扩展。

# 18. Dynamic Domain Navigation

Frontend 不固定假设 MotorControl 存在。通过 `/projects/{id}/domains` + `/ui/extensions` 获取导航、表单、动作和 capability；未激活 Domain 不显示对应页面。

# 19. V1.3 Safety / Source / Recovery UX

新增 Source Status、Domain Extensions、Commissioning、Recovery Center。Actuator Enable 页面持续显示 Target identity、firmware hash、Safety Profile/limits、ResourceLock 与 Emergency Stop；不得用普通 “Run” 按钮模糊表达。


---

<!-- FILE: 10_BENCHMARK_TEST_SPEC.md -->

# Embedded Engineering Agent
## Benchmark & Test Specification V1.3

# 1. 目的

EEA 不能以“回答看起来不错”衡量。Model/Prompt/Knowledge/Rule/Agent/Adapter/Device DB/Claim Resolver/Generator 的修改都必须能通过固定 Benchmark 判断退化。

# 2. Test Pyramid

Unit、Schema、Architecture Dependency、Migration、Integration、Tool Adapter、Agent Contract、Security、Import、Artifact Invalidation、Benchmark、E2E、Hardware Regression。

# 3. Benchmark A：FOC Motor Controller

固定输入：STM32G431、DRV8323、AS5047、24V、10A、PMSM、FOC、CAN、UART、Current/Velocity/Position modes。

评分：Requirement 8、Device/Pin 15、Claim/Evidence 10、Hardware 10、Circuit/Electrical 10、MCUConfig/Timing 12、MotorControlIR 10、Firmware/Build 10、Test/Traceability 5、Review 5、Hallucination 5，总分 100。

# 4. Hard Fail

fabricated pin、unsupported AF accepted、package mismatch、关键电气超限未报告、Compiler/ERC fail 却 PASS、Secret leak、Private Memory leak、Candidate repo 自动 Trusted、stale artifact 当 CURRENT、local backend 未鉴权、resource lock bypass、危险硬件操作无 Permission、明显 `.ioc`/firmware Pin 冲突未报告。

# 5. Pin / Claim / Electrical Tests

Pin：合法 TIM1 complementary、非法 AF、package missing、debug conflict、duplicate、wrong package，非法条件 100% reject。  
Claim：Datasheet vs Community、Errata 覆盖 Datasheet、Package applicability、Revision-specific、缺 Evidence，要求冲突显式且 source priority 正确。  
Electrical：48V+40V MOSFET、5V→non-tolerant 3.3V GPIO、CAN missing transceiver/termination、ADC overrange、gate driver supply invalid、current sense saturation、transient margin insufficient。

# 6. MCUConfig / MotorControl Negative Tests

MCUConfig：wrong timer channel、unsupported complementary、impossible timer frequency、invalid ADC trigger、invalid DMA request、IRQ conflict、PinMap mismatch。  
MotorControl：encoder reversed、electrical angle sign inconsistent、phase sequence mismatch、speed feedback sign mismatch、PI no saturation、startup alignment missing、ADC sample window invalid、current-loop CPU budget exceeded。

# 7. Firmware Negative Tests

everything in main.c、Application direct HAL、dependency cycle、blocking API in ISR、missing timeout、duplicated hardware Pin、Generator 忽略 MCUConfig。

# 8. Existing Project Import Benchmark

真实 STM32CubeMX/CMake 或 PlatformIO 项目。要求识别 MCU/build system/main modules/pin/clock/protocol hints，输出 Import Report。故意 `.ioc` 与源码 Pin 不一致必须 Issue。

# 9. Artifact Invalidation Benchmark

Generate PinMap v1 → Circuit/Schematic/Firmware → 修改 PWM Pin → PinMap v2。必须使 CircuitIR/Schematic/MCUConfig/Firmware BSP stale；不相关 Protocol docs 不应无条件 stale。

# 10. Memory / Promotion / Security

Project A private DebugCase 对 Project B 不可见；Task 不能直接 Global Trusted；private scope expansion 需 policy/approval。恶意 README/build script/symlink 必须被隔离。

# 11. Local Backend / Resource Lock

无 Bearer Token 调 REST/WS 必须拒绝；旧 launch token 失效。两个 Job 同时抢同一 Debug Probe：一个 acquire，一个 RESOURCE_BUSY，不得并发 flash。

# 12. API / Agent / RAG / Tool

CI 检查 OpenAPI→TS Client 同步，Breaking API 仍 v1 则 Fail。Agent 输出必须 Pydantic validation。Datasheet benchmark 固定 supply/AF/peripheral/electrical/timer/CAN/package 问题，关键事实必须 Claim + Evidence。Tool benchmark 至少 KiCad ERC、CMake、PlatformIO、Cppcheck、pyOCD、Renode、Import parser。

# 13. Metrics

统计 hallucination rate、Evidence coverage、critical issue recall、stale propagation accuracy、import accuracy、security pass、budget usage。目标：P0 Decision ≥95% Evidence；Device/Pin critical facts 100%；CRITICAL Issue 100% evidence 或 UNKNOWN；Motor sign/timing critical fact 100%。

# 14. Traceability / Budget / Regression

P0 Requirement ≥1 implementation link + ≥1 verification link，否则 Release Gate Fail。Repository Discovery 必须记录 candidates/shallow/deep/clone bytes/tokens/cost/runtime，超 budget 停止。

每版本输出 Version、FOC/Gateway/Robot/import score、Pin/Claim accuracy、Evidence coverage、hallucination、critical recall、stale accuracy、security、budget、knowledge snapshot、rule/prompt version。

# 15. CI / Release

CI 必须 unit、ruff/mypy、architecture、migration、API compatibility、security、import smoke、artifact invalidation smoke、benchmark smoke、package build。Release Report 保存 Benchmark/Known Issues/Tool Versions/Model Config/Prompt/Rule/Knowledge/Schema/Migration。

# 16. Core Neutrality Smoke Benchmark

FOC E2E 后立即运行：

`STM32G431 + UART + CAN + SPI Sensor + FreeRTOS`，不激活 MotorControl Plugin。

必须完成 Requirement → Device → Pin → MCUConfig → Firmware → Build → Static Analysis → Protocol → Test → Review。若 Core import/Schema/API/Frontend 强依赖 motor_control，Hard Fail。

# 17. ELKB Benchmark

1. Knowledge Retrieval：问“为什么 FOC 电流采样通常需要与 PWM 同步？”必须返回 PRINCIPLE + 高权威 Evidence。
2. Cross-source Fusion：设计 PMSM current sensing，结果必须组合 Device、Datasheet、ELKB、ERIS、Rules。
3. Authority Ranking：Official Application Note 必须优先于 Random Blog（其他条件相当）。
4. Conflict：不同 Learning Source 观点冲突时保留 applicability/conditions，不任意覆盖。
5. Private Isolation：Project A 私有学习资料对 Project B 不可检索。
6. Formula：EngineeringEquation 必须含变量/单位/assumptions/applicability/evidence，不能只返回字符串公式。

# 18. E2E Gate Definition Update

FOC Minimal E2E 的 `Build` 必须是 Real Build，且在 Release Gate 前执行 Cppcheck + Core Firmware Rules。Sandbox Foundation 必须早于任何外部 Repo/Archive/Build Script benchmark。

# 19. V1.3 Reliability / Safety Hard Gates

新增 Hard Fail：未经 commissioning 自动 actuator/PWM enable；E-stop 后自动 resume；SQL commit 后 crash 导致依赖永久不传播；Event replay 重复 Artifact/SideEffect；stale PatchProposal 覆盖新源码；Domain composition 依赖 load 顺序；恶意 Markdown 可调用 privileged API；Qdrant 丢失导致事实不可恢复；unit dimension mismatch 仍参与计算。

# 20. Crash Recovery Benchmark

注入 SQL commit→dispatch 前 kill、Object put→SQL commit 前 kill、Qdrant update kill、Git patch→metadata 前 kill、ResourceLock holder kill、Commissioning 中 cancel/kill。

# 21. Domain Composition Benchmark

覆盖 0/1/2/3 Domain、missing dependency、conflict、generator cycle、plugin migration。

# 22. Hardware Commissioning Benchmark

FOC 至少验证 SafeState、current limit、encoder direction、phase/sign、ADC offset、low-power、closed-loop limited、E-stop。

# 23. NFR Benchmark

覆盖大 Repo/PDF、并发 Job、disk full、DB locked、tool missing、network offline、WS resync、index rebuild、backup/restore。


---

<!-- FILE: 11_CODEX_IMPLEMENTATION_AND_ACCEPTANCE.md -->

# Embedded Engineering Agent
## Codex 开发任务拆分与验收标准 V1.3 — Architecture Freeze

# 1. 总执行纪律

每次只完成一个 Milestone：`Implement → Test → Review → Acceptance → Commit`。上一阶段未通过不得继续。阶段结束更新 CHANGELOG、TEST_REPORT、KNOWN_ISSUES、NEXT_PHASE。

禁止：Mock 冒充真实集成；Domain 直接依赖第三方；无 Migration 改表；LLM 绕过 Schema/Rule；LLM 猜 Pin；外部 Repo 自动 Trusted；外部代码未隔离执行；危险动作绕 Permission；Secret 入 Prompt/日志；STALE 冒充 CURRENT；Resource Lock 绕过；Core 硬编码 MotorControl。

# 2. V1.3 总策略

```text
Foundation
→ AI Provider Foundation
→ Claim/Document/Device
→ Sandbox Foundation
→ Requirement + Pin/Rule
→ Hardware/Circuit/Schematic
→ MCUConfig + Firmware + Static Analysis
→ Domain Extension Infrastructure
→ MotorControl Built-in Plugin
→ Protocol/Test/Review + Engineering Dependency Graph
→ V1.3 Reliability/Domain/Source/Commissioning Gates (M18A–M18E)
→ FOC Minimal E2E
→ Core Neutrality Smoke
→ Desktop UI
→ Existing Project Import
→ Knowledge Core + ELKB MVP
→ ContextBuilder + Full Agent Runtime
→ ERIS/Repository Intelligence
→ OSDLE + Technical Knowledge Discovery
→ Debug/Repair/Hardware
→ Gateway/Robot
```

FOC 是 Reference Benchmark，不是独立产品或 Core 子系统。

# M0 Repository Skeleton

FastAPI、React/Tauri placeholder、CLI、SQLAlchemy/Alembic、pytest/ruff/mypy、CI、health、OpenAPI export。验收启动/迁移/CI。

# M1 Core Domain

Project、Artifact、Evidence、Issue、Decision、Job、Permission、Traceability、revision/optimistic lock、schema registry。Core Domain coverage ≥80%。

# M2 AI Provider Foundation

AIProvider Port、LiteLLM Adapter、SecretService、Prompt Registry、StructuredGenerationService、Pydantic output validation、usage/budget accounting。

验收：结构化输出、provider failure、timeout、budget、secret not prompt/log。此阶段不做复杂 multi-agent workflow。

# M3 EngineeringValue + Claim Core

EngineeringValue、EngineeringClaim、ClaimConflict、ClaimResolver、ClaimPredicateRegistry、source priority、applicability。Errata/package/revision conflict 可验证；无 Evidence 不得 DOCUMENT_VERIFIED。

# M4 Document + Device Intelligence

Upload、DocumentIR、Docling Adapter、Claim extraction、STM32 Device Provider、多源 merge。STM32G431 PA8/TIM1_CH1、Complementary PWM、FDCAN、ADC/DMA/package query、非法 AF reject。

# M5 Sandbox Foundation

SafePath、Archive traversal/symlink 防护、isolated workspace、no secrets、network deny by default、process/CPU/RAM/runtime limit、structured command execution。

验收：恶意 archive/symlink/build script 无法越界读取 host/key。M5 未通过禁止外部 Repo/Archive Build。

# M6 Requirement DSL

profiles/schema/NL analyze/completeness，调用 M2 StructuredGeneration，不直连模型。FOC Requirement 缺失项能发现。

# M7 Pin Planner + Core Rule Engine

PinRequirement/Candidate/Assignment/Lock/Constraint Solver；PIN_CONFLICT、PIN_FUNCTION_INVALID、GPIO_VOLTAGE、PWM_CAPABILITY、ADC_CHANNEL、DEBUG_PIN_CONFLICT 等。非法条件 100% reject/unknown，不猜 PASS。

# M8 SystemArchitecture / HardwareIR / Component

SystemArchitectureIR、HardwareIR、PowerDomain、Interface、Component Selection。FOC benchmark 只作为输入数据，不向 Core Schema 添加 motor-only 字段。

# M9 CircuitIR + Electrical Rules

CircuitComponent/Net/PowerNet/Constraint；MOSFET_VDS、ADC_RANGE、GATE_DRIVER_VOLTAGE、CAN_TRANSCEIVER、TERMINATION 等。

# M10 Schematic / KiCad

SKiDLBackend、KiCad CLI、ERC、Artifact creation。CircuitIR → editable schematic/netlist；缺关键连接 → ERC Issue。

# M11 MCUConfigIR

ClockIR、GPIO、PWMConfig、ADCConfig、DMAIR、InterruptConfigIR。MCUConfigIR 是 Timer/PWM/ADC/DMA/IRQ 唯一事实源。

# M12 FirmwareIR + Generator + Real Build

Firmware layers/modules、BSP/Platform、STM32 HAL skeleton、CMake/PlatformIO Adapter、build diagnostics。Firmware 必须读取 PinMap + MCUConfigIR。

# M13 Static Analysis + Firmware Rules

Cppcheck；APP_DIRECT_HAL_CALL、ISR_BLOCKING、DEPENDENCY_CYCLE、MCUCONFIG_FIRMWARE_MISMATCH。FOC E2E 前必须完成。

# M14 Domain Extension Infrastructure

DomainExtensionRegistry、DomainDescriptor、DomainIR envelope、rule/generator/context/UI hooks、capability routing。建立 `plugins/builtin/`。

验收：空 Domain 列表仍能创建普通 MCU 项目；Core 无 `import motor_control`。

# M15 MotorControl Built-in Plugin

位于 `plugins/builtin/motor_control/`。实现 MotorControlIR、MotorControlAgent/Rules/Generator/UI metadata。

关键约束：
- MotorControlIR 保存控制需求与 refs；
- actual timer/channel/deadtime/ADC trigger/DMA/IRQ 读取 MCUConfigIR；
- inverter/encoder/current-sense hardware 通过 HardwareIR refs；
- 不制造第二事实源。

# M16 ProtocolIR

CAN Transport、Message/Field、C/Python/DBC/Markdown Generator、Codec Tests。一个 IR 修改后所有产物同步。

# M17 Test / Traceability / Review

TestIR、Coverage、Traceability、Review Engine、Issue dedupe。P0 无 Test → Review Fail；AI 不覆盖 Compiler/ERC/Rule 明确失败。

# M18 Engineering Dependency & Impact Graph

DependencyNodeRef + EngineeringDependencyEdge，覆盖 Requirement/Claim/Pin/Selection/IR/KnowledgeSnapshot/Artifact/Test。实现 stale/invalid propagation、impact analysis、revalidate/regenerate plan。

验收：Errata Claim supersede 能传播到受影响 Pin/MCUConfig/Firmware；无关 UI metadata 不传播。

# V1.3 Mandatory Pre-FOC Gates

以下 Milestone 插入 M19 FOC Minimal E2E 前：

## M18A Transactional Outbox & Recovery
outbox/processed events/SideEffectJournal/RecoveryService/crash injection。SQL commit→crash 后可重放；重复消费不产生重复 Artifact。

## M18B Domain Composition Contract
DomainActivation + requires/conflicts/capability routing/Rule & Generator DAG/activation API。0/1/2+ Domain 与 conflict/cycle 可确定处理。

## M18C Source Authority & Workspace
SourceRevision、PatchProposal、SafePath、ETag/If-Match、Git working-tree SSOT、generated/diverged ownership。Build/Test/Review 全绑定 SourceRevision。

## M18D Hardware Commissioning & Safety
CommissioningProfile/Session/SafetyLimit/SafeState/EmergencyStop；Flash 与 Actuator Enable 分离；FOC 首次闭环使用 limited profile。

## M18E Renderer / NFR Hardening
CSP/sanitize/navigation isolation/Tauri capability allowlist、canonical unit、team identity schema foundation、backup/restore/failure injection baseline。

M18A–M18E 未通过，M19 不得标 PASS。

# M19 FOC Minimal E2E Release Gate

Create Project → Requirement → Claims/Device → Architecture → PinMap → Hardware/Circuit → Schematic/ERC → MCUConfig → activate MotorControl Plugin → MotorControlIR → Firmware → Code → Real Build → Cppcheck/Firmware Rules → Protocol → Test → Review。

硬验收：0 fabricated pin、0 known pin conflict、critical electrical issue recall、real build、static analysis、critical evidence、traceability、impact propagation、no secret/private leak。

# M20 Core Neutrality Smoke Gate

不加载 MotorControl Plugin：STM32G431 + UART + CAN + SPI Sensor + FreeRTOS，完成 Requirement → Pin → MCUConfig → Firmware → Build → Static Analysis → Protocol → Test → Review。

任何 Core Schema/API/Frontend 对 motor_control 的强依赖均 Fail。

# M21 Desktop UI Vertical Slice

Dashboard、Project、Requirement、Documents、Pin、Hardware、Schematic、MCUConfig、Firmware、Domain Extensions、Protocol、Tests、Review、Settings、AI Panel。Domain UI 动态加载。

# M22 Existing Project Import

Local/Git/CMake/PlatformIO/Makefile/.ioc/KiCad scan。所有外部 materialization/build 依赖 M5 Sandbox Foundation。`.ioc` vs source pin mismatch → Issue。

# M23 Knowledge & Memory Core

KnowledgeEntry、MemoryEntry、Scope、Trust、Lifecycle、Promotion、AuthorityLevel、KnowledgeRelation。Cross-project isolation、Private promotion policy。

# M24 ELKB-1 Learning Knowledge Domain

KnowledgeType 扩展、LearningKnowledge、EngineeringEquation、AuthorityLevel、SourcePolicy、KnowledgeRelation。复用 KnowledgeEntry/Evidence/Scope/Trust/Lifecycle。

# M25 ELKB-2 Learning Document Extraction

用户上传 Learning Document → DocumentIR → Concept/Principle/Algorithm/Formula/Guideline extraction → normalization → Evidence。默认 USER_PRIVATE/PROJECT_PRIVATE。

# M26 ELKB-3 Authority / Trust / License

Authority ranking、SourceLicense/Storage/Quotation/Retrieval policy、conflict/applicability、private isolation。官方资料在同等相关度下优先于低质量 Blog。

# M27 ELKB-4 ContextBuilder Integration

ContextBuilder 动态融合 Facts + Theory(ELKB) + Practice(ERIS) + Rules + Experience。先做 ELKB retrieval benchmark；禁止简单 vector similarity 直接决定答案权威性。

# M28 Full Agent Runtime

EngineeringAgent、AgentRuntime、LangGraphAdapter、checkpoint/retry/resume/cancel、tool orchestration、human approval。复用 M2 AIProvider。

# M29 ERIS Foundation

首批 ingest SimpleFOC、VESC、ODrive、Zephyr、FreeRTOS、TinyUSB、lwIP、MCUboot。所有外部 Repo 受 Sandbox/Budget 管理。

# M30 Repository Intelligence

Scanner、Build detection、File classification、symbol/dependency、architecture/module summary。RepositoryKnowledge 必须 commit-bound。

# M31 OSDLE + Budget

KnowledgeGap、RepositoryProvider、CandidatePool、Metadata→Shallow→Deep、Budget gate。候选不能自动 Production/Trusted。

# M32 ELKB-5 Technical Knowledge Discovery

作为统一 Discovery Provider 的 document-discovery capability：Official App Note/Training/Guide/Open-access Course/Paper/Engineering Article。Authority/License/Budget → ELKB Staging → Curator。不得另造重复 OSDLE/Curator 框架。

# M33 Sandbox Hardening + Curator

Container/VM adapter、network allowlist、dependency resolver、security hardening、Curator promotion/deprecation/conflict。恶意 Repo/Plugin 无 host secret。

# M34 Debug / Repair / Git

Debug Root Cause Ranking + ELKB principle + ERIS reference + Project History；Repair 使用 branch/diff/build/test/review/rollback。速度反向高速至少检查 encoder direction、electrical-angle sign、phase sequence、speed feedback sign、PI saturation。

# M35 Hardware Debug / Resource Lock / Simulation

pyOCD/OpenOCD、probe identity、FLASH/DEBUG permission、ResourceLock；Renode Simulation。真实板 Flash→Reset→SafeState→Commissioning；通过 Safety Gate 后才允许受限 Run。

# M36 Gateway / Robot Benchmarks

Gateway：CAN + RS485 + Ethernet + Modbus + MQTT + OTA，不加载 MotorControl，验证 Core neutrality。

Robot Joint：FOC + CAN FD + EtherCAT + Absolute Encoder + IMU + Brake + ROS2-facing，验证多 Domain Plugin 组合。

# 3. Release Discipline

每个 Release 必须通过：Core tests、security、migration、API compatibility、FOC benchmark、Core Neutrality、Import、Impact Graph、ELKB retrieval/fusion/private isolation，以及该 Release 激活能力对应的 Tool integration。

# 4. 阶段报告格式

TEST_REPORT：milestone/environment/tests/pass-fail/skips/tool versions/benchmark delta/budget usage。  
KNOWN_ISSUES：severity/impact/workaround/planned milestone。  
NEXT_PHASE：scope/dependencies/blockers。  
任何 skipped hard gate 必须明确标记，不得转写为 PASS。


---

<!-- FILE: 12_DEPLOYMENT_DEV_ENV.md -->

# Embedded Engineering Agent
## Deployment & Development Environment V1.3

# 1. 支持目标

Windows 11、Linux、Local Desktop、Backend Service、CI；后续 Docker/企业部署。

# 2. 工具链

Python 3.12+、Node.js LTS、pnpm、Rust stable、Tauri stable、Git、Docker/Podman。第三方工程工具版本由 ToolRegistry 探测，不在 Domain 硬编码。

# 3. Backend / Frontend

```bash
python -m venv .venv
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

pnpm install
pnpm dev
pnpm tauri dev
```

# 4. Config / Local Data

Config 层级 System Default < User Config < Project Override，Secret 独立。环境变量可 EEA_ENV/EEA_LOG_LEVEL/EEA_DATA_DIR/EEA_DB_URL。

Windows `%LOCALAPPDATA%/EEA/`；Linux `~/.local/share/eea/`，包含 db/objects/cache/logs/tool metadata/session metadata。

# 5. Tool Discovery

启动探测 kicad-cli/platformio/cmake/cppcheck/pyocd/openocd/renode。缺失不阻止 App 启动，由 `/capabilities` 告知前端。

# 6. Desktop Sidecar

Tauri → choose random loopback port → generate random session token → start FastAPI sidecar → health/auth handshake → frontend 通过 IPC 获得 token。Backend 只监听 loopback。

# 7. Sandbox

初期 Docker/Podman Adapter，接口 `SandboxService`，后续可替换 Windows Sandbox/VM/bwrap/firejail。

# 8. CI

Python lint/typecheck/unit/architecture/migration → Frontend typecheck/lint → OpenAPI client diff → Security → Import smoke → Artifact invalidation smoke → Benchmark smoke → Package build。

# 9. OpenAPI Client

CI 启动 Backend/export OpenAPI → generate TypeScript Client → generated code dirty 则 Fail。

# 10. Packaging / Service Deployment

Tauri 输出 Windows installer/Linux package。团队版：Web/Desktop → Backend → PostgreSQL/Qdrant/Object Storage/Worker/Sandbox Runner。V1.x 单机可单进程 JobExecutor。

# 11. Observability / Backup / Upgrade

Structured logs 使用 request_id/job_id/agent_run_id/tool_run_id/import_run_id/resource_lock_id，Secret redaction。单机 Project export + DB/Object/Qdrant snapshot；团队 PostgreSQL backup + Qdrant snapshot + Object versioning。

升级前 Compatibility Check、Migration Dry-run、Backup、Schema Migration、Plugin Compatibility、Knowledge index migration，失败可 rollback。

# 12. Offline Mode / Profiles

后续支持 local LLM/Embedding/cached Device DB/ERIS snapshot；Offline 时 OSDLE 停止。

推荐 dev profiles：minimal、foc-dev、full、ci。`foc-dev` 默认 KiCad、CMake/PlatformIO、Cppcheck、pyOCD、optional Renode。

# 13. V1.3 Profiles

`minimal`：Core + AIProvider mock/real selectable + no external execution。  
`foc-dev`：Core + builtin.motor_control + KiCad/CMake/PlatformIO/Cppcheck + Sandbox Foundation。  
`knowledge-dev`：Document/Embedding/ELKB/ERIS/Discovery adapters。  
`full`：全部已安装 capabilities。  
`ci`：固定 Tool versions + isolated sandbox + benchmark datasets。

外部 Repo/Build 测试默认走 Sandbox Foundation，不能因为本地开发方便而直接执行不可信脚本。

# 14. V1.3 Recovery / Desktop Security

App 启动：`Compatibility Check → DB Migration → Recovery Scan → Outbox Worker → Index Health → Tool Discovery → API Ready`。存在 unresolved hardware session、blocking migration 或关键一致性问题时进入 Recovery Mode。

Tauri package 强制 CSP、禁止任意 remote navigation、最小 IPC capability。CI 增加 crash/failure injection、backup-restore、Qdrant rebuild、workspace reconcile、renderer security。


---

<!-- FILE: 13_PLUGIN_SDK_SPEC.md -->

# Embedded Engineering Agent
## Plugin SDK Specification V1.3

# 1. 目标

新增 MCU、Tool、Protocol、Instrument、Agent、Generator、Domain、Importer、Knowledge Source 不修改 Core。

# 2. Plugin Types

AgentPlugin、DevicePlugin、RulePlugin、ToolPlugin、GeneratorPlugin、ParserPlugin、RepositoryPlugin、InstrumentPlugin、DomainPlugin、ImporterPlugin、KnowledgeSourcePlugin、UIExtensionMetadataPlugin。

# 3. Built-in Domain Plugin

MotorControl 是首个官方 Built-in Domain Plugin，目录 `plugins/builtin/motor_control/`，使用与外部 DomainPlugin 相同的 manifest/schema/rule/generator/UI contribution 契约。

Core 只认识 DomainDescriptor/DomainIRRef/Capabilities，不认识 FOC 字段。

# 4. Manifest

```yaml
id: org.eea.motor_control
name: Motor Control
version: 1.3.0
api_version: "1"
plugin_type: domain
trust_tier: bundled
entrypoint: eea_motor_control.plugin:Plugin
capabilities: [motor_control.ir, motor_control.review, motor_control.codegen]
permissions: [READ, WRITE, BUILD]
dependencies: []
```

# 5. Domain Contract

DomainPlugin 可以新增 schema/rules/generators/knowledge/context/UI metadata，但不得：
- 修改 Core Schema 既有语义；
- 在 Core DB 私自建无命名空间表；
- 复制 MCUConfigIR 的实际 Timer/ADC/DMA/IRQ 配置成为第二事实源；
- 要求所有 Project 激活该 Domain。

# 6. Dynamic API/UI

Domain 通过 `/projects/{id}/domains` 注册 capability。Frontend 使用 `/ui/extensions` 动态增加导航/表单/动作。固定 `/motor-control` 路径只能作为 builtin plugin compatibility alias。

# 7. Generator / Device / Rule / Tool

Generator 输入使用 Core IR + registered Domain IR。  
DevicePlugin 实现 find/get/pin/peripheral/validate/get_claims。  
RulePlugin 提供 stable rule id/version/tests/no uncontrolled side effect。  
ToolPlugin 提供 ToolInfo/capability/health/permission/Port implementation。

# 8. Importer / Repository / Knowledge Source

RepositoryPlugin：search/metadata/clone-fetch/issues/PR/releases。  
ImporterPlugin：detect/parse/extract facts/generate IR candidates/diagnostics。  
KnowledgeSourcePlugin：发现或访问 Technical Learning Sources，返回 metadata/authority/license/extraction policy；不得绕过 ELKB Curator。

# 9. Trust Tier / Isolation

- `bundled`：EEA 官方随产品发布，可受控 In-Process。
- `signed_trusted`：组织信任签名插件，策略决定 In/Out Process。
- `community_untrusted`：必须 Out-of-Process + Sandbox。

Manifest Permission 不是 OS 安全边界。V1.3 Release 只要求 bundled plugin 完整支持。

# 10. Agent / UI Extension

AgentPlugin 声明 input/output schema、allowed tools、required knowledge domains、prompt、budget profile。UI Extension 第一阶段只允许 navigation/action/form metadata，不允许任意 remote JS。

# 11. Security / Data / Test

安装显示 publisher/source/signature/trust tier/permissions/network/filesystem/dependencies。私有数据 namespaced。必须测试 manifest、compatibility、permission、schema、unit、integration、health、sandbox、core-neutrality。

# 12. V1.3 Domain Composition Contract

DomainDescriptor 声明 requires/optional/conflicts/capabilities/priority/rule phases/generator phases/migration provider。Registry 构建 composition DAG，禁止用插件加载顺序决定语义。

Domain 可贡献 CommissioningStep/Rule，但 Core SafetyState、Permission、ResourceLock、EmergencyStop 不可被绕过或降级。Plugin disable 不删除项目 Domain 数据；upgrade 先 compatibility + migration plan。


---

<!-- FILE: 14_ENGINEERING_GLOSSARY.md -->

# Embedded Engineering Agent
## Engineering Glossary V1.3

**Project**：独立工程工作区与 Project Memory 隔离边界。  
**Requirement DSL**：需求稳定内部 Schema。  
**EngineeringValue**：带单位、范围、容差、条件、Evidence 的可计算工程数值。  
**EngineeringClaim**：Subject-Predicate-Value-Applicability-Evidence 的原子工程事实。  
**Claim Conflict**：两个 Claim 在适用范围重叠时的事实冲突。  
**Claim Resolver**：按来源、Revision、Package、Condition 处理 Claim 冲突的服务。  
**Device / Device Instance**：器件能力模型 / 项目内具体实例。  
**SystemArchitectureIR**：系统功能块与接口。  
**HardwareIR**：与 EDA 无关的硬件模块/器件/电源域/接口。  
**CircuitIR**：元件/Pin/Net/电源/电气约束。  
**MCUConfigIR**：时钟、GPIO、Peripheral、DMA、IRQ 等 MCU 配置唯一内部表示。  
**FirmwareIR**：Firmware 层、模块、Task、ISR、依赖与资源。  
**MotorControlIR**：Motor/Encoder/CurrentSense/PWM/ControlLoop/SignConvention 等电机控制模型。  
**ProtocolIR**：通信协议唯一事实源。  
**TestIR**：测试环境、用例、Pass Condition。  
**Pin Requirement / Assignment**：功能对 Pin 的要求 / 到具体 Pin-AF 的映射。  
**Artifact**：导入或生成的版本化工程产物。  
**Artifact Dependency Graph**：Artifact 上下游依赖图。  
**Stale Artifact**：上游变化后不再保证有效的 Artifact。  
**Evidence**：支撑事实、设计、Issue、Knowledge 的可追溯来源。  
**Issue**：Rule/Tool/AI/Test/Debug/Import 发现的问题。  
**ADR**：工程选择及理由记录。  
**Traceability**：Requirement、Architecture、Implementation、Test 的关系。  
**Rule / Rule Pack**：确定性约束 / 一组版本化规则。  
**Pre-generation Rule**：生成前约束。  
**Post-generation Rule**：生成后验证。  
**Review Engine**：Schema + Claim/Evidence + Rule + Tool + Staleness + AI 综合审查。  
**Agent / Agent Runtime**：有明确 Schema/职责/工具的工程节点 / 编排运行抽象。  
**Port / Adapter**：核心能力抽象接口 / 第三方实现。  
**Plugin / Domain Plugin**：不改 Core 的扩展包 / 特定工程领域扩展。  
**ERIS**：Embedded Reference Intelligence System。  
**OSDLE**：Open Source Discovery & Learning Engine。  
**Repository Knowledge Package**：Repository 经过结构化工程分析后的知识包。  
**Engineering Pattern / Anti-Pattern**：通用成熟设计模式 / 高风险常见模式。  
**Debug Case**：Problem → Root Cause → Fix → Verification 的结构化案例。  
**Global / Project / Task Memory**：公共长期 / 项目长期 / 当前任务临时记忆。  
**Memory Promotion**：知识向更广 Scope 受控晋升。  
**Trust Score / Verification Level / Lifecycle / Scope**：可信度、验证层级、生命周期、可见范围。  
**Knowledge Gap / Curator**：知识覆盖不足 / 去重、冲突、License、Evidence、Promotion 管理。  
**Sandbox**：隔离执行不可信 Repo/Script。  
**Capability**：Backend/Plugin/Tool 声明的可用能力。  
**Permission**：READ/BUILD/FLASH 等受控权限。  
**Resource Lock**：对 Probe/Port/Instrument 等独占资源的租约。  
**Budget**：Token/Cost/Runtime/RepoSize 等执行上限。  
**Job / ToolRun / AgentRun / ImportRun**：长任务 / 工具执行 / Agent 执行 / 项目导入执行。  
**Single Source of Truth**：某类事实只有一个权威内部表示。  
**Degraded Mode**：能力缺失时明确降级而不是假成功。

**ELKB / Embedded Learning Knowledge Base**：嵌入式学习与工程理论知识库，保存 Concept/Principle/Algorithm/Formula/Guideline 等 Theory Knowledge。  
**Authority Level**：知识来源权威等级 T0~T6，与 Trust Score 分离。  
**LearningKnowledge**：ELKB 的正式 KnowledgeEntry subtype。  
**EngineeringEquation**：带变量、单位、假设、适用条件、限制和 Evidence 的结构化公式。  
**Technical Knowledge Discovery**：发现官方技术资料、开放课程/论文和高质量工程资料的 Discovery capability。  
**Domain Extension Registry**：Core 管理 0..N Domain Plugin 的注册、Capability、Schema、Rule、Generator、UI Hook。  
**Built-in Domain Plugin**：随 EEA 发布但不属于 Core Schema 的官方插件，例如 MotorControl。  
**Core Neutrality**：不加载垂直 Domain Plugin 时 Core 仍能完成通用嵌入式工程闭环。  
**Engineering Dependency & Impact Graph**：跨 Requirement/Claim/IR/Artifact/Test/Knowledge Snapshot 的通用依赖与变化影响图。  
**Claim Predicate Registry**：为 EngineeringClaim predicate 定义 value/applicability schema、unit 与 conflict strategy 的注册表。

**Hardware Commissioning Session**：Firmware 从 Flash 到允许真实执行器正常运行的分阶段安全验证会话。  
**SafeState**：Crash/Cancel/Fault 时硬件必须进入或尝试进入的安全输出状态。  
**SafetyLimit**：Commissioning/Hardware run 的结构化电压、电流、速度、占空比、时间限制。  
**Transactional Outbox**：业务 SQL transaction 同时保存待投递事件，防止 commit 与 EventBus 之间丢事件。  
**Processed Event / Inbox**：Consumer 幂等记录。  
**SideEffectJournal**：Git/Flash/外部写入等不可简单回滚动作的意图、前后状态与补偿记录。  
**Domain Composition**：多个 Domain 的依赖、冲突、capability、rule/generator ordering 解析。  
**DomainActivation**：Project 激活某 Domain/version/configuration 的版本化对象。  
**SourceRevision**：Git working tree/commit/tree hash 对应的精确源码版本。  
**PatchProposal**：AI/Agent 产生、尚未应用到源码 SSOT 的可审查修改。  
**Canonical Unit**：工程值归一化后的标准单位与 dimension。


---

<!-- FILE: 15_PROJECT_IMPORT_REVERSE_ENGINEERING_SPEC.md -->

# Embedded Engineering Agent
## Existing Project Import & Reverse Engineering Specification V1.3

# 1. 目标

Existing Project Import 是 V1.3 核心能力。用户真实场景往往是分析、修 Bug、改 Pin、升级 MCU、做协议、Review 现有项目，而不是只从空目录生成。

# 2. 输入

V1.3 最少支持 Local folder、Git repository、ZIP/TAR、CMake、Makefile、PlatformIO、STM32CubeMX `.ioc`、STM32CubeIDE project、KiCad project、raw C/C++ source。后续扩 Keil/IAR/Zephyr/Yocto/Buildroot。

# 3. Pipeline

```text
Source
→ Safe Materialization
→ File Inventory
→ Build System Detection
→ Toolchain Detection
→ MCU/Board Detection
→ Config Parser
→ Source/Symbol Scan
→ Dependency
→ Pin/Clock/Peripheral Facts
→ Protocol Hints
→ Claim Extraction
→ IR Candidate Generation
→ Build(optional)
→ Static Analysis
→ Consistency Review
→ Import Report
```

# 4. 安全与只读

导入阶段 read-only、no silent rewrite、no auto cleanup。外部 archive/repo 做 path/symlink safety 和 sandbox；Build 默认需策略允许。

# 5. CubeMX `.ioc`

优先提取 MCU/Package、Pin assignment、Clock tree、TIM/PWM、ADC、DMA、NVIC、UART、CAN/FDCAN、SPI/I2C，转为 Claims + PinMap candidate + MCUConfigIR candidate。

# 6. Build / MCU Detection

识别 CMakeLists.txt、platformio.ini、Makefile、CubeIDE metadata、compile_commands.json、linker script、startup file。

MCU 证据优先级：explicit config(.ioc/board) > compiler defines > linker/startup > CMSIS header > build flags > filename inference。冲突生成 ClaimConflict。

# 7. Firmware Reverse Engineering

提取 modules/public APIs/interrupt handlers/RTOS tasks/HAL-LL calls/global state/peripheral init/pin macros/protocol handlers，形成 FirmwareIR + MCUConfigIR candidate + Issues。

# 8. Hardware Reverse Engineering

KiCad 提取 symbols/nets/MCU pins/power/interfaces/connectors/transceiver/gate driver，形成 CircuitIR candidate。

# 9. Cross-source Consistency

必须检查 `.ioc` pin vs source、schematic pin vs firmware、MCU package vs Device DB、clock config vs bitrate/timer、protocol docs vs source IDs。

# 10. Import Report

包含 Detected Project Type/MCU/Board/Build/Toolchain/Peripherals/Protocols/Hardware Files/Claim Count/IR Candidates/Build Result/Static Analysis/Conflicts/Critical Issues/Unknowns/Recommended Next Actions。

# 11. Evidence / Merge

Imported Fact 保存 file path/line/symbol/parser-tool version/content hash，可标 IMPORT_VERIFIED，但不自动等价于 Datasheet Verified。

Imported candidate 与 current IR 使用 compare/merge/accept imported/keep current/manual resolve，禁止 silent overwrite。

# 12. Acceptance

FOC Existing Project Import Benchmark：MCU detected、`.ioc` Pin extracted、build system detected、firmware module summary；故意 `.ioc` vs source pin mismatch → HIGH Issue。

# 13. V1.3 Sandbox Precondition

Safe Materialization/Sandbox Foundation 是 Import 的硬前置依赖。Archive extraction、Git checkout、Build/Configure Script 不得直接在宿主工作区无隔离执行。只读扫描也必须做 path/symlink/size safety。

Import 输出的 motor-control hints 只能形成 Domain IR Candidate；只有项目激活 MotorControl Plugin 后才解析成 MotorControlIR。

# 14. V1.3 SourceRevision Import

Import 完成后必须创建初始 SourceRevision/tree hash；Imported facts/IR candidate/Build 绑定该 revision。后续用户代码变化不能让旧 Import Report 继续冒充当前状态。


---

<!-- FILE: 16_MOTOR_CONTROL_DOMAIN_SPEC.md -->

# Embedded Engineering Agent
## Motor Control Built-in Domain Plugin Specification V1.3

# 1. 定位

MotorControl 是 EEA 首个高价值 **Built-in Domain Plugin**。FOC Motor Controller 是第一个 Reference Benchmark。MotorControl 不属于 Core Domain，不能成为所有 Project 的必经步骤。

# 2. 目录与依赖

```text
plugins/builtin/motor_control/
├── domain/
├── schemas/
├── rules/
├── agents/
├── generators/
├── knowledge/
├── ui/
└── benchmarks/
```

依赖方向：`MotorControl Plugin → Core public services/IR`。Core 禁止反向 import MotorControl。

# 3. MotorControlIR

```text
MotorControlIR
├── motor_ref / motor_parameters
├── inverter_ref
├── encoder_ref
├── current_sense_ref
├── pwm_requirement
├── adc_sampling_requirement
├── mcu_config_refs
├── electrical_angle
├── sign_convention
├── startup
├── current_loop
├── velocity_loop
├── position_loop
├── limits
└── fault_policy
```

# 4. Single Source of Truth

**MCUConfigIR 是 MCU 硬件配置唯一事实源（Single Source of Truth）。**

实际 MCU 配置只在 MCUConfigIR：

- timer / channel / complementary channel
- center-aligned mode
- realized switching frequency
- realized deadtime
- ADC instance/channel/trigger
- DMA request
- IRQ priority

MotorControlIR 只保存“控制需求、目标值、允许范围、控制语义、引用”。

例如：

```text
MotorControlIR.pwm_requirement.target_frequency = 20 kHz
MotorControlIR.pwm_requirement.center_aligned_required = true
MotorControlIR.mcu_config_refs.pwm = MCUConfigIR.peripherals[TIM1]

MCUConfigIR.PWMConfig.timer = TIM1
MCUConfigIR.PWMConfig.realized_frequency = 20 kHz
```

Rule 检查 requirement ↔ realized config 是否一致。

# 5. Hardware References

Inverter、Encoder、CurrentSense 尽量通过 HardwareIR DeviceInstance/Module 引用；Domain IR 可保存 motor-specific semantics（phase mapping、sign、offset、latency），不重复器件 MPN、电气 rating 等 Hardware Fact。

# 6. Electrical Angle / Sign Convention

显式建模 mechanical direction、electrical angle direction、phase order、positive torque current、speed feedback sign、Park convention、SVPWM phase mapping、zero offset。任何隐式 sign 都视为 Review 风险。

# 7. Loops

CurrentLoop：frequency/period、Id/Iq target、Kp/Ki、output limit、anti-windup、decoupling、sample-to-actuation latency、CPU budget。  
VelocityLoop：frequency、Kp/Ki、speed/acceleration/current limit、feedback source。  
PositionLoop：frequency、controller type、position/velocity limit、wrap handling。

# 8. Startup / Calibration

encoder alignment、electrical zero、current sensor offset、cogging calibration(optional)、open-loop ramp(optional)。每步保存 prerequisites、current/voltage limit、timeout、failure behavior、test result。

# 9. Fault Policy

overcurrent、bus over/undervoltage、driver fault、encoder loss、overspeed、stall、current-sense invalid、control overrun。Action：disable PWM/safe state/retry/latched/log/evidence。

# 10. Rules

COMPLEMENTARY_PWM、DEADTIME_REQUIRED、CURRENT_SENSE_ADC_RANGE、ADC_TRIGGER_ALIGNMENT、CURRENT_LOOP_TIMING_BUDGET、SIGN_CONVENTION_COMPLETE、SPEED_FEEDBACK_SIGN_CONSISTENT、ELECTRICAL_ANGLE_DIRECTION_CONSISTENT、PI_OUTPUT_SATURATION_LIMIT、STARTUP_ALIGNMENT_REQUIRED、MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH。

# 11. ELKB / ERIS / Debug

MotorControlAgent 查询：
- ELKB：FOC theory、current sampling、bandwidth、SVPWM、encoder/control principles；
- ERIS：VESC/ODrive/SimpleFOC 的真实实现；
- Project Experience：本项目历史故障；
- Device/Claims：MCU/encoder/driver facts；
- Rules：确定性限制。

速度反向高速：encoder raw direction → mechanical speed sign → electrical angle sign → phase order → Park/SVPWM convention → speed error sign → PI saturation → current direction。  
低速抖动：encoder quantization、current offset、minimum pulse、deadtime distortion、friction/cogging、angle latency、current loop noise、speed estimator、loop-rate ratio。

# 12. Acceptance

1. Plugin disable 后 Core Neutrality benchmark 仍 PASS。
2. Plugin enable 后 FOC E2E PASS。
3. 修改 MCUConfig PWM/ADC 时 MotorControl cross-validation 能检测 mismatch。
4. Core repo 不出现 motor-only schema import。
5. API/Frontend 通过 Domain Registry 动态出现 Motor Control 页面。

# 13. V1.3 Commissioning Safety

MotorControl 必须贡献 current offset/polarity、encoder direction/zero/wrap、phase sequence/electrical-angle sign、PWM polarity/deadtime/break、ADC sample window、gate-driver fault、bus voltage/current、loop saturation 等 Commissioning Preflight。

Production loop enable 只能通过 Core HardwareCommissioningService。sign convention 不确定时状态 UNKNOWN/BLOCKED，禁止“高速试转确认”。


---

<!-- FILE: 17_ARTIFACT_DEPENDENCY_INVALIDATION_SPEC.md -->

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


---

<!-- FILE: 18_RESOURCE_BUDGET_LOCK_EXECUTION_SPEC.md -->

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


---

<!-- FILE: 19_ARCHITECTURE_DECISIONS.md -->

# Embedded Engineering Agent
## Architecture Decision Records V1.3

# ADR-001：IR-first

Requirement → IR → Generator → Tool Verification，而不是让 LLM 直接生成复杂工程文件。原因：可验证、可替换、可 Diff、可 Migration。

# ADR-002：EngineeringClaim

关键事实使用 Claim，解决多数据源、Errata、Revision、Package、Evidence 与冲突。

# ADR-003：CMSIS-SVD 不是完整 Device 数据源

Device Provider 采用多源融合。SVD 主要用于 Peripheral/Register 信息，Pin/AF/Package/Electrical 由其他官方/结构化来源补齐。

# ADR-004：Rule Engine 前移

生成前执行 Pre-rule，生成后执行 Post-rule，避免先制造确定性错误再靠后置 Review 修复。

# ADR-005：FOC 垂直切片优先

V1.3 先完成真实 FOC E2E，再建设大规模 ERIS/OSDLE，避免“平台完整但没有工程闭环”。

# ADR-006：MCUConfigIR

Clock/GPIO/Timer/ADC/DMA/IRQ 独立建模，因为 FirmwareIR 的模块级架构不足以生成可靠 STM32 工程。

# ADR-007：MotorControl 使用 Domain Plugin

不把所有 FOC 字段硬编码进 Core FirmwareIR，保持 Core 通用，同时支持 FOC 深度建模。

# ADR-008：Artifact Staleness 是后端能力

Dependency graph + hash + invalidation，不依赖前端提示来保证工程一致性。

# ADR-009：Existing Project Import 是 V1.3 核心

已有工程的分析/修复是高频真实场景，Import 在 ERIS/OSDLE 之前完成。

# ADR-010：Desktop Sidecar 必须鉴权

loopback + random port + per-launch token，防止本机其他进程调用高风险 API。

# ADR-011：OSDLE 分级分析 + Budget

Metadata → Shallow → Deep，控制 Clone/Token/时间/成本。

# ADR-012：Graph DB 非 V1.3 依赖

先使用 SQL edge table，避免首版增加不必要基础设施。

# ADR-013：PCB Generation 不作为 V1.3 正式 capability

保留 reserved endpoint，但默认 unavailable，避免 API 与真实能力不一致。

# ADR-014：MotorControl 是 Built-in Domain Plugin

FOC 是 Reference Benchmark；MotorControlIR 不属于 Core Schema。Core 通过 DomainExtensionRegistry 激活 0..N Domain。

# ADR-015：Domain IR 不复制 MCUConfigIR

Domain 保存需求/约束/语义/ref，Timer/PWM/ADC/DMA/IRQ realized config 只在 MCUConfigIR。

# ADR-016：AI Provider Foundation 前移

Structured model invocation 是 Requirement/Architecture 的基础能力；Full Agent Runtime 后移，避免前期私建临时 LLM 调用。

# ADR-017：Sandbox Foundation 前移

任何外部 Repo/Archive/Build Script 进入执行链之前先具备最小 Sandbox；后期再做 Hardening。

# ADR-018：Static Analysis 属于 FOC E2E Gate

Cppcheck + Core Firmware Rules 必须在 FOC Minimal E2E 之前实现。

# ADR-019：Artifact Graph 升级为 Engineering Dependency & Impact Graph

Claim/Requirement/IR/Knowledge Snapshot 也可以成为变化传播源，Artifact 只是其中一种节点。

# ADR-020：ELKB 是一级 Knowledge Platform 能力

ELKB 负责 Theory/Principle/Algorithm/Guideline；不等于普通 RAG，不替代 Datasheet/ERIS/Rules/Project Experience。

# ADR-021：Authority 与 Trust 分离

Authority 表示来源级别；Trust 表示对象基于 Evidence/Verification/Freshness/Conflict 的当前可信状态。

# ADR-022：Technical Knowledge Discovery 复用统一 Discovery/Curator

TKDE 不成为重复产品模块；作为 document-discovery capability 复用 Provider、Budget、Sandbox、License、Curator。

# ADR-023：Core Neutrality 是 Release Gate

FOC E2E 后立即运行无 MotorControl 的通用 MCU smoke，防止垂直 Benchmark 反向污染 Core。

# ADR-024：Hardware Commissioning Safety Layer
Build/Flash 不能直接通向执行器运行；Core 提供 Commissioning/SafeState/SafetyLimit/EmergencyStop。

# ADR-025：Transactional Outbox
业务 mutation + outbox 同 SQL transaction，Consumer 幂等，Qdrant 可重建。

# ADR-026：Domain Composition is Deterministic
0..N Domain 通过依赖/冲突/Capability/Rule/Generator DAG 组合，不依赖 import/load 顺序。

# ADR-027：Git Working Tree is Source Byte SSOT
IR 保存设计意图；Git Working Tree 保存可编辑源码字节；Artifact 保存不可变快照。AI 修改先 PatchProposal。

# ADR-028：Canonical Units
工程值计算必须 unit/dimension normalize。

# ADR-029：Renderer is an Untrusted Content Boundary
Repository/README/ELKB 渲染强制 sanitize/CSP/navigation isolation/minimal Tauri capability。


---

<!-- FILE: 20_RELEASE_AND_VERSIONING_SPEC.md -->

# Embedded Engineering Agent
## Release & Versioning Specification V1.3

# 1. 版本对象

Product、Backend API、Schema、DB Migration、Prompt、Rule Pack、Plugin API、Tool Adapter、Knowledge Snapshot、Benchmark Dataset、Generator 都必须版本化。

# 2. Product / API

Product 使用 SemVer，V1.3 文档基线为 `1.3.0`。API 路径 `/api/v1`，Breaking API 新建 `/api/v2`。

# 3. Schema / Migration

核心 IR 自带 schema_version。Breaking change bump major，并提供 Migration。读取旧项目必须经过 migration chain。

# 4. Prompt / Rule / Plugin

Agent Prompt 保存 name/version/hash，AgentRun 绑定版本。Rule 使用 stable id + version，Issue 保存 rule version。Plugin Manifest 声明 api_version，Core 不兼容则 INCOMPATIBLE。

# 5. Knowledge Snapshot

Release 保存 global knowledge snapshot id、device DB snapshot、reference repo commits、rule pack versions，使旧 Decision 可解释。

# 6. Tool / Generator Version

KiCad、SKiDL、CMake、PlatformIO、Cppcheck、pyOCD、Renode 等关键工具版本进入 Release Report。Schematic/Firmware/Protocol Generator 版本写入 Artifact。

# 7. Compatibility Matrix

至少记录 API、Schema、Plugin API、DB migration、Desktop、Device DB snapshot、Knowledge snapshot。

# 8. Release Gate

必须通过 tests、security、migration、FOC benchmark、import benchmark、artifact invalidation benchmark、API compatibility，且无已知 P0。

# 9. Release Report

包含 Version、Build SHA、Benchmark、Known Issues、Tool Versions、Model Config、Prompt Versions、Rule Versions、Knowledge Snapshot、Schema Version、Migration Version、Plugin API Version。

# 10. Domain / ELKB Compatibility

Release Snapshot 额外记录 active built-in domain versions、Domain Plugin API version、ELKB taxonomy/schema version、Authority policy version、Learning source license policy version。

MotorControl Plugin 可以独立 minor/patch 升级，但 Core major compatibility 必须由 Plugin API matrix 约束。

# 11. V1.3 Additional Release Gate

Release Snapshot 增加 SourceRevision policy、Domain Composition contract、Commissioning/Safety schema、Outbox/Recovery schema、Unit normalization policy、Renderer security policy。Release 必须通过 crash recovery、Domain composition、Source conflict、Hardware commissioning、backup/restore、renderer security 与 NFR benchmark。


---

<!-- FILE: 21_EMBEDDED_LEARNING_KNOWLEDGE_BASE_SPEC.md -->

# Embedded Engineering Agent
## Embedded Learning Knowledge Base（ELKB）Specification V1.3
### 嵌入式学习与工程理论知识库

# 1. 定位

**ELKB 不是普通 RAG，也不是自动 Fine-tuning 系统。**

ELKB 是 EEA Knowledge Platform 的一级组成部分，主要服务 Engineering Agent 的设计、解释、审查和 Debug。

ELKB 回答：**“为什么要这样设计？背后的理论、原理、算法和工程方法是什么？”**

它不等同于：
- Datasheet/Device Facts；
- ERIS 的成熟工程实现；
- Rule Engine 的确定性判断；
- Project Memory 的本项目真实经验；
- 普通 PDF RAG；
- 自动 Fine-tuning。

# 2. Unified Knowledge Model

```text
Facts       = Datasheet + Device
Theory      = ELKB
Practice    = ERIS
Rules       = Engineering Rule Engine
Experience  = Project Memory / Verified Debug Cases
```

五类知识共同构成 Embedded Engineering Intelligence Engine。

# 3. ELKB Content Types

CONCEPT：什么是 DMA / Priority Inversion。  
PRINCIPLE：为什么 CAN 无损仲裁 / 为什么 ADC 与 PWM 同步。  
ALGORITHM：FOC/PID/LQR/Kalman/SVPWM，含 Inputs/Outputs/Assumptions/Steps/Applicability/Limitations。  
FORMULA：结构化 Equation，含变量/单位/假设/适用条件/Evidence。  
DESIGN_GUIDELINE：ADC RC Filter、CAN termination、RTOS priority design。  
BEST_PRACTICE：ISR 短、Application 不直连 HAL、Protocol 单一事实源。

# 4. Domain Taxonomy

完整可扩展 Taxonomy：

- Embedded Fundamentals
- CPU / MCU Architecture
- MCU Peripheral
- RTOS
- Embedded Linux
- Communication
- Control Theory
- Motor Control
- Power Electronics
- Hardware Design
- PCB / EMC
- Bootloader / OTA
- Robotics / ROS2
- Testing
- Debugging
- Reliability / Safety

V1.3 首批内容：MCU Fundamentals、ARM Cortex-M、STM32、FreeRTOS、Communication、Motor Control、Power Electronics、Embedded Firmware Architecture、Debugging、Testing。

# 5. LearningKnowledge

LearningKnowledge 复用 KnowledgeEntry 的 scope/trust/lifecycle/evidence，附加 topic、type、domains、definition、explanation、principles、prerequisites、applicable_conditions、limitations、examples、equations、relations、authority。

# 6. EngineeringEquation

公式必须结构化：

```text
name
expression
variables(symbol/name/unit/dimension)
assumptions
applicability
limitations
evidence
```

禁止仅保存字符串公式。

# 7. Authority Level

T0_STANDARD_OFFICIAL  
T1_OFFICIAL_TECHNICAL  
T2_TRUSTED_ACADEMIC  
T3_MATURE_ENGINEERING_REFERENCE  
T4_HIGH_QUALITY_COMMUNITY  
T5_UNVERIFIED_COMMUNITY  
T6_AI_INFERENCE

Authority 与 Trust/Freshness/Verification 分离。

# 8. Ingestion

```text
Learning Document
→ Safe Materialization
→ DocumentParser
→ DocumentIR
→ Semantic Chunk
→ Knowledge Extraction
→ Knowledge Normalization
→ Concept/Principle/Algorithm/Formula/Guideline
→ Evidence
→ Authority/License/Trust
→ ELKB Staging
→ Curator
→ Scoped KnowledgeEntry
```

Chunk/Embedding 仅是 Retrieval 基础层，不是最终知识对象。

# 9. Source Types

Official：Manufacturer Training/App Note/Programming Guide/Architecture Guide/Official Docs。  
Standard：Protocol/Architecture/Consortium Specification。  
Academic：Open-access textbook/course/paper/thesis。  
Engineering：technical guide/high-quality article。  
User Provided：学习资料、个人笔记、公司内部培训。

User Provided 默认 USER_PRIVATE/PROJECT_PRIVATE。

# 10. Copyright / License

每个来源记录 SourceLicense、UsagePolicy、StoragePolicy、QuotationPolicy、RetrievalPolicy。

不允许无差别抓取/存储受版权保护教材全文。无法长期存储全文时，只保留 Metadata、Structured Summary、Knowledge Extraction、Evidence Link 和合规短引用。

# 11. Technical Knowledge Discovery

Technical Knowledge Discovery 是统一 Discovery Provider 架构的 document-discovery capability，不另造 OSDLE 平行系统。

流程：Knowledge Gap → Candidate Pool → Authority/License/Quality → Budget → Parse/Extract → ELKB Staging → Curator。

V1.3 不要求大规模互联网爬虫、完整论文搜索系统或复杂推荐算法。

# 12. Agents

LearningKnowledgeAgent：从技术资料提取 Concept/Principle/Algorithm/Formula/Guideline。  
KnowledgeNormalizationAgent：同义概念归一到统一 Concept ID。  
KnowledgeCuratorAgent：Authority/Evidence/Duplicate/Conflict/Applicability/License/Promotion/Deprecation。  
TechnicalKnowledgeDiscoveryAgent：发现候选资料，复用统一 Provider/Budget/Sandbox。

# 13. Knowledge Relations

PREREQUISITE_OF、EXPLAINS、IMPLEMENTED_BY、VALIDATED_BY、CONTRADICTS、APPLIES_TO、RELATED_TO、DERIVED_FROM、USED_BY_RULE、HAS_DEBUG_CASE。

V1.3 以 SQL edge table 实现，不引入 Graph DB 强依赖。

# 14. Retrieval

先 Scope/Lifecycle/Applicability filter，再综合 Semantic Relevance、Authority、Trust、Verification、Freshness、Project Relevance、Domain Applicability。

同语义相关度下，官方高权威资料优先于随机 Blog；但过期/冲突仍需由 Freshness/Applicability 修正。

# 15. ContextBuilder

不同任务动态组合：

```text
Project Locked Facts
Project Verified Memory
Official Datasheet
Device Facts
Engineering Rules
ELKB Trusted Knowledge
ERIS Trusted Reference
Lower Trust Sources
AI Inference
```

不是永远固定排序；Debug/Architecture/Hardware/Firmware/Motor Control 可调整权重。

# 16. Agent Usage

System Architect：architecture principle/design guideline/reference architecture。  
Hardware Agent：electrical/power/PCB principle + device facts/reference circuit。  
Firmware Agent：software architecture/RTOS/concurrency/driver patterns。  
MotorControl Plugin：FOC theory/current sampling/bandwidth/SVPWM + reference projects/debug cases。  
Review Agent：best practice/anti-pattern/guideline/rules。  
Debug Agent：underlying principle/failure mode/debug case/device/project history。

# 17. Example: PMSM Current Sensing

Context 应组合：
- Device：STM32G431 ADC/OPAMP/Timer capability；
- Datasheet：ADC timing/electrical；
- ELKB Principle：PWM synchronous sampling；
- ELKB Algorithm：current reconstruction；
- ELKB Guideline：front-end/anti-aliasing；
- ERIS：VESC/ODrive sensing architecture；
- Debug Case：offset/switching noise/sampling point；
- Rule：ADC range/PWM trigger/timing。

# 18. Private ELKB

用户资料默认 USER_PRIVATE/PROJECT_PRIVATE。Private → broader scope 需要 privacy/license/redaction/approval。Project A 私有资料对 Project B 不可见。

# 19. Frontend

Knowledge Center 新增 Learning Knowledge。支持 Domain Tree、Search、Type/Authority/Trust Filter、Concept/Principle/Algorithm/Formula/Guideline、Source、Relations。

V1.3 不做在线课程产品；主要消费者仍是 Agent。

# 20. API

使用 `/api/v1/learning/*`；Learning Document upload/extract、Knowledge/Domain/Concept/Algorithm/Formula/Guideline retrieval、Candidate discovery/analyze/approve/reject、Relations。

# 21. Database / Vector

复用 knowledge_entries；Learning 专属 detail、engineering_equations、knowledge_relations、learning documents/candidates、source licenses/authority metadata。

Vector metadata 必须含 type/domain/authority/trust/verification/source/publisher/license/scope/lifecycle/freshness。

# 22. Lifecycle

DISCOVERED → CANDIDATE → ACTIVE → TRUSTED，可进入 STALE/CONFLICTED/DEPRECATED/ARCHIVED。未验证 Learning Document 不得直接 GLOBAL_TRUSTED。

# 23. Benchmark

- Knowledge Retrieval
- Cross-source Fusion
- Authority Ranking
- Conflict / Applicability
- Private Isolation
- Formula Structure
- License Policy

# 24. V1.3 MVP

优先：Learning Document Upload、Parsing、Classification、Concept/Principle/Algorithm/Design Guideline、Evidence、Authority、Vector Retrieval、ContextBuilder Integration。

暂不做：复杂 Graph DB、自动 Fine-tuning、大规模 crawler、完整论文搜索、复杂推荐算法。


---

<!-- FILE: 22_HARDWARE_COMMISSIONING_SAFETY_SPEC.md -->

# Embedded Engineering Agent
## Hardware Commissioning & Safety Specification V1.3

# 1. 目的

EEA 可以生成、修改、烧录并调试真实嵌入式硬件，因此“Build 成功”不等于“允许直接运行”。本规范定义从 Firmware Artifact 到真实硬件运行之间的安全执行层，尤其覆盖 FOC、电源、执行器、机器人关节等可能造成高速运动、过流、过压或机械损伤的场景。

核心原则：**Safe-by-default、PWM/Actuator 默认关闭、分阶段使能、硬限制优先于 AI 判断、每一步都有 Evidence 与可回滚状态。**

# 2. HardwareCommissioningSession

至少包含：

- project_id / target_id / firmware_artifact_id / firmware_hash
- hardware_identity / probe_identity / board_revision
- commissioning_profile_id
- state / current_step / started_by / approved_by
- safety_limits_snapshot
- preflight_results / step_results / evidence_ids
- emergency_stop_state / watchdog_state
- resource_lock_ids / permission_token_ids
- created_at / completed_at / aborted_at

状态：

`CREATED → PREFLIGHT → FLASHED_SAFE → SENSOR_CHECK → LOW_POWER → CLOSED_LOOP_LIMITED → USER_APPROVAL → NORMAL_OPERATION`

异常状态：

`BLOCKED / ABORTED / EMERGENCY_STOP / FAULTED / ROLLBACK_REQUIRED`

# 3. Safety Limit

SafetyLimit 必须结构化，至少支持：

- max_bus_voltage
- max_phase_current
- max_iq / max_id
- max_speed
- max_position_delta
- max_duty_cycle
- max_pwm_enable_duration
- max_temperature
- max_test_runtime
- watchdog_timeout
- current_ramp_rate
- speed_ramp_rate
- safe_brake_policy
- safe_output_state

任何 Agent/Plugin 只能请求更保守限制；扩大硬限制需要明确审批。

# 4. Commissioning Pipeline

```text
Build
→ Static Analysis
→ Rule / Safety Pre-check
→ Permission + Resource Lock
→ Target Identity Verification
→ Flash
→ Reset
→ SAFE OUTPUT STATE (PWM/Actuator Disabled)
→ Sensor Sanity Check
→ ADC/Current Offset Calibration
→ Encoder/Direction/Range Check
→ Gate Driver/Fault Input Check
→ Low-power/Open-loop Test
→ Phase/Sign Convention Verification
→ Current-loop Limited Test
→ Velocity/Position Limited Test
→ User Approval
→ Normal Operation
```

不满足任一步，后续步骤禁止自动继续。

# 5. Motor Control 专项 Gate

MotorControl Plugin 至少检查：

- encoder direction / zero / wrap / plausibility
- electrical-angle sign
- phase sequence
- current-sense polarity and channel mapping
- ADC sampling window
- PWM polarity / complementary output / deadtime / break input
- speed feedback sign
- current/speed/position PI saturation
- startup alignment strategy
- current offset
- bus voltage
- gate-driver fault status
- emergency stop / watchdog

第一次闭环运行必须使用 Commissioning Profile，而不是 Production Profile。

# 6. Safe Output State

每个 HardwareTarget 必须声明 SafeState，例如：

- PWM outputs disabled or break asserted
- MOSFET gate-enable low
- motor torque command = 0
- relay/contactor open
- heater/output disabled
- robot brake policy defined
- GPIO outputs set to safe level

系统崩溃、Agent cancel、heartbeat loss、resource-lock loss、tool timeout 时必须进入或尝试进入 SafeState，并记录结果。

# 7. Emergency Stop

EmergencyStop 可由：

- 用户
- Hardware fault input
- Watchdog
- Rule Engine
- Safety monitor
- Tool Adapter
- Agent Runtime policy

触发。触发后：

`stop command → disable actuator/PWM → preserve logs/evidence → release or quarantine resource → mark session EMERGENCY_STOP`

禁止自动恢复到 NORMAL_OPERATION。

# 8. Permission / Lock

FLASH、DEBUG、HARDWARE_CONTROL、ACTUATOR_ENABLE 分离。真正使能执行器必须具备：

- valid permission
- valid target identity
- valid ResourceLock
- safety profile
- preflight PASS
- limits snapshot
- explicit user approval when policy requires

# 9. Evidence

每一步保存：

- measured values
- thresholds
- raw tool result / waveform reference
- firmware hash
- target identity
- rule version
- tool version
- operator/agent
- timestamp

# 10. API

核心资源：

- CommissioningProfile
- HardwareCommissioningSession
- CommissioningStepResult
- SafetyLimit
- EmergencyStopEvent

API 由 Core 提供，Domain Plugin 可贡献 domain-specific preflight/step/rule，但不能绕过 Core safety state machine。

# 11. Acceptance

Hard Fail：

- Flash 后直接自动 PWM enable
- 无 target identity 执行 actuator enable
- 无 safety limit snapshot
- encoder/sign 未验证直接高速度闭环
- current limit 未设置直接运行
- emergency stop 后自动 resume
- crash/cancel 后输出状态未知却标 SUCCESS
- Safety Rule 被 Agent 文本判断覆盖

FOC Benchmark 必须加入真实或 Hardware-in-the-loop commissioning gate。


---

<!-- FILE: 23_TRANSACTIONAL_EVENT_RECOVERY_SPEC.md -->

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


---

<!-- FILE: 24_DOMAIN_COMPOSITION_SPEC.md -->

# Embedded Engineering Agent
## Domain Composition & Multi-Domain Contract Specification V1.3

# 1. 目的

EEA Project 可以激活 0..N Domain Plugin。V1.3 正式定义多个 Domain 同时存在时的依赖、冲突、规则、生成器、UI、Migration 与执行顺序，避免 MotorControl 单插件场景掩盖组合问题。

# 2. DomainActivation

字段至少：

- project_id
- domain_id
- plugin_id / plugin_version
- domain_schema_version
- status: ACTIVE/DISABLED/INCOMPATIBLE/BLOCKED
- configuration
- activated_at / activated_by
- capability_snapshot
- dependency_snapshot

# 3. DomainDescriptor 扩展

至少增加：

- requires_domains
- optional_domains
- conflicts_with
- provided_capabilities
- required_capabilities
- priority
- rule_phases
- generator_phases
- migration_provider
- context_contributions
- ui_contributions

# 4. Composition Resolution

激活前：

```text
Manifest Validation
→ Plugin API Compatibility
→ Required Domain Resolution
→ Capability Resolution
→ Conflict Detection
→ Schema Compatibility
→ Rule/Generator Phase Ordering
→ Migration Check
→ Activation Plan
→ User/Policy Approval
→ Activate
```

存在不可解冲突必须 BLOCKED，禁止“最后加载者覆盖”。

# 5. Capability Routing

Capability 由 Registry 路由，调用者不得写死具体 Domain。若多个 provider 提供同 capability：

- explicit project selection
- deterministic priority
- compatibility policy
- conflict error

禁止依赖 Python import 顺序。

# 6. Rule Ordering

统一 phase：

`PRE_SCHEMA → PRE_DESIGN → PRE_GENERATION → POST_GENERATION → PRE_EXECUTION → POST_EXECUTION → RELEASE_GATE`

Domain Rule 注册 stable rule id/version/phase/inputs/severity/authority。Core safety rule 优先级不可被 Domain 降级。

# 7. Generator Ordering

Generator 声明：

- consumes
- produces
- requires_capabilities
- before/after constraints
- deterministic version
- side effects

Registry 构建 DAG；cycle 必须拒绝激活或生成。

# 8. Cross-domain Dependency

跨 Domain 使用 `DomainIRRef`、Core IR ref、Engineering Dependency Edge，不直接访问另一插件内部表或 Python class。

例：

```text
MotorControlIR
→ requires deterministic cyclic transport
→ EtherCATDomain capability
→ Protocol/MCUConfig/Firmware dependency
```

# 9. Database Namespace

Plugin 表必须 namespace；Domain 数据有 project/domain/version ownership。禁用插件后数据不删除，状态变为 inactive；重新启用需 compatibility/migration。

# 10. UI

Frontend 只基于 `/projects/{id}/domains` 与 `/ui/extensions` 构造页面。

UI contribution 仅声明 metadata/action/form/schema，不注入任意 remote JS。

# 11. API

正式 Core API：

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

# 12. Migration

升级 Core/Plugin 时先计算 Domain Migration Plan。任何 schema/plugin API 不兼容导致 project BLOCKED_UPGRADE，不静默丢数据。

# 13. Benchmark

至少：

- 0 Domain：普通 MCU 项目
- 1 Domain：MotorControl
- 2 Domain：MotorControl + EtherCAT/mock deterministic transport
- 3 Domain：MotorControl + Transport + Robotics/ROS2-facing mock
- conflict case
- missing dependency case
- generator cycle case
- plugin disable/enable migration case


---

<!-- FILE: 25_SOURCE_AUTHORITY_WORKSPACE_GIT_SPEC.md -->

# Embedded Engineering Agent
## Source Authority, Workspace & Git Specification V1.3

# 1. 目的

明确 FirmwareIR、Generated Source、Git Working Tree、Artifact、BuildResult 的权威关系，防止 AI edit、手工 edit、RepairAgent、Generator 形成多套互相覆盖的“源码事实源”。

# 2. Source of Truth

```text
Requirements / IR
      ↓ generation intent
Generated Source Candidate
      ↓ accepted/applied
Git Working Tree  ← 源码实际可编辑 SSOT
      ↓ commit
SourceRevision
      ↓ build
BuildRun / Binary Artifact
```

FirmwareIR 是结构/设计事实源，不是用户源码字节的最终事实源。
Artifact 保存不可变快照/生成物/Build 结果，不替代 Git Working Tree。

# 3. SourceRevision

至少：

- project_id
- repository_id
- commit_sha (nullable for working-tree snapshot)
- tree_hash
- dirty
- base_commit
- workspace_revision
- source_manifest_hash
- created_by / created_at

所有 Build/Test/Review/AgentPatch 绑定 SourceRevision。

# 4. Write Path

任何源码修改：

```text
SafePath
→ Symlink/Workspace boundary check
→ Permission
→ Expected content hash / ETag
→ Git dirty/base check
→ Apply to temp
→ Diff
→ Optional syntax/static validation
→ Atomic replace
→ workspace_revision++
→ Outbox SourceChanged
→ Impact Analysis
```

# 5. AI Edit

AI 不直接写磁盘。AI 生成 PatchProposal：

- base SourceRevision
- affected files
- unified diff/structured edits
- rationale/evidence
- expected impact
- required build/tests

用户或 Repair Workflow apply 后才改变 Working Tree。

# 6. Generator

Generator 对已存在用户代码默认产生 candidate/diff，除非文件标记为 generated-owned。Generated-owned 文件必须有 generator marker/version/input hash，用户改动后进入 diverged 状态，禁止静默覆盖。

# 7. Git

Repair 默认：

`new branch → patch → diff → build/test/review → commit`

Destructive Git 仍需 Permission。Import 项目可选择 external repo mirror/worktree 模式，但所有路径必须受 Workspace Boundary 管理。

# 8. API

文件读取返回 content_hash/SourceRevision/ETag。写入必须提交 expected hash 或 If-Match。

推荐：

```http
GET  /projects/{id}/source/status
GET  /projects/{id}/source/revision
GET  /projects/{id}/source/files/content?path=
POST /projects/{id}/source/patch-proposals
POST /patch-proposals/{id}/apply
GET  /patch-proposals/{id}/diff
POST /projects/{id}/source/commit
```

旧 firmware files write API 映射到 Source Service，不允许绕过安全路径。

# 9. Artifact

Source snapshot、generated output、binary、map、ELF、reports 可成为 Artifact。Artifact 不可变；修改等于创建新版本。

# 10. Acceptance

- concurrent edit → 409
- stale PatchProposal 不可直接 apply
- symlink escape reject
- AI edit 不能绕过 diff
- generator 不能覆盖 diverged user file
- Build 必须绑定精确 SourceRevision
- crash 后 Workspace/DB 可 reconcile


---

<!-- FILE: 26_NON_FUNCTIONAL_RELIABILITY_SPEC.md -->

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


---

<!-- FILE: README.md -->

# Embedded Engineering Agent（EEA）V1.3 Architecture Freeze 文档包

**版本：** 1.3.0  
**状态：** Architecture Freeze / 正式开工基线  
**核心目标：** 保持 Core 通用，通过 Domain Plugin 扩展垂直能力，并形成 Facts + Theory + Practice + Rules + Experience 的统一 Embedded Engineering Intelligence Engine。

## V1.3 核心升级

1. MotorControl 从 Core 真正迁移为 `plugins/builtin/motor_control`。
2. New Design Workflow 改为 `Active Domain IRs (0..N)`，不再无条件经过 MotorControlIR。
3. AIProvider/Structured Generation 前移；Full Agent Runtime 后移。
4. Sandbox Foundation 前移到首次外部 Repo/Archive/Build 之前。
5. Cppcheck + Core Firmware Rules 前移到 FOC Minimal E2E Gate 之前。
6. MCUConfigIR 成为 Timer/PWM/ADC/DMA/IRQ 唯一事实源；MotorControlIR 使用 requirement + refs。
7. Artifact Dependency 升级为 Engineering Dependency & Impact Graph。
8. 新增 Core Neutrality Smoke Benchmark，防止 FOC 反向污染 Core。
9. Plugin 增加 bundled/signed/community trust tier。
10. 新增 ELKB（Embedded Learning Knowledge Base）一级知识能力。
11. 新增 AuthorityLevel、LearningKnowledge、EngineeringEquation、KnowledgeRelation、LearningDocumentCandidate。
12. Technical Knowledge Discovery 复用统一 Discovery/Provider/Budget/Sandbox/Curator。
13. ELKB 明确不是普通 RAG、不是自动 Fine-tuning；私有学习资料默认 Private Scope。

## 文档清单

| 编号 | 文件 | 用途 |
|---|---|---|
| 00 | 00_MASTER_PLAN.md | 项目总体方案 |
| 01 | 01_TECHNICAL_SPEC.md | 技术实现规格 |
| 02 | 02_DOMAIN_MODEL_AND_SCHEMA.md | Domain/Schema 宪法 |
| 03 | 03_DATABASE_AND_STORAGE_DESIGN.md | 数据与存储 |
| 04 | 04_AGENT_WORKFLOW_SPEC.md | Agent 工作流 |
| 05 | 05_KNOWLEDGE_MEMORY_SPEC.md | Knowledge/Memory/ELKB/ERIS/OSDLE |
| 06 | 06_RULE_ENGINE_SPEC.md | 确定性规则引擎 |
| 07 | 07_SECURITY_PERMISSION_SPEC.md | 安全/权限/Sandbox/Plugin Trust |
| 08 | 08_FRONTEND_BACKEND_API_CONTRACT.md | REST/WebSocket/Domain/ELKB API |
| 09 | 09_FRONTEND_UX_SPEC.md | Frontend Engineering IDE |
| 10 | 10_BENCHMARK_TEST_SPEC.md | Benchmark/回归 |
| 11 | 11_CODEX_IMPLEMENTATION_AND_ACCEPTANCE.md | Codex 正式施工顺序 |
| 12 | 12_DEPLOYMENT_DEV_ENV.md | 部署与开发环境 |
| 13 | 13_PLUGIN_SDK_SPEC.md | Plugin/Domain SDK |
| 14 | 14_ENGINEERING_GLOSSARY.md | 术语 |
| 15 | 15_PROJECT_IMPORT_REVERSE_ENGINEERING_SPEC.md | 已有项目导入 |
| 16 | 16_MOTOR_CONTROL_DOMAIN_SPEC.md | Built-in MotorControl Plugin |
| 17 | 17_ARTIFACT_DEPENDENCY_INVALIDATION_SPEC.md | Engineering Dependency & Impact |
| 18 | 18_RESOURCE_BUDGET_LOCK_EXECUTION_SPEC.md | Budget/Lock/Execution |
| 19 | 19_ARCHITECTURE_DECISIONS.md | Architecture Decisions |
| 20 | 20_RELEASE_AND_VERSIONING_SPEC.md | Release/Version |
| 21 | 21_EMBEDDED_LEARNING_KNOWLEDGE_BASE_SPEC.md | ELKB 正式规范 |
| 22 | 22_HARDWARE_COMMISSIONING_SAFETY_SPEC.md | 实机 Commissioning / SafeState / E-Stop |
| 23 | 23_TRANSACTIONAL_EVENT_RECOVERY_SPEC.md | Outbox / Inbox / Crash Recovery |
| 24 | 24_DOMAIN_COMPOSITION_SPEC.md | 0..N Domain 组合契约 |
| 25 | 25_SOURCE_AUTHORITY_WORKSPACE_GIT_SPEC.md | Git/Workspace/Source SSOT |
| 26 | 26_NON_FUNCTIONAL_RELIABILITY_SPEC.md | NFR / Reliability / Failure Injection |

## 编号兼容性说明

ELKB 更新任务原建议文件名为 `15_EMBEDDED_LEARNING_KNOWLEDGE_BASE_SPEC.md`，但现有 V1.1 已占用 15–20。为避免破坏既有引用，本冻结版保留原编号并将 ELKB 编为 21。

## 开发纪律

- Core 不硬编码垂直 Domain。
- Pin/AF/Package/电气限制不得靠 LLM 猜测。
- LLM 做推理/候选/解释；Rule/Compiler/ERC/Static Analysis/Simulation/Hardware Test 做确定性验证。
- 外部代码执行必须经过 Sandbox。
- 关键知识/Claim/Decision 保留 Evidence。
- 私有知识必须 Scope 隔离。
- 上游变化由 Engineering Dependency & Impact Graph 传播。
- FOC 是首个 Reference Benchmark；Core Neutrality 是紧随其后的硬 Gate。


## V1.3 新增冻结项

- Hardware Commissioning & Safety
- Transactional Outbox / Recovery
- Deterministic Domain Composition
- Git/Workspace Source Authority
- NFR / Renderer Security / Canonical Unit / Team Identity


---

<!-- FILE: CHANGELOG_V1.2.md -->

# EEA V1.2 Documentation Changelog

## Architecture Freeze Changes

- MotorControl 从 Core Domain 迁移为 Built-in Domain Plugin。
- Core Workflow 支持 0..N Active Domain IRs。
- AIProvider Foundation 前移，Full Agent Runtime 后移。
- Sandbox Foundation 前移至所有外部执行之前。
- Static Analysis/Firmware Rules 前移至 FOC E2E Gate。
- MCUConfigIR / MotorControlIR 重复事实源被消除。
- Artifact Dependency 升级为 Engineering Dependency & Impact Graph。
- 新增 ClaimPredicateRegistry。
- 新增 Core Neutrality Smoke Benchmark。
- Plugin 增加 Trust Tier / Out-of-Process policy。
- 新增 ELKB 一级知识系统及 LearningKnowledge/EngineeringEquation/Authority/Relations。
- Technical Knowledge Discovery 合并进统一 Discovery Provider 架构。
- API/Frontend/Codex Phase/Release Gate 同步升级。


---

<!-- FILE: CHANGELOG_V1.3.md -->

# EEA V1.3 Documentation Changelog

- Hardware Commissioning & Safety 进入 FOC Release Gate。
- Transactional Outbox/Inbox/Recovery 解决 SQL/EventBus 崩溃窗口。
- Domain Composition 正式定义 0..N Domain 依赖/冲突/执行顺序。
- Git Working Tree 明确为源码字节 SSOT，AI 通过 PatchProposal 修改。
- NFR 增加 failure injection、backup/restore、Renderer Security、Team Identity、Canonical Unit。
- Codex 在 M19 前强制加入 M18A–M18E。


---

<!-- FILE: DOCUMENT_CHANGELOG.md -->

# DOCUMENT_CHANGELOG

## V1.3 变更主题

新增 22–26 五份正式规范：Hardware Commissioning & Safety、Transactional Event/Recovery、Domain Composition、Source Authority/Workspace/Git、NFR/Reliability。

横向同步：00/01/02/03/04/06/07/08/09/10/11/12/13/14/15/16/17/18/19/20/README。

核心冻结：Flash ≠ Actuator Enable；SQL mutation + Outbox 同事务；Domain 组合确定性；Git Working Tree 为源码字节 SSOT；AI edit 先 PatchProposal；Canonical Unit；Renderer 为不可信内容边界。


---

<!-- FILE: CONSISTENCY_CHECK_REPORT.md -->

# CONSISTENCY_CHECK_REPORT

## V1.3 Architecture Audit Matrix

| Check | Result |
|---|---|
| Core neutrality / MotorControl plugin boundary | PASS |
| MCUConfigIR actual config SSOT | PASS |
| 0..N Domain deterministic composition | PASS |
| Git Working Tree source-byte SSOT | PASS |
| PatchProposal + SourceRevision optimistic write | PASS |
| SQL mutation + Transactional Outbox | PASS |
| Idempotent event consumer / crash replay | PASS |
| Qdrant rebuildable derived index | PASS |
| Impact propagation crash recovery | PASS |
| Flash / Actuator Enable separated | PASS |
| SafeState / SafetyLimit / EmergencyStop | PASS |
| FOC Commissioning gate | PASS |
| Hardware cancel/lock-loss safety | PASS |
| Renderer sanitize/CSP/navigation isolation | PASS |
| Private knowledge scope isolation | PASS |
| Team identity schema foundation | PASS |
| Canonical unit/dimension normalization | PASS |
| Backup/Restore + failure injection | PASS |
| Codex M18A–M18E before M19 | PASS |
| Release Gate includes recovery/source/domain/safety/NFR | PASS |
| ELKB remains structured, scoped, evidence-based | PASS |
| Core Neutrality Smoke remains after FOC | PASS |

**结果：22/22 PASS。**

说明：这里的 PASS 表示 V1.3 文档规范已覆盖且未发现已知架构矛盾；代码实现后仍必须由真实测试报告重新证明。


---

<!-- FILE: MODIFIED_FILES.md -->

# MODIFIED_FILES

## V1.3 本轮新增
22_HARDWARE_COMMISSIONING_SAFETY_SPEC.md
23_TRANSACTIONAL_EVENT_RECOVERY_SPEC.md
24_DOMAIN_COMPOSITION_SPEC.md
25_SOURCE_AUTHORITY_WORKSPACE_GIT_SPEC.md
26_NON_FUNCTIONAL_RELIABILITY_SPEC.md
CHANGELOG_V1.3.md

## 本轮重点修改
00,01,02,03,04,06,07,08,09,10,11,12,13,14,15,16,17,18,19,20,README,合订本与审查报告。
