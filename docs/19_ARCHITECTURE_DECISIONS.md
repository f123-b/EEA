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
