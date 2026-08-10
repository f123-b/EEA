# EEA 文档更新任务：新增 Embedded Learning Knowledge Base（ELKB）

## 一、任务背景

当前 Embedded Engineering Agent（EEA）已经设计了以下核心知识能力：

- Datasheet Intelligence
- Device Intelligence
- ERIS（Embedded Reference Intelligence System）
- OSDLE（Open Source Discovery & Learning Engine）
- Engineering Rule Engine
- Global / Project / Task Memory
- Project Experience Intelligence

现有设计能够：

- 从 Datasheet / Reference Manual 获取器件事实
- 从优秀开源项目学习工程架构和实现方式
- 从真实项目中积累 Debug / Test / Design Experience
- 通过 Rule Engine 进行确定性工程审查

但是当前知识体系还缺少一个重要部分：

# 系统化嵌入式理论、原理、算法、工程方法和技术学习资料知识库。

例如当前系统知道：

- STM32G431 的 ADC 有什么能力
- VESC 如何组织 Motor Control Firmware
- 某个 Hardware Rule 是否违反

但还应该能够理解：

- ADC 采样为什么要考虑混叠
- PWM 与 ADC 为什么需要同步采样
- FreeRTOS 优先级反转的原理
- CAN 仲裁机制为什么不会破坏数据
- FOC 中 Clarke / Park / SVPWM 的原理
- MOSFET 开关损耗怎么产生
- DMA、Cache、一致性问题为什么出现
- PID/LQR/MPC 分别适合什么控制场景
- OTA A/B Partition 为什么可以提高可靠性
- Watchdog Supervisor 为什么比简单喂狗更加可靠

因此需要正式增加：

# ELKB — Embedded Learning Knowledge Base

中文：

# 嵌入式学习与工程理论知识库

ELKB 必须成为 EEA Knowledge Platform 的一级组成部分，而不是普通文档 RAG 文件夹。

---

# 二、ELKB 的系统定位

重新定义 EEA Knowledge Platform：

```text
Engineering Knowledge Platform
│
├── Datasheet Intelligence
│   ├── Datasheet
│   ├── Reference Manual
│   ├── Errata
│   └── Application Note
│
├── Device Intelligence
│   ├── MCU
│   ├── Peripheral
│   ├── Pin
│   ├── DMA
│   ├── Clock
│   └── Electrical
│
├── ELKB
│   Embedded Learning Knowledge Base
│   │
│   ├── Embedded Fundamentals
│   ├── MCU / CPU Architecture
│   ├── RTOS
│   ├── Embedded Linux
│   ├── Communication
│   ├── Control Theory
│   ├── Motor Control
│   ├── Power Electronics
│   ├── Hardware Design
│   ├── PCB / EMC
│   ├── Robotics
│   ├── ROS2
│   ├── Boot / OTA
│   ├── Testing
│   ├── Debugging
│   ├── Reliability
│   └── Safety
│
├── ERIS
│   ├── Open Source Projects
│   ├── Reference Architecture
│   ├── Engineering Pattern
│   ├── Test Pattern
│   └── Debug Cases
│
├── Engineering Rules
│
├── Project Experience
│
└── Memory & Knowledge Lifecycle
```

这几个知识系统的职责必须明确区分。

---

# 三、不同知识源分别解决什么问题

必须在文档中明确：

## Datasheet Intelligence

回答：

> 芯片 / 器件实际上能够做什么？

例如：

```text
STM32G431 是否支持 TIM1 Complementary PWM？
PA8 是否支持 TIM1_CH1？
ADC 输入范围是多少？
DRV8323 的 Gate Drive Voltage 是多少？
```

属于：

# Hardware / Device Facts

---

## Device Intelligence

回答：

> 如何以机器可读方式表示芯片能力？

例如：

```text
Pin
Peripheral
DMA
Interrupt
Clock
Electrical
Memory
```

属于：

# Structured Device Facts

---

## ELKB

回答：

> 为什么要这样设计？背后的理论和工程原理是什么？

例如：

