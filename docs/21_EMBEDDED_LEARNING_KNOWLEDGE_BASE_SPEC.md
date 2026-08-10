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
