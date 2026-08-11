# EEA 当前修正任务 + 架构完善 + 正式后续升级路线
## Codex 直接执行版

> Repository: `f123-b/EEA`  
> 当前审核基线：`main` / `4b5346f695e89db81982def2ba56d1d07515c97b`  
> 文档目的：直接交给 Codex 执行。  
> 核心原则：**修当前真实问题，不为优化停工；正式后续升级只做架构预留，不阻塞当前 Milestone。**

---

# 0. Codex 必读

本轮工作必须严格区分三类内容：

```text
A. 当前必须修复的问题
   → 真正 Blocker
   → 修完后才允许正式进入 M15

B. 当前架构完善 / 技术债务
   → NON-BLOCKING
   → 可以顺手修，也可以按原 Milestone 延后
   → 不得阻塞 M15/M16/... 后续进度

C. 正式 Future Upgrade Roadmap
   → 用户已经确认的 4 个后续升级方向
   → 当前只允许做兼容性预留
   → 禁止提前大规模实现
   → 绝不作为当前 Milestone Gate
```

不要把 B 类和 C 类混为“后续升级”。

---

# 1. 本轮总目标

当前先增加一个短修正阶段：

```text
M14R = Repository Acceptance Hardening
```

目标：

```text
修 CI
→ 修 M14 当前真实语义问题
→ 修验收/版本一致性
→ 建立可复现的 Acceptance
→ 正式进入 M15
```

本轮不是：

```text
重新设计 EEA
重构全部 Repository
提前实现 M18/M23/M27/M30
提前做完整知识库
提前做 EdgeAI
提前做大型项目引擎
```

---

# 2. 严格禁止事项

Codex 不得：

1. 推翻当前 V1.3 Architecture Freeze。
2. 重新设计 Core / Domain / Plugin 总体架构。
3. 更改既定 M0–M36 主里程碑编号。
4. 把 MotorControl / FOC 放回 Core。
5. 创建第二套 Domain Framework。
6. 为“代码更漂亮”进行大规模目录重构。
7. 为修 CI 关闭 mypy / coverage / migration / OpenAPI gate。
8. 用大量 `# type: ignore` 掩盖平台问题。
9. 将 skipped / pending / unavailable 写成 PASS。
10. 自行标记 `HUMAN_ACCEPTED`。
11. 为非阻断优化停止当前主线开发。
12. 提前实现完整 M18A Outbox/Recovery。
13. 提前实现完整 M18C Source Authority。
14. 提前实现完整 ELKB。
15. 提前实现 4 项 Future Upgrade。
16. 为新增前端页面伪造后端能力或假数据。

---

# 3. A 类：当前必须修改的内容

以下为真正的 Blocker。

只有 A 类全部完成，才允许：

```text
READY_FOR_M15 = YES
```

---

# 4. A-01 修复 Ubuntu CI / mypy 的 Windows ctypes 错误

## 当前问题

GitHub Actions 当前：

```text
desktop = PASS
backend = FAIL
```

backend 在 mypy 失败。

问题文件：

```text
adapters/src/eea_adapters/sandbox.py
```

涉及：

```python
ctypes.WinDLL
ctypes.get_last_error
```

Linux 类型环境下 mypy 认为这些 Windows-only 属性不存在。

因此后续：

```text
DB upgrade
alembic check
pytest
OpenAPI export check
TypeScript contract check
```

全部没有真实执行。

## 修改要求

采用最小平台边界修复。

优先方案：

```text
adapters/src/eea_adapters/
├── sandbox.py
└── windows_job.py
```

或同等级清晰的平台隔离方案。

要求：

- Windows Job Object 实现保持有效；
- Linux 下不导入/静态解析 Windows-only API；
- Windows-specific 代码与 cross-platform sandbox 分离；
- sandbox 无法证明安全能力时继续 fail closed；
- 不关闭 mypy；
- 不大面积 ignore；
- 不删除 Windows sandbox 能力。

## 测试

至少：