```text
为什么 PWM 与 ADC 要同步？

为什么 ISR 不应该长时间阻塞？

为什么 FreeRTOS 会发生优先级反转？

为什么 CAN 能进行无损仲裁？

为什么 FOC 要进行 Clarke / Park 变换？

为什么 MOSFET Gate Charge 会影响开关损耗？

为什么高速 PCB 需要考虑 Return Path？
```

属于：

# Theory + Principle + Engineering Knowledge

---

## ERIS

回答：

> 成熟工程通常是怎么实现的？

例如：

```text
VESC 如何实现 Fault Manager？

ODrive 如何组织位置 / 速度 / 电流控制？

Zephyr 如何设计 Driver Model？

MCUboot 如何组织 Boot / Image State？
```

属于：

# Real Engineering Reference

---

## Rule Engine

回答：

> 当前方案是否违反确定性工程规则？

例如：

```text
48V Bus 使用 40V MOSFET？
→ CRITICAL

PA8 同时配置两个互斥功能？
→ PIN_CONFLICT
```

属于：

# Deterministic Validation

---

## Project Experience

回答：

> 我们过去真实项目中发生过什么？

例如：

```text
速度模式反向高速旋转
→ Encoder direction / feedback sign mismatch

齿槽标定异常
→ calibration state / angle direction / current limit issue
```

属于：

# Verified Real-world Experience

---

# 四、ELKB 应包含的主要知识领域

至少建立以下 Domain Taxonomy。

## 4.1 Embedded Fundamentals

```text
C
C++
Memory Model
Pointer
Stack
Heap
Alignment
volatile
atomic
interrupt
DMA
timer
watchdog
startup
linker
memory map
```

---

## 4.2 CPU / MCU Architecture

```text
ARM Cortex-M
Exception
NVIC
SysTick
PendSV
MPU
Cache
FPU
Memory Barrier
Bus Architecture
Clock Tree
Reset
Boot
```

---

## 4.3 MCU Peripheral

```text
GPIO
ADC
DAC
Timer
PWM
DMA
UART
SPI
I2C
CAN
USB
Ethernet
RTC
Comparator
OPAMP
Encoder Interface
```

---

## 4.4 RTOS

```text
Task
Scheduler
Context Switch
Priority
Queue
Semaphore
Mutex
Event
Stream Buffer
Notification
Critical Section
ISR-Task Communication
Race Condition
Deadlock
Livelock
Priority Inversion
Priority Inheritance
Real-time Scheduling
WCET
```

---

## 4.5 Embedded Linux

```text
Process
Thread
IPC
Socket
Shared Memory
Pipe
Message Queue
Signal
Kernel
Driver
Device Tree
sysfs
procfs
GPIO
SPI
I2C
SocketCAN
Network
Systemd
BSP
Bootloader
OTA
```

---

## 4.6 Communication

```text
UART
RS232
RS485
SPI
I2C
CAN
CAN FD
CANopen
Modbus RTU
Modbus TCP
USB
Ethernet
TCP
UDP
HTTP
MQTT
BLE
Wi-Fi
EtherCAT
```

---

## 4.7 Control Theory

```text
PID
Feedforward
Cascade Control
State Space
LQR
MPC
Observer
Kalman Filter
PLL
Low-pass Filter
IIR
FIR
Trajectory
Control Stability
Bandwidth
Phase Margin
```

---

## 4.8 Motor Control

```text
DC Motor
BLDC
PMSM
FOC
Clarke
Park
Inverse Park
SVPWM
Current Loop
Velocity Loop
Position Loop
Encoder
Hall
Sensorless
Observer
Field Weakening
MTPA
Cogging Compensation
Friction Compensation
Current Sampling
Deadtime Compensation
Calibration
```

---

## 4.9 Power Electronics

```text
MOSFET
IGBT
Gate Driver
Buck
Boost
LDO
DC/DC
Current Sense
Shunt
Operational Amplifier
Protection
Overcurrent
Overvoltage
Undervoltage
TVS
Fuse
Reverse Polarity
Thermal
Switching Loss
Conduction Loss
```

---

## 4.10 Hardware Design

