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
| 27 | 27_M23_KNOWLEDGE_MEMORY_ACCEPTANCE.md | M23/M23R knowledge and memory acceptance |
| M24A | M24A_ENGINEERING_PLANNING_ARCHITECTURE.md | Engineering planning architecture |
| M24A | M24A_PLANNING_TRUST_BOUNDARY.md | Planning trust and no-execution boundary |

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