```bash
ruff check .
ruff format --check .
mypy
pytest tests/test_m5_sandbox.py -q
```

---

# 5. A-02 恢复完整 CI Gate

A-01 修完后必须跑完整 Gate。

至少包括：

```bash
ruff check .
ruff format --check .
mypy
python -m eea_cli db upgrade
alembic check
pytest
eea openapi export --check
eea openapi typescript --check
pnpm lint
pnpm typecheck
pnpm build
```

最终要求：

```text
backend = GREEN
desktop = GREEN
```

如果后续步骤暴露新问题：

```text
修真实问题
```

禁止：

```text
删除测试
关闭 Gate
降低 coverage
skip 失败步骤
写成 known issue 后跳过
```

---

# 6. A-03 修正 M14 验收 SHA 和报告可复现性

## 当前问题

现有：

```text
reports/M14/TEST_REPORT.md
```

记录审核 HEAD：

```text
cccdd74ee4a86818c0c2e948997460fea9ad638e
```

而 M14 代码实际进入：

```text
4b5346f695e89db81982def2ba56d1d07515c97b
```

所以当前 M14 验收报告不能从其记录 SHA 直接复现。

## 修改要求

所有 A 类修改完成后：

```text
clean checkout exact SHA
→ migrations
→ focused tests
→ full tests
→ OpenAPI contracts
→ frontend build
→ remote CI
```

然后更新：

```text
reports/M14/TEST_REPORT.md
reports/M14/KNOWN_ISSUES.md
reports/M14/NEXT_PHASE.md
```

报告至少写：

```text
Exact Commit SHA
Date
Python version
Node version
Migration head
Focused test commands
Focused test result
Full regression command
Full regression result
OpenAPI result
Frontend result
GitHub Actions Run ID
Remote CI result
Human acceptance state
Final state
```

## 状态规则

建议：

```text
IMPLEMENTED
LOCAL_VERIFIED
REMOTE_VERIFIED
HUMAN_ACCEPTANCE_PENDING
HUMAN_ACCEPTED
ACCEPTED
BLOCKED
```

且：

```text
ACCEPTED
=
LOCAL_VERIFIED
+ REMOTE_VERIFIED
+ HUMAN_ACCEPTED
```

没有人工确认时不能写 `ACCEPTED`。

---

# 7. A-04 修正 Version / Milestone 漂移

当前代码已经到 M14，但多个位置仍显示 M6/dev6。

至少检查：

```text
README.md
pyproject.toml
apps/desktop/package.json
apps/backend/src/eea_backend/main.py
apps/backend/src/eea_backend/version.py
CHANGELOG.md
PACKAGE_INFO.txt
```

如果文件不存在则忽略，不得创建无意义重复文件。

## 修改目标

同步：

```text
Current implementation milestone
Backend version
Python package version
Desktop version
API meta version
Changelog
```

使用现有版本策略生成：

```text
M14 / M14R 对应 development version
```

不要随意升级 major/minor。

## 轻量防回归

允许增加一个简单测试检查：

```text
README milestone
backend milestone
package version
desktop version
```

基础一致性。

不要现在构建复杂 Release Metadata Platform。

---

# 8. A-05 修正 Domain Configuration 生命周期

这是进入 MotorControl M15 前必须修的语义问题。

## 当前错误行为 1

Domain 已经：

```text
ACTIVE
```

再次调用：

```text
activate(configuration=new_configuration)
```

当前实现可能直接返回 existing activation，造成：

```text
new_configuration 被静默忽略
```

## 当前错误行为 2

Domain：

```text
ACTIVE
→ DISABLED
→ activate()
```

如果本次未传 configuration，当前实现可能因为：

```python
configuration or {}
```

把旧配置替换为 `{}`。

这与：

```text
disable 不删除 Domain data
```

冲突。

## 正确语义

必须区分：

```text
configuration = omitted
configuration = {}
configuration = {...}
```

要求：

### 未提供

```text
保留 existing.configuration
```

### 显式 `{}`