```text
Power Tree
Decoupling
Ground
ADC Front End
Current Sense
Clock
Reset
Boot
ESD
EMI
EMC
Signal Integrity
Level Shifting
Isolation
CAN Physical Layer
RS485 Physical Layer
USB Physical Layer
```

---

## 4.11 PCB

```text
Stackup
Ground Plane
Return Path
Differential Pair
Impedance
High Current Routing
Gate Loop
ADC Layout
Kelvin Sense
Thermal Via
EMI
Crosstalk
Decoupling Placement
```

---

## 4.12 Bootloader / OTA

```text
Bootloader
Firmware Image
CRC
Signature
Secure Boot
A/B Partition
Rollback
Boot Flag
Version
Recovery
Interrupted Upgrade
OTA State Machine
```

---

## 4.13 Robotics

```text
Robot Joint
Servo
IMU
Encoder
Kinematics
Dynamics
Trajectory
State Estimation
Motor Driver
CAN FD
EtherCAT
ROS2
micro-ROS
Realtime Control
```

---

## 4.14 Testing

```text
Unit Test
Integration Test
System Test
Boundary Test
Stress Test
Fault Injection
Regression
Simulation
SIL
HIL
Hardware Test
Production Test
```

---

## 4.15 Debugging

```text
HardFault
Stack Overflow
Memory Corruption
Race
Deadlock
DMA Error
Cache Coherency
CAN Bus-Off
I2C Lock
SPI Error
ADC Noise
Ground Noise
EMI
FOC Oscillation
Motor Jitter
Encoder Error
Startup Failure
Boot Failure
OTA Failure
```

---

## 4.16 Reliability / Safety

```text
Watchdog
Fault Manager
Fail-safe
Timeout
Redundancy
Brownout
Fault Recovery
Safe State
Power-on Self Test
Runtime Diagnostic
Functional Safety Concepts
```

---

# 五、ELKB 不允许只是普通 RAG

必须明确：

```text
PDF
↓
Chunk
↓
Embedding
```

只能作为 Retrieval 基础层。

不能作为 ELKB 最终形式。

完整流程应该是：

```text
Learning Document
      ↓
Document Parser
      ↓
Document IR
      ↓
Semantic Chunk
      ↓
Knowledge Extraction
      ↓
Knowledge Normalization
      ↓
Concept / Principle / Algorithm / Guideline
      ↓
Evidence
      ↓
Trust Evaluation
      ↓
ELKB
```

---

# 六、新增 KnowledgeType

现有 KnowledgeType 扩展为：

```text
DEVICE
DATASHEET_FACT

CONCEPT
PRINCIPLE
ALGORITHM
FORMULA

DESIGN_GUIDELINE
BEST_PRACTICE

REFERENCE_PROJECT
REFERENCE_ARCHITECTURE
MODULE

PATTERN
ANTI_PATTERN

DEBUG_CASE
TEST_PATTERN

RULE

PROJECT_EXPERIENCE
```

其中：

## CONCEPT

描述：

```text
什么是 DMA？
什么是 Priority Inversion？
```

---

## PRINCIPLE

描述：

```text
为什么 CAN Arbitration 是 nondestructive arbitration？
为什么 Decoupling Capacitor 要靠近 IC？
```

---

## ALGORITHM

描述：

```text
FOC
PID
LQR
Kalman Filter
SVPWM
```

应包括：

```text
Inputs
Outputs
Assumptions
Steps
Complexity
Applicable Conditions
Limitations
```

---

## FORMULA

结构化公式知识。

例如：

```text
MOSFET conduction loss

P ≈ I² × RDS(on)
```

需要记录：

```text
variables
units
assumptions
applicability
source
```

不得只有公式字符串。

---

## DESIGN_GUIDELINE

例如：

```text
ADC RC Filter Design
CAN Termination Design
FreeRTOS Task Priority Design
```

---

## BEST_PRACTICE

例如：

```text
ISR 尽量短
Application 不直接依赖 HAL
Protocol 使用单一事实源
```

---

# 七、新增 LearningKnowledge Model

建议增加：

