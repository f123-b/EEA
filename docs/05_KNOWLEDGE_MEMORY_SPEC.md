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