```text
按 plugin schema 验证
合法才清空
不合法则拒绝
```

### 提供新 configuration

```text
schema validate
→ persist
→ revision + 1
→ updated_at 更新
```

### ACTIVE 状态再次 activate

不能静默忽略配置。

可以：

```text
把 activate 视作 idempotent + configuration reconciliation
```

或者用当前最小兼容方式修正。

## 最小范围原则

本轮必须修：

```text
activate / re-activate configuration semantics
```

本轮不强制做：

```text
完整 Configuration Management API
ETag 系统
复杂 audit history
```

这些属于 B 类。

## 测试

至少：

```text
test_reactivate_preserves_configuration_when_omitted
test_active_reactivation_applies_new_configuration
test_explicit_empty_configuration_is_validated
test_configuration_revision_increments
test_disable_does_not_delete_configuration
```

---

# 9. A-06 Domain Configuration 最小 Schema Validation

当前已经存在 Domain schema API，因此 activation 不应继续无验证保存任意 dict。

## 修改目标

形成最小闭环：

```text
Domain plugin schema
→ configuration
→ validate
→ activation
```

要求：

- plugin schema 自身非法：fail closed；
- activation configuration 不符合 schema：拒绝；
- 拒绝后不产生部分写入；
- 旧配置 re-enable 时也必须检查 compatibility；
- activation snapshot 记录 schema/version 信息；
- 返回结构化错误。

推荐错误：

```text
DOMAIN_CONFIGURATION_INVALID
```

如果已有等价错误体系则复用，不要重复造错误码。

新增错误时同步：

```text
Core error model
Backend schema
OpenAPI
TypeScript
Tests
```

---

# 10. A 类完成条件

以下全部满足：

```text
A-01 PASS
A-02 PASS
A-03 PASS
A-04 PASS
A-05 PASS
A-06 PASS
```

则：

```text
M14R = COMPLETE
READY_FOR_M15 = YES
```

注意：

```text
B 类未完成
C 类未完成
```

都不能使：

```text
READY_FOR_M15 = NO
```

---

# 11. B 类：当前架构完善项

本章是：

```text
NON-BLOCKING ENGINEERING IMPROVEMENTS
```

不是正式 Future Upgrade。

Codex 可以：

```text
顺手做
独立小 PR
或按原 Milestone 延后
```

不得拖慢主线。

---

# 12. B-01 Capability Selection 形成真正 SSOT

当前：

```text
resolve / validate
```

可以传：

```text
selected_capabilities
```

但真实 activate 路径尚未完整持久化/应用。

长期必须保证：

```text
validate plan
=
activation plan
=
runtime plan
=
restart/recovery plan
```

## 推荐设计

未来 `DomainActivationRequest` 可包含：

```json
{
  "configuration": {},
  "selected_capabilities": {},
  "activated_by": "..."
}
```

并持久化 project-scoped capability selection。

## 完成时机

如果 M15 只有一个 MotorControl provider，没有 capability ambiguity：

```text
不阻断 M15
```

但在：

```text
2 个以上 Domain 提供同一 capability
```

进入生产组合测试前必须完成。

---

# 13. B-02 Domain Activation SQL Transaction Ownership

当前 repository 的：

```text
add()
save()
```

可能内部直接 commit。

多 Domain activation 时存在：

```text
dependency A 已 commit
dependency B 已 commit
requested domain 失败
```

造成 partial activation 的风险。

## 正确长期方向

```text
Application Service / UnitOfWork
    controls transaction

Repository
    add / save / flush
```

## 进度规则

如果可以小范围修：

```text
现在修
```

如果会波及大面积 repository API：

```text
DEFER TO M18A
```

完整：

```text
Outbox
Inbox
SideEffectJournal
Recovery
Crash injection
```

仍然属于 M18A，不得提前。

---

# 14. B-03 Domain Configuration PATCH / ETag

未来推荐增加：

```http
PATCH /api/v1/projects/{project_id}/domains/{domain_id}/configuration
```

支持：