```python
class LearningKnowledge(KnowledgeEntry):

    topic: str

    knowledge_type: LearningKnowledgeType

    domain: list[str]

    definition: str | None

    explanation: str | None

    principles: list[str]

    prerequisites: list[str]

    applicable_conditions: list[str]

    limitations: list[str]

    examples: list[KnowledgeExample]

    equations: list[EngineeringEquation]

    related_concepts: list[UUID]

    related_patterns: list[UUID]

    related_rules: list[str]

    related_debug_cases: list[UUID]

    evidence_ids: list[UUID]

    authority_level: AuthorityLevel

    trust_score: float
```

---

# 八、新增 EngineeringEquation

建议：

```python
class EngineeringEquation(BaseModel):

    id: UUID

    name: str

    expression: str

    variables: list[EquationVariable]

    units: dict[str, str]

    assumptions: list[str]

    applicability: list[str]

    limitations: list[str]

    evidence_ids: list[UUID]
```

这样 AI 可以真正使用工程公式，而不是靠语言模型记忆公式。

---

# 九、新增 Authority Level

除了 Trust Score，再增加来源权威等级。

建议：

```text
T0_STANDARD_OFFICIAL
T1_OFFICIAL_TECHNICAL
T2_TRUSTED_ACADEMIC
T3_MATURE_ENGINEERING_REFERENCE
T4_HIGH_QUALITY_COMMUNITY
T5_UNVERIFIED_COMMUNITY
T6_AI_INFERENCE
```

解释：

## T0

标准组织 / 芯片厂商正式规范。

## T1

官方 Application Note、Training、技术指南。

## T2

可信教材、论文、大学课程资料。

## T3

成熟开源项目及长期工程实践。

## T4

高质量技术文章。

## T5

普通论坛 / Blog / Discussion。

## T6

模型自行推理。

---

# 十、检索排序必须升级

不能只使用 Vector Similarity。

建议：

```text
RetrievalScore =
    SemanticRelevance
  + AuthorityScore
  + TrustScore
  + VerificationScore
  + FreshnessScore
  + ProjectRelevance
  + DomainApplicability
```

同样语义相关时：

```text
Official Datasheet
```

必须优先于：

```text
Random Blog
```

---

# 十一、知识源分类

ELKB 来源至少支持：

## Official

```text
Manufacturer Training
Application Note
Programming Guide
Architecture Guide
Official Example Documentation
Official Blog
```

## Standard

```text
Protocol Standard
Architecture Specification
Official Consortium Documentation
```

## Academic

```text
Open-access Textbook
Course Material
Research Paper
Thesis
```

## Engineering

```text
Technical Documentation
Engineering Guide
High-quality Technical Article
```

## User Provided

```text
用户上传学习资料
个人技术笔记
公司内部培训
```

Private source 必须保持 Private Scope。

---

# 十二、版权与 License

ELKB 不能无差别抓取互联网上受版权保护的教材全文。

必须建立：

```text
SourceLicense
UsagePolicy
StoragePolicy
QuotationPolicy
RetrievalPolicy
```

对于无法长期存储全文的来源：

可以保存：

```text
Metadata
Structured Summary
Knowledge Extraction
Evidence Link
Short Citation
```

而不是复制整本书。

---

# 十三、新增 Technical Knowledge Discovery

建议在 OSDLE 旁增加：

# TKDE — Technical Knowledge Discovery Engine

负责发现：

```text
Official Application Note
Official Training
Official Development Guide
Open-access Course
Open-access Paper
Engineering Article
Protocol Documentation
```

整体：

```text
Internet / Vendor / Academic Sources
        ↓
TechnicalKnowledgeDiscoveryAgent
        ↓
Candidate Document Pool
        ↓
Authority Check
        ↓
Copyright / License
        ↓
Quality Evaluation
        ↓
Parser
        ↓
Knowledge Extraction
        ↓
ELKB Staging
        ↓
Knowledge Curator
        ↓
Global Engineering Memory
```

也可以将 TKDE 作为 OSDLE 的 `document discovery` 子系统，而不是独立产品模块。

实现时优先保持统一 Provider 架构。

---

# 十四、新增 Learning Document Candidate

建议 Schema：

