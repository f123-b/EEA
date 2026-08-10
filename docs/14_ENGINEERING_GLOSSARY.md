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