```text
If-Match
revision
actor
validation
```

但：

```text
不是 M15 Gate
```

A-05 修完后，M15 可以先继续使用 activation API。

---

# 15. B-04 Domain UI Route Hardening

当前 UI metadata route 过滤未来应升级为：

```text
normalize
→ internal-route allowlist
```

规则建议：

```text
必须以 /
禁止 //
禁止 URI scheme
禁止 http:
禁止 https:
禁止 javascript:
禁止 data:
禁止 file:
禁止 control character
禁止 leading/trailing whitespace bypass
```

当前仅 bundled plugin：

```text
风险有限
```

因此：

```text
不阻断 M15
```

最迟在：

```text
M21 Desktop UI
或
signed/community plugin 开放前
```

完成。

---

# 16. B-05 Project Isolation 持续作为硬约束

此前 Project Scope Hardening 已处理：

```text
Document
DocumentIR
Evidence
content-hash metadata isolation
```

这些不得回退。

未来所有新实体都必须明确：

```text
project-scoped?
global?
private?
shared?
readonly?
```

Repository 查询必须优先显式传：

```text
project_id
```

API 必须从 path/project context 做 scope 校验。

## 每个项目最终应拥有独立工程上下文

```text
Project
├── requirements
├── documents
├── evidence
├── claims
├── devices
├── pins
├── hardware
├── circuit
├── schematic
├── MCU config
├── firmware
├── source/workspace
├── build
├── static analysis
├── domains
├── protocol
├── tests
├── review
├── knowledge snapshot
└── debug/history
```

这是一条持续架构约束。

不是每个 Milestone 都要重新实现 Project Isolation Framework。

---

# 17. B-06 每个 Project 独立 Code / Hardware / Test / Workspace

用户明确要求：

```text
不同项目互不干扰
```

最终建议逻辑结构：

```text
projects/{project_id}/
├── workspace/
├── imported-source/
├── artifacts/
├── builds/
├── tests/
├── logs/
└── debug/
```

实际物理存储可以采用：

```text
SafePath
Object Storage
Git worktree
Database metadata
```

组合实现。

现在：

```text
只需保证 scope 正确
```

完整 SourceWorkspace SSOT：

```text
按 M18C / M22
```

继续，不允许在 M14R 提前做完整重构。

---

# 18. B-07 Frontend 保持简约 Codex / Engineering IDE 风格

前端继续保持：

```text
简约
高级
低视觉噪声
工程信息优先
Codex/IDE 风格
```

推荐稳定布局：

```text
┌ Project / Engineering Tree ┐
│                            │
├────────────────────────────┤
│       Main Workspace       │
│                            │
├────────────────────────────┤
│ Build / Test / Tool / Log  │
└────────────────────────────┘

右侧：
AI / Context / Issue
可折叠
```

禁止：

```text
大量渐变
复杂动画
大量卡片
无意义 KPI
同屏堆很多曲线
纯展示式 Dashboard
```

## Project 首页只保留

```text
Project status
Current phase
Blockers
Recent activity
Build/Test summary
Important issues
```

## 子页面可逐步支持

```text
Overview
Requirements
Documents
Pins
Hardware
Schematic
MCU Config
Firmware
Code
Build
Static Analysis
Domains
Protocol
Tests
Review
Knowledge
Debug
Settings
```

但原则：

```text
后端 capability 存在
→ 页面启用

后端 capability 尚未存在
→ 不伪造
```

---

# 19. B-08 Domain UI 必须动态扩展

M15 MotorControl Plugin 可以贡献：

```text
navigation metadata
form metadata
schema metadata
action metadata
context metadata
```

Frontend 根据：

```text
/projects/{id}/domains
/projects/{id}/ui/extensions
```

或当前既有等价 API 动态展示。

允许有：

```text
/motor-control
```

兼容入口。

但 Project shell 不得写死：

```text
MotorControl 一定存在
```

必须继续支持：

```text
0 Domain
```

普通 MCU 项目。

---