```python
class LearningDocumentCandidate(BaseModel):

    id: UUID

    source_url: str

    source_type: str

    title: str

    publisher: str | None

    author: str | None

    published_at: datetime | None

    updated_at: datetime | None

    domains: list[str]

    authority_level: AuthorityLevel

    quality_score: float

    license_info: LicenseInfo | None

    storage_allowed: bool

    extraction_allowed: bool

    lifecycle: CandidateStatus
```

---

# 十五、新增 ELKB Agent

至少增加：

## LearningKnowledgeAgent

职责：

```text
阅读技术资料
→ 提取 Concept
→ Principle
→ Algorithm
→ Formula
→ Design Guideline
```

---

## KnowledgeNormalizationAgent

职责：

把不同资料对同一概念的表述统一。

例如：

```text
priority inversion
priority reversal
优先级反转
```

归到统一 Concept ID。

---

## LearningKnowledgeCuratorAgent

职责：

```text
Authority Check
Evidence Check
Duplicate Check
Conflict Check
Applicability Check
Copyright/License Check
Promotion
Deprecation
```

可以考虑复用现有 KnowledgeCuratorAgent，而不是创建重复框架。

---

# 十六、Agent 使用 ELKB 的方式

## System Architect

查询：

```text
architecture principle
design guideline
reference architecture
```

---

## Hardware Agent

查询：

```text
electrical principle
power design guideline
PCB principle
device fact
reference circuit
```

---

## Firmware Agent

查询：

```text
software architecture
RTOS concepts
driver patterns
concurrency principles
reference implementation
```

---

## Motor Control Agent

查询：

```text
FOC theory
current sampling
control bandwidth
SVPWM
encoder
motor reference projects
debug cases
```

---

## Review Agent

查询：

```text
best practice
anti-pattern
design guideline
rule
```

---

## Debug Agent

查询：

```text
underlying principle
known failure mode
debug case
device fact
project history
```

---

# 十七、典型多源知识融合

例如任务：

> 设计 STM32G431 PMSM FOC 电流采样。

ContextBuilder 应分别获取：

```text
DEVICE FACT
STM32G431 ADC / OPAMP / Timer

DATASHEET
ADC timing / electrical characteristics

ELKB PRINCIPLE
PWM synchronous sampling

ELKB ALGORITHM
FOC current reconstruction

ELKB DESIGN GUIDELINE
ADC front-end / anti-aliasing

ERIS
VESC / ODrive current sensing architecture

DEBUG CASE
ADC offset
switching noise
wrong sampling point

RULE
ADC range
PWM trigger
timing constraint
```

再交给 Hardware/Firmware Agent 综合设计。

---

# 十八、Debug 示例

用户现象：

```text
低速电机抖动
```

系统检索：

```text
ELKB:
FOC low-speed control principles
encoder quantization
friction
cogging
current loop bandwidth

ERIS:
VESC / ODrive / SimpleFOC implementations

Debug DB:
low-speed jitter cases

Project Memory:
current project logs / previous fixes

Device:
encoder / ADC characteristics
```

这样 Debug Agent 不只是“搜相似 Bug”，还能够理解问题背后的理论原因。

---

# 十九、Knowledge Graph 关系扩展

KnowledgeEntry 之间增加：

```text
PREREQUISITE_OF

EXPLAINS

IMPLEMENTED_BY

VALIDATED_BY

CONTRADICTS

APPLIES_TO

RELATED_TO

DERIVED_FROM

USED_BY_RULE

HAS_DEBUG_CASE
```

例如：

```text
FOC
  ├─ requires → Clarke Transform
  ├─ requires → Park Transform
  ├─ implemented_by → VESC
  ├─ debug_case → Electrical Angle Error
  └─ applies_to → PMSM / BLDC
```

未来 Knowledge Graph 可以基于这些关系构建。

---

# 二十、数据库设计更新

需要在数据库设计中增加或扩展：

```text
learning_documents

learning_document_candidates

learning_knowledge

engineering_equations

knowledge_relations

authority_levels

knowledge_source_licenses
```

可以根据现有统一 `knowledge_entries` 架构进行 subtype 实现，避免无必要地创建过多重复表。

