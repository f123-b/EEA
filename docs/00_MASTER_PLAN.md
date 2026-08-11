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

M12R/M12A 将固件构建分为 `HOST_SMOKE` 与 `DEVICE`：DEVICE 必须引用 Core-owned `DependencyLock`，通过 ESCR Provider 解析 immutable revision/hash 并从离线缓存 materialize。首个真实目标为固定 STM32CubeG4 release 的 STM32G431 ARM ELF；远程 CI 未绿灯前不得进入 M13。

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
