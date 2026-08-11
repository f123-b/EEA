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

Firmware layers/modules、BSP/Platform、FirmwareIR、SourceRevision、BuildInputSnapshot、BuildRun 与 ESCR。M12R 要求 BuildRun 时间戳单调、构建时长聚合、CMake DSL 注入阻断、PlatformIO native fallback 禁用，并区分 `HOST_SMOKE` 与 `DEVICE`。M12A 要求 Core-neutral component catalog、immutable revision/hash、license/compatibility/reference-only policy、确定性 DependencyLock、离线缓存 materialization，以及官方 STM32CubeG4 固定提交的真实 STM32G431 CMake/ARM ELF 构建。

验收：M12/M12A 本地测试与真实 DEVICE build 通过；远程 CI 必须绿色且人工复核后才可标记 ACCEPTED。远程未绿灯时停止在 M12，禁止进入 M13。

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