核心要求：

ELKB 必须在数据模型上是正式知识对象，而不是简单 `document_chunks`。

---

# 二十一、Vector Database 更新

Qdrant metadata 增加：

```text
knowledge_type

domain

authority_level

trust_level

verification_level

source_type

source_id

publisher

license

scope

lifecycle

freshness
```

检索必须支持 Filter。

---

# 二十二、Memory 生命周期

ELKB 同样遵守现有 Memory Lifecycle。

```text
DISCOVERED
↓
CANDIDATE
↓
ACTIVE
↓
TRUSTED
```

后续可能：

```text
STALE
CONFLICTED
DEPRECATED
ARCHIVED
```

新找到的文章不能直接进入 Trusted。

---

# 二十三、用户自己的学习资料

必须支持：

```text
上传学习资料
```

例如：

```text
FreeRTOS学习笔记.pdf

电机控制讲义.pdf

STM32课程资料.pdf

Linux驱动笔记.md
```

系统：

```text
Parse
↓
Classify
↓
Extract Knowledge
↓
Project/User Private ELKB
```

默认：

```text
USER_PRIVATE
```

或：

```text
PROJECT_PRIVATE
```

不能进入：

```text
GLOBAL_PUBLIC
```

除非有明确 Promotion。

---

# 二十四、前端增加 Learning Knowledge 页面

Knowledge Center 中增加：

```text
Knowledge Center
│
├── Overview
├── Device Knowledge
├── Datasheet
├── Learning Knowledge
├── Reference Projects
├── Architectures
├── Patterns
├── Debug Cases
├── Knowledge Gaps
└── Candidates
```

Learning Knowledge 页面支持：

```text
Domain Tree

Search

Concept

Principle

Algorithm

Formula

Design Guideline

Source

Authority

Trust

Related Knowledge
```

---

# 二十五、学习资料不是面向用户的“课程系统”

当前阶段不要把 EEA 做成类似在线学习网站。

ELKB 的首要目标是：

# 提升 Engineering Agent 的设计、解释、审查和 Debug 能力。

用户可以查看这些知识，但主要消费者仍是 Agent。

未来如需要，可以增加：

```text
Explain to User
Learning Mode
Interview Mode
Concept Visualization
```

但不能让这部分干扰核心工程平台。

---

# 二十六、Benchmark 更新

Benchmark 必须增加 ELKB 测试。

至少加入：

## Knowledge Retrieval Test

问题：

```text
为什么 FOC 电流采样通常需要和 PWM 同步？
```

检查：

```text
是否找到 PRINCIPLE
是否有高权威来源
是否有 Evidence
```

---

## Cross-source Fusion Test

任务：

```text
设计 PMSM current sensing
```

检查结果是否同时利用：

```text
Device
Datasheet
ELKB
ERIS
Rules
```

而不是单一知识源。

---

## Authority Ranking Test

同一问题同时存在：

```text
Official Application Note
Random Blog
```

要求：

Official source 排名更高。

---

## Conflict Test

两个 Learning Source 对某工程实践意见不同。

系统必须：

```text
记录适用条件
而不是任意选一个
```

---

## Private ELKB Isolation Test

Project A 上传私有学习资料。

Project B 不得检索到。

---

# 二十七、最终知识平台定义

更新后 EEA Knowledge Platform 应正式定义为：

```text
Embedded Engineering Intelligence
│
├── Device Facts
├── Datasheet Facts
├── Theory & Principles
├── Algorithms
├── Design Guidelines
├── Engineering Patterns
├── Reference Architectures
├── Open-source Engineering Experience
├── Debug Cases
├── Test Patterns
├── Engineering Rules
└── Verified Project Experience
```

---

# 二十八、必须修改的现有文档

请不要只新增一个 ELKB 文档。

必须同步检查并修改以下文件：