# 20. B-09 ELKB 保持既定路线，不提前

ELKB 已经是正式架构的一部分，不属于新 Future Upgrade。

继续按既定 Milestone：

```text
M23 Knowledge & Memory Core
M24 ELKB-1 Learning Knowledge Domain
M25 Learning Document Extraction
M26 Authority / Trust / License
M27 ContextBuilder Integration
M32 Technical Knowledge Discovery
```

## ELKB 定位

```text
Embedded Learning Knowledge Base
```

不是简单：

```text
vector RAG
```

也不是：

```text
auto fine-tuning
```

未来知识结构包括：

```text
Concept
Principle
Algorithm
Equation
Guideline
Tradeoff
Failure Mode
Applicability
Evidence
Authority
License
Relation
```

私有资料默认：

```text
USER_PRIVATE
PROJECT_PRIVATE
```

禁止自动升级为 Global Trusted。

---

# 21. B-10 ERIS / OSDLE 主动学习按既定路线实施

开源学习能力仍按照：

```text
M29 ERIS Foundation
M30 Repository Intelligence
M31 OSDLE + Budget
M32 Technical Knowledge Discovery
M33 Sandbox Hardening + Curator
```

执行。

外部 Repo：

```text
Discovery
→ Fetch
→ Sandbox
→ Analyze
→ Candidate
→ Curate
→ Promote
```

不得：

```text
clone = trusted
```

不得直接运行未知：

```text
build script
post-install
binary
```

典型学习源未来可以包括：

```text
SimpleFOC
VESC
ODrive
Zephyr
FreeRTOS
MCUboot
TinyUSB
lwIP
```

但不是现在的 M14R 工作。

---

# 22. B-11 优先集成成熟开源工具

原则：

```text
EEA 自己掌控：
Engineering IR
Rules
Evidence
Orchestration
Project Scope
Authority
Determinism

第三方：
通过 Adapter 集成
```

可评估：

```text
KiCad
Cppcheck
Tree-sitter
CMake
PlatformIO
OpenOCD
pyOCD
Renode
Docling
Qdrant
LiteLLM
LangGraph
```

使用前检查：

```text
License
Version pin
Sandbox
Determinism
Normalized I/O
Evidence
Failure semantics
```

第三方 SDK 不得泄漏进 Core。

---

# 23. B-12 FOC 只是 Reference Benchmark

M15：

```text
MotorControl = Built-in Domain Plugin
```

FOC：

```text
Reference Benchmark
```

不能把 EEA 变成 FOC 专用平台。

在 FOC E2E 后继续验证：

```text
plain MCU
```

例如：

```text
STM32G431
UART
CAN
SPI Sensor
FreeRTOS
```

不加载 MotorControl，也要可以走完整工程路径。

---

# 24. B-13 Source Authority 按原计划实施

未来必须解决：

```text
generated code
imported code
user code
git code
workspace code
artifact
```

谁是 SSOT。

但完整工作继续放：

```text
M18C
M22
```

M14R 不提前实现完整 Git Workspace。

---

# 25. B-14 Hardware Safety 按原计划实施

MotorControl 最终需要：

```text
SafeState
E-Stop
flash policy
commissioning
hardware-session ownership
physical confirmation
```

但完整能力继续放：

```text
M18D
M35
```

M15 只做 Domain Plugin 本身，不顺便实现完整板级安全系统。

---

# 26. B-15 文档治理

以后避免不停新增：

```text
最终方案
最终新版方案
升级方案
修正版
修正版2
```

规则：

### 架构发生变化

```text
更新冻结文档
+ changelog
```

### 实现问题

```text
对应 Milestone report
或
单一 correction task
```

### 后续升级

```text
统一维护 Future Upgrade Roadmap
```

避免 Codex 同时读取多个冲突版本。

---

# 27. C 类：正式 Future Upgrade Roadmap

下面 4 项才是用户确认的：

```text
EEA 正式后续升级方向
```

它们与前面的 B 类工程完善不同。

统一编号：

