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

Project、Artifact、ArtifactDependency、Evidence、Claim、ClaimResolver、Issue、Decision、Traceability、Job、Permission、ResourceLock、Budget、Requirement、Document、Device、PinPlanner、Architecture、HardwareDesign、CircuitDesign、MCUConfig、FirmwareDesign、DomainExtension、DomainComposition、DomainCapability、Protocol、Test、Review、Debug、Repair、Memory、Knowledge、Discovery、RepositoryIntelligence、ProjectImport、Plugin、ToolRegistry。

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

Requirement、EngineeringClaim、HardwareIR、CircuitIR、MCUConfigIR、FirmwareIR、DomainDescriptor、DomainActivation、DomainIREnvelope、ProtocolIR、TestIR、KnowledgeEntry、PluginManifest 均带 schema_version。Breaking change 使用新 major + migration。

具体 Domain IR 的 schema_version 由对应 Domain Plugin 管理；Core 只验证 Plugin API compatibility、DomainDescriptor 和 DomainIREnvelope。

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