```text
00_MASTER_PLAN.md

01_TECHNICAL_SPEC.md

02_DOMAIN_MODEL_AND_SCHEMA.md

03_DATABASE_AND_STORAGE_DESIGN.md

04_AGENT_WORKFLOW_SPEC.md

05_KNOWLEDGE_MEMORY_SPEC.md

08_FRONTEND_BACKEND_API_CONTRACT.md

09_FRONTEND_UX_SPEC.md

10_BENCHMARK_TEST_SPEC.md

11_CODEX_IMPLEMENTATION_AND_ACCEPTANCE.md

13_PLUGIN_SDK_SPEC.md

14_ENGINEERING_GLOSSARY.md
```

并新增：

```text
15_EMBEDDED_LEARNING_KNOWLEDGE_BASE_SPEC.md
```

---

# 二十九、MASTER_PLAN 修改要求

在总体知识体系中增加 ELKB。

更新：

```text
Datasheet Intelligence
Device Intelligence
ERIS
OSDLE
```

为：

```text
Datasheet Intelligence
Device Intelligence
ELKB
ERIS
OSDLE / Technical Knowledge Discovery
```

明确：

```text
Datasheet = Facts

ELKB = Theory / Principle / Algorithm

ERIS = Real Engineering Practice

Rules = Deterministic Judgment

Project Memory = Verified Local Experience
```

---

# 三十、TECHNICAL_SPEC 修改要求

增加：

```text
LearningKnowledgeService

LearningDocumentService

KnowledgeNormalizationService

TechnicalKnowledgeDiscoveryService
```

必要 Ports：

```python
class LearningKnowledgeProvider(Protocol):
    ...

class TechnicalKnowledgeSourceProvider(Protocol):
    ...
```

如果可以复用已有 Document/Knowledge Provider，则优先复用，不要为了 ELKB 制造重复基础设施。

---

# 三十一、DOMAIN_MODEL 修改要求

加入：

```text
LearningKnowledge

EngineeringEquation

AuthorityLevel

LearningDocumentCandidate

KnowledgeRelation
```

并扩充：

```text
KnowledgeType
```

---

# 三十二、DATABASE 修改要求

加入 ELKB 数据存储、Source License、Authority、Knowledge Relation。

同时说明：

```text
Document raw storage
≠
Knowledge storage
```

Document 是 Source。

KnowledgeEntry 是提取后的 Engineering Knowledge。

---

# 三十三、AGENT_WORKFLOW 修改要求

ContextBuilder 增加：

```text
Learning Knowledge Retrieval
```

顺序建议：

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

但具体排序应根据任务类型动态调整。

---

# 三十四、KNOWLEDGE_MEMORY 修改要求

正式加入：

```text
ELKB
Technical Knowledge Discovery
Authority Level
Theory Knowledge
Algorithm Knowledge
Formula Knowledge
Learning Source License
```

并纳入 Promotion/Lifecycle。

---

# 三十五、API 修改要求

增加：

```http
GET /api/v1/learning/knowledge

GET /api/v1/learning/knowledge/{knowledge_id}

GET /api/v1/learning/domains

GET /api/v1/learning/concepts

GET /api/v1/learning/algorithms

GET /api/v1/learning/guidelines

GET /api/v1/learning/formulas
```

资料：

```http
POST /api/v1/projects/{project_id}/learning/documents

GET /api/v1/projects/{project_id}/learning/documents

POST /api/v1/learning/documents/{document_id}/extract
```

Discovery：

```http
POST /api/v1/learning/discovery

GET /api/v1/learning/candidates

GET /api/v1/learning/candidates/{id}

POST /api/v1/learning/candidates/{id}/analyze

POST /api/v1/learning/candidates/{id}/approve

POST /api/v1/learning/candidates/{id}/reject
```

Knowledge Relation：

```http
GET /api/v1/learning/knowledge/{id}/relations
```

---

# 三十六、Frontend UX 修改要求

Knowledge Center 增加：

# Learning Knowledge

页面最少包含：

```text
Domain Navigation

Concept Search

Knowledge Type Filter

Authority Filter

Trust Filter

Source

Related Concepts

Related Algorithms

Related Rules

Related Debug Cases
```

Knowledge Detail 显示：

```text
Definition

Explanation

Applicable Conditions

Limitations

Formula

Examples

Source

Authority

Trust

Verification

Relations
```

---

# 三十七、Codex 开发 Phase 修改建议