```text
FU-01
FU-02
FU-03
FU-04
```

当前全部：

```text
NON-BLOCKING
```

---

# 28. FU-01 大型项目支持 / EngineeringScope

## 目标

EEA 最终需要支持：

```text
几十万
到
百万行级代码
```

以及：

```text
多 MCU
多仓库
多固件
多板卡
多子系统
多模块
复杂依赖
长期演进
```

不能假设：

```text
一个 Project
=
一个小仓库
=
一个 firmware target
```

## Future Capability

建议引入概念：

```text
EngineeringScope
```

例如：

```text
Project
└── EngineeringScope
    ├── Repository
    ├── Workspace
    ├── Module
    ├── Target
    ├── Board
    ├── Firmware
    ├── Hardware Unit
    ├── Test Scope
    └── Knowledge Scope
```

支持：

```text
hierarchical scope
incremental analysis
dependency graph
scope-aware retrieval
scope-aware Agent context
scope-aware build/test
scope-aware evidence
scope-aware changes
```

## 大型代码库核心问题

未来必须解决：

```text
全仓库不能一次塞给 LLM
```

因此需要：

```text
Symbol Index
AST Index
Dependency Graph
Call Graph
Include Graph
Build Graph
Change Graph
Evidence Graph
Semantic Index
```

以及：

```text
incremental indexing
incremental invalidation
incremental build/test
incremental context assembly
```

## 接入阶段

当前只做架构兼容性预留。

建议：

```text
M14：Domain/Project model 不封死
M18：Workspace / transaction / source scope 基础
M27：ContextBuilder scope-aware
M30：Repo Intelligence 完善大型代码理解
```

## 绝不阻断当前进度

```text
M15 不需要实现 EngineeringScope
```

只需要避免写死：

```text
project == single workspace == single target
```

---

# 29. FU-02 Component Intelligence Database

## 目标

建立真正面向电子/嵌入式工程的结构化元器件智能数据库。

它不是简单：

```text
PDF storage
```

也不是只做：

```text
datasheet RAG
```

而是：

```text
Component Intelligence
```

## 数据对象

未来至少包括：

```text
MCU
MPU
SoC
FPGA
Gate Driver
MOSFET
Power IC
ADC/DAC
OpAmp
Encoder
IMU
Sensor
CAN Transceiver
EtherCAT PHY
RS485
Ethernet PHY
Memory
Connector
Crystal
Protection Device
Power Module
Motor
Actuator
```

## 每个 Component 可以包含

```text
manufacturer
mpn
category
lifecycle
package
voltage
current
temperature
clock
memory
peripherals
interfaces
pin functions
electrical constraints
timing
recommended circuit
reference design
errata
datasheet revisions
application notes
availability metadata
alternative parts
compatibility
evidence
authority
license
```

## Engineering Intelligence

需要支持：

```text
参数比较
器件选型
替代料
兼容检查
Pin capability
Power compatibility
Interface compatibility
Reference Design retrieval
Errata warning
Constraint propagation
```

## 与现有 EEA 连接

未来连接：

```text
HardwareIR
DeviceSelectionIR
PinIR
CircuitIR
SchematicIR
RequirementIR
ELKB
Evidence
Rules
Agent
```

## 建议阶段

```text
M23 Knowledge & Memory Core
```

附近开始接入。

但它作为正式升级能力可以独立版本化。

## 当前要求

现在只需要确保：

```text
Hardware entities 有稳定 ID/reference
Evidence/Authority 模型可复用
Global component data 与 Project private engineering data 可区分
```

不要现在开始爬取全网 datasheet。

---

# 30. FU-03 EdgeAI Domain Plugin

## 目标

未来新增：

```text
EdgeAI Domain Plugin
```

使 EEA 能支持：

```text
嵌入式 AI
TinyML
MCU AI
NPU deployment
Edge inference
```

## 能力范围

未来工作流：

```text
Model
→ analyze
→ target compatibility
→ optimization
→ quantization
→ conversion
→ compile
→ memory planning
→ deploy
→ benchmark
→ validate
```

## 支持内容

### Model

```text
ONNX
TFLite
PyTorch exported model
vendor model format
```

### Optimization

```text
INT8
INT4（硬件支持时）
FP16
pruning
operator fusion
memory reuse
```

### Deployment targets

例如：

```text
STM32
ESP32
NXP
Renesas
Rockchip
Jetson
other MCU/SoC/NPU
```

具体支持以后通过 provider/adapter 扩展。

## EdgeAI IR

未来可设计：

```text
EdgeAIIR
ModelIR
QuantizationIR
DeploymentIR
BenchmarkIR
```

但：

```text
不能放入 Core-specific AI assumptions
```

它应继续遵循现有：

```text
Domain Plugin
Capability
IR reference
Rule
Generator
Context contribution
UI contribution
```

架构。

## 当前要求

现在不实现 EdgeAI。

只需确保：

```text
Domain Framework 足够通用
```

不要让 Domain Framework 只服务 MotorControl。

---

# 31. FU-04 LLM Cost & Context Budget System

## 目标

EEA 后续会出现：

```text
大仓库
多 Agent
长任务
大量工具调用
大量知识检索
多个模型
```

必须管理：

```text
Token
Context
API Cost
Latency
Tool Budget
Agent Budget
Knowledge Budget
```

## Future Model

可以设计：

```text
BudgetPolicy
ContextBudget
TokenBudget
CostBudget
ToolBudget
RetrievalBudget
AgentBudget
```

## ContextBuilder

最终 ContextBuilder 需要根据：

```text
task
EngineeringScope
risk
authority
relevance
recency
evidence
budget
```

动态选择上下文。

不允许：

```text
把所有代码
所有文档
所有历史消息
所有 ELKB
全部塞给模型
```

## 模型路由

未来支持：

```text
simple task → low-cost model
planning/review → stronger model
large code context → context-optimized model
vision task → vision-capable model
```

具体 Provider 通过 Adapter / Model Gateway。

## 可观测性

未来应该记录：

```text
per task tokens
per agent tokens
per model cost
per tool cost
retrieval count
context composition
cache hit
latency
budget exceeded
```

## 建议阶段

```text
M27 / M28
```

附近重点接入。

ERIS/OSDLE 也可以复用 Budget Policy。

## 当前要求

现在只做：

```text
接口不封死
```

不要求当前实现成本计费系统。

---

# 32. 四项 Future Upgrade 的优先关系

推荐：

```text
FU-01 EngineeringScope
        ↓
FU-04 Context & Cost Budget

FU-02 Component Intelligence
        ↓
ELKB / Hardware Intelligence

FU-03 EdgeAI
        ↓
建立在成熟 Domain Framework 上
```

不是严格串行。

但当前主线：

```text
M15+
```

优先级高于 Future Upgrade。

---

# 33. Future Upgrade 当前实施规则

Codex 如果在当前开发中遇到与 FU-01~04 有关的设计点：

只允许：

```text
预留扩展点
避免写死假设
写 backlog note
```

禁止：

```text
提前实现整个 Future Upgrade
```

例如：

### 正确

```text
Project API 不写死只有一个 target_id
```

### 错误

```text
为了 FU-01 现在直接重写整个 Project/Workspace/Build 系统
```

### 正确

```text
Domain Framework 保持通用
```

### 错误

```text
现在直接创建完整 EdgeAI runtime
```

---

# 34. M15 开始条件

M15 只依赖：

```text
A 类全部 PASS
```

不依赖：

```text
B 类全部完成
FU-01 完成
FU-02 完成
FU-03 完成
FU-04 完成
```

即：

```text
A complete
→ START M15
```

---

# 35. M15 范围控制

M15 只实现：

```text
plugins/builtin/motor_control/
```

或当前 Architecture Freeze 规定的等价路径。

主要内容：

```text
MotorControl DomainDescriptor
MotorControlIR
rules
generator declarations
context metadata
UI metadata
activation integration
tests
```

## SSOT 规则

```text
Timer / PWM / ADC / DMA / IRQ
→ MCUConfigIR

Inverter / Encoder / CurrentSense
→ HardwareIR

MotorControlIR
→ references + control requirements
```

不要产生第二事实源。

## 禁止顺手加入

```text
full hardware commissioning
full E-stop runtime
full flash orchestration
EdgeAI
EngineeringScope
Component DB
full Outbox
full ELKB
```

---

# 36. M15 后继续按既定主线推进

本轮修正后继续现有 M0–M36 路线。

不要因为本文件创建新的长期：

```text
M14R → M14R2 → M14R3 → ...
```

M14R 只用于恢复 repository acceptance discipline。

---

# 37. Codex 输出格式

Codex 完成本轮后必须输出：

```text
1. EXACT_BASE_SHA
2. EXACT_FINAL_SHA

3. BLOCKERS_FIXED
4. MODIFIED_FILES
5. ROOT_CAUSES
6. FIXES_APPLIED

7. TESTS_ADDED
8. FOCUSED_TEST_RESULTS
9. FULL_TEST_RESULTS

10. MIGRATION_HEAD
11. OPENAPI_RESULT
12. TYPESCRIPT_CONTRACT_RESULT
13. DESKTOP_RESULT

14. CI_RUN_ID
15. CI_RESULT

16. REMAINING_NON_BLOCKING_ENGINEERING_ITEMS

17. FUTURE_UPGRADE_STATUS
    FU-01 = NOT_STARTED / RESERVED
    FU-02 = NOT_STARTED / RESERVED
    FU-03 = NOT_STARTED / RESERVED
    FU-04 = NOT_STARTED / RESERVED

18. HUMAN_ACCEPTANCE_STATUS

19. READY_FOR_M15 = YES / NO
```

---

# 38. READY_FOR_M15 判定

只有 A 类影响 READY。

```text
A-01 PASS
A-02 PASS
A-03 PASS
A-04 PASS
A-05 PASS
A-06 PASS
```

则：

```text
READY_FOR_M15 = YES
```

B 类未完成：

```text
NON_BLOCKING
```

C/FU 未完成：

```text
PLANNED
NON_BLOCKING
```

不得因为未来升级尚未开发而输出：

```text
READY_FOR_M15 = NO
```

---

# 39. 最终验收命令

至少：

```bash
ruff check .
ruff format --check .
mypy

python -m eea_cli db upgrade
alembic check

pytest

eea openapi export --check
eea openapi typescript --check

pnpm lint
pnpm typecheck
pnpm build
```

focused 至少覆盖：

```bash
pytest tests/test_m5_sandbox.py -q
pytest tests/test_m14_domain_extensions.py -q
```

如果当前仓库有 project scope hardening focused test，继续执行。

新增 Domain configuration 测试必须进入 focused suite。

---

# 40. 最终工程原则

所有修改继续按：

```text
Correctness
→ Safety
→ Reproducibility
→ Project Isolation
→ Evidence
→ Determinism
→ Maintainability
→ Performance
→ UI polish
```

推进。

但同时遵守另一条同等重要的规则：

```text
非关键优化不得阻断主线开发。
```

最终目标不是：

```text
在 M14 无限追求完美
```

而是：

```text
修掉会污染后续架构的问题
→ 建立可靠 Gate
→ 继续 M15/M16/...
→ 在正确阶段实现更大的能力
```

---

# 41. 本文档中的分类必须长期保持

以后所有新增需求优先判断：

```text
这是当前 bug？
这是既定 Milestone 能力？
这是工程完善？
还是 Future Upgrade？
```

不要再把四者混成一个清单。

当前正式 Future Upgrade 永久记录为：

```text
FU-01 EngineeringScope
FU-02 Component Intelligence Database
FU-03 EdgeAI Domain Plugin
FU-04 LLM Cost & Context Budget System
```

除非用户后续明确增加、删除或修改，否则不要自行改变这 4 项。