不要把 ELKB 留到项目最后才做。

建议在：

```text
Document System
Retrieval
Device Intelligence
ERIS
```

附近加入 ELKB。

推荐新增开发阶段：

```text
PHASE ELKB-1
Learning Knowledge Domain

PHASE ELKB-2
Learning Document Extraction

PHASE ELKB-3
Authority / Trust / License

PHASE ELKB-4
Context Builder Integration

PHASE ELKB-5
Technical Knowledge Discovery
```

实际编号请根据现有 Phase 顺序重新整理，避免重复编号。

---

# 三十八、ELKB 第一阶段不要做得过重

MVP 应优先完成：

```text
Learning Document Upload

Document Parsing

Knowledge Classification

Concept

Principle

Algorithm

Design Guideline

Evidence

Authority Level

Vector Retrieval

Context Builder Integration
```

暂时不需要：

```text
复杂 Knowledge Graph DB

自动 Fine-tuning

大规模互联网爬虫

完整论文搜索系统

复杂推荐算法
```

---

# 三十九、ELKB 第一批建议知识领域

不要第一版直接覆盖全部嵌入式。

第一阶段重点：

```text
MCU Fundamentals

ARM Cortex-M

STM32

FreeRTOS

Communication

Motor Control

Power Electronics

Embedded Firmware Architecture

Debugging

Testing
```

原因：

这些领域与初始 FOC Benchmark 及核心嵌入式研发流程关系最强。

第二阶段：

```text
Embedded Linux

EtherCAT

ROS2

Robotics

USB

Ethernet

OTA
```

---

# 四十、最终要求

文档更新完成以后，整个 EEA 必须具备统一知识逻辑：

```text
用户需求
   ↓
Context Builder
   │
   ├── Project Facts
   ├── Datasheet
   ├── Device DB
   ├── ELKB
   ├── ERIS
   ├── Engineering Rules
   └── Project Experience
   ↓
Engineering Agent
   ↓
Design / Review / Debug
```

最终形成：

# Facts + Theory + Practice + Rules + Experience

其中：

```text
Facts
=
Datasheet + Device

Theory
=
ELKB

Practice
=
ERIS

Rules
=
Engineering Rule Engine

Experience
=
Project Memory / Verified Debug Cases
```

这五类知识共同构成 EEA 的：

# Embedded Engineering Intelligence Engine

---

# 四十一、执行要求

执行本次文档修改时：

1. 先完整阅读现有 `/docs`。
2. 不删除现有成熟架构。
3. 不创建与现有 ERIS / Memory / Document 基础设施重复的系统。
4. ELKB 要通过现有 KnowledgeEntry、Evidence、Lifecycle、Scope、Trust 体系融合。
5. 对所有受影响文档进行一致性检查。
6. API、Schema、Database、Agent、Frontend、Codex Phase 必须同步。
7. 更新 `README.md` 文档目录。
8. 新增 `15_EMBEDDED_LEARNING_KNOWLEDGE_BASE_SPEC.md`。
9. 更新 `EEA_COMPLETE_DOCUMENTATION.md`（如果仓库维护合订本）。
10. 更新文档版本/CHANGELOG。
11. 检查所有术语统一使用 ELKB / Embedded Learning Knowledge Base。
12. 不要把 ELKB 描述成简单 RAG。
13. 不要把“主动学习”实现为自动 Fine-tuning。
14. 不允许未验证学习文档直接成为 GLOBAL_TRUSTED。
15. 用户私有学习资料默认保持 USER_PRIVATE / PROJECT_PRIVATE。

完成以后输出：

```text
MODIFIED_FILES.md
DOCUMENT_CHANGELOG.md
CONSISTENCY_CHECK_REPORT.md
```

其中 `CONSISTENCY_CHECK_REPORT.md` 必须检查：

```text
Master Plan
↔ Technical Spec

Schema
↔ Database

Agent Workflow
↔ Knowledge System

API
↔ Frontend UX

Codex Phase
↔ Technical Dependencies

ELKB
↔ ERIS
↔ Memory
↔ OSDLE
```

确认没有相互矛盾后，本次更新才算完成。