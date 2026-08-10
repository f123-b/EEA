# EEA V1.3.1 — Codex 增量修正指令

> **用途**：本文件只用于修正 EEA V1.3 Architecture Freeze 中已经确认的架构矛盾和实施顺序问题。  
> **目标读者**：正在实施 EEA 的 Codex。  
> **执行方式**：增量修正，不重做项目，不推翻已经正确实现的模块。  
> **优先级**：本文件对下面明确列出的冲突项，优先于 EEA V1.3 对应旧表述；未列出的内容继续以 EEA V1.3 原文为准。

---

# 0. Codex 必须先遵守的执行规则

1. **不要删除、重建或整体重构当前 EEA 代码库。**
2. 先读取当前代码、当前 Milestone、数据库 migration、API、测试和目录结构，再判断每个 FIX 是否已经部分完成。
3. 已经满足本文件验收条件的实现保持不动，只补缺失测试/文档。
4. 已有实现与本文件冲突时，使用**最小兼容迁移**修正；禁止为了“结构更漂亮”扩大修改范围。
5. **不要重新编号 M0–M36。** 本文件使用 `FIX-01`～`FIX-10` 作为插入式修正任务。
6. 不要新引入 Kafka、NATS、Graph DB、新 Web 框架、新数据库或新的插件框架；当前 SQLite/PostgreSQL + InProcess EventBus + Qdrant + Git + Tauri/FastAPI 体系保持不变。
7. 不要把 MotorControl 重新放回 Core。
8. 不要让 Plugin 直接访问 DebugProbe/Serial/CAN/Flash/Actuator 等 raw hardware adapter。
9. 不要把 `Flash SUCCESS`、`Build SUCCESS` 或 `Tool SUCCESS` 解释成硬件安全验证成功。
10. 每完成一个 FIX，必须运行该 FIX 的验收测试；未通过不得把对应 milestone 标记 PASS。
11. 如果当前 Codex 已经实施到某个后续 Milestone，**不要回滚进度**；立即插入所缺 FIX，完成迁移后继续现有 Milestone。
12. 如果本文件没有要求修改某个模块，不要顺手重构它。

---

# 1. 总体执行顺序

按以下顺序处理，后一个 FIX 不得反向破坏前一个 FIX：

```text
FIX-01  Core / Domain 边界清理
FIX-02  Canonical Unit 前移
FIX-03  SourceRevision / BuildInputSnapshot 前移
FIX-04  Domain Composition 前移
FIX-05  Durable Outbox Delivery / Recovery
FIX-06  Hardware 三层 Fail-safe
FIX-07  FOC Gate 与 Hardware Adapter 顺序修正
FIX-08  Job / Permission / API Error 横向同步
FIX-09  SafetyLimit / CapabilityBroker / Source Snapshot 收口
FIX-10  Consistency Checker 与最终回归
```

如果当前代码已经超过对应插入点：

```text
DO NOT ROLLBACK
→ implement missing FIX
→ migrate existing data/API/code minimally
→ add compatibility layer if needed
→ run regression
→ continue current milestone
```

---

# 2. FIX-01 — 彻底清理 MotorControl 的 Core / Plugin 边界

## 2.1 问题

EEA V1.3 已规定 MotorControl 是 Built-in Domain Plugin，但部分 Core 文档仍把 `MotorControlIR` / `MotorControlService` 当作 Core Schema/Application Service。

这会造成两套 MotorControl：

```text
core/.../motor_control
plugins/builtin/motor_control/...
```

**这是禁止的。**

## 2.2 必须修改的文档

### `02_DOMAIN_MODEL_AND_SCHEMA.md`

将原：

```text
# 17. MotorControlIR

至少：motor、inverter、encoder、current_sense、pwm、adc_sampling、
electrical_angle、loops、sign_convention、startup、limits、faults。
详见 16 文档。
```

替换为：

```text
# 17. DomainIRRef / DomainIREnvelope

DomainIRRef：
- project_id
- domain_id
- domain_ir_id
- domain_schema_version
- plugin_id
- plugin_version
- revision

DomainIREnvelope：
- ref: DomainIRRef
- requirement_ids
- evidence_ids
- core_ir_refs
- extension_payload_ref

Core 只保存 Domain IR 的统一引用/封装，不定义 MotorControlIR、EtherCATIR、
RoboticsIR 等具体领域字段。

具体 MotorControlIR 仅定义在：
`16_MOTOR_CONTROL_DOMAIN_SPEC.md`
以及：
`plugins/builtin/motor_control/`
```

**不要改变后续章节编号。** 原 `#18 RTOS` 继续保持 `#18`。

### `01_TECHNICAL_SPEC.md`

在 `# 5. Application Services` 中：

删除 Core Service：

```text
MotorControl
```

增加/确认：

```text
DomainExtension
DomainComposition
DomainCapability
```

Core Application Services **不得出现**：

```text
MotorControlService
MotorControlAgent
MotorControlGenerator
```

这些只能在 MotorControl Plugin 内存在。

在 `# 13. Schema Versioning` 中：

删除 Core schema-version 列表中的：

```text
MotorControlIR
```

增加/确认：

```text
DomainDescriptor
DomainActivation
DomainIREnvelope
```

并补一句：

```text
具体 Domain IR 的 schema_version 由对应 Domain Plugin 管理；
Core 只验证 Plugin API compatibility、DomainDescriptor 和 DomainIREnvelope。
```

## 2.3 代码硬约束

允许：

```text
core/domain/domain_descriptor.*
core/domain/domain_activation.*
core/domain/domain_ir_ref.*
core/domain/domain_composition.*
core/application/domain_extension_service.*
core/application/domain_composition_service.*
```

禁止：

```text
core/**/motor_control*
core/**/foc*
core/** import plugins.builtin.motor_control
```

MotorControl 必须仅存在于：

```text
plugins/builtin/motor_control/
```

## 2.4 验收

必须新增自动检查：

```text
CORE_MUST_NOT_DEFINE_MOTOR_CONTROL
CORE_MUST_NOT_IMPORT_MOTOR_CONTROL_PLUGIN
```

验收条件：

- 不加载任何 Domain Plugin，可以创建普通 MCU 项目。
- Core unit tests 在没有 MotorControl package import 的情况下通过。
- 搜索 `core/` 不存在 MotorControlIR/MotorControlService/FOC-specific schema。

---

# 3. FIX-02 — Canonical Unit 必须前移，不得等到 M18E

## 3.1 插入点

**必须在 M7 Pin Planner + Core Rule Engine 开始依赖工程数值比较之前完成。**

如果 M7/M9 已经实现，不回滚；立即迁移现有 Rule 输入。

## 3.2 `EngineeringValue` 最终契约

Core 中只保留一套工程数值类型：

```python
class EngineeringValue(BaseModel):
    unit: str
    dimension: str
    canonical_unit: str

    nominal: float | None = None
    minimum: float | None = None
    typical: float | None = None
    maximum: float | None = None

    normalized_nominal: float | None = None
    normalized_minimum: float | None = None
    normalized_typical: float | None = None
    normalized_maximum: float | None = None

    tolerance_percent: float | None = None
    condition: dict[str, object] = {}
    evidence_ids: list[UUID] = []
```

规则：

```text
输入显示值
→ UnitNormalizationService
→ canonical unit + dimension + normalized value
→ Rule / Claim conflict / Equation
```

禁止 Rule 自己实现：

```text
if unit == "mV": ...
if unit == "kV": ...
```

## 3.3 最低支持 dimension

V1.3.1 至少冻结：

```text
VOLTAGE
CURRENT
RESISTANCE
CAPACITANCE
INDUCTANCE
FREQUENCY
TIME
TEMPERATURE
ANGLE
ANGULAR_VELOCITY
LENGTH
POWER
ENERGY
DIMENSIONLESS
```

后续可以扩展，但不能让各 Domain 自创重复 dimension 名。

## 3.4 验收

必须至少通过：

```text
24 V == 24000 mV
48 V > 40 V
1 kHz == 1000 Hz
1000 us == 1 ms
VOLTAGE 与 CURRENT 不允许直接比较
```

M7/M9 已有 Rule 全部迁移到 normalized value。

---

# 4. FIX-03 — SourceRevision 必须在第一次 Real Build 前存在

## 4.1 插入点

`SourceRevision + SourceWorkspaceService + BuildInputSnapshot` 必须成为 **M12 Firmware Generator + Real Build 的前置能力**。

不要等 M18C。

如果 M12 已经实现：

```text
保留现有 Build Adapter
→ 给 Build 输入补 SourceRevision / BuildInputSnapshot
→ 给已有 BuildRun 加 migration/nullable compatibility
→ 新 BuildRun 强制绑定
```

## 4.2 Source of Truth

唯一关系：

```text
Requirements / IR
        ↓
Generated Source Candidate
        ↓ apply
Git Working Tree        ← 可编辑源码字节 SSOT
        ↓ snapshot
SourceRevision
        ↓
BuildInputSnapshot
        ↓
BuildRun
        ↓
Binary / ELF / MAP Artifact
```

禁止：

```text
FirmwareIR = source bytes SSOT
Artifact = editable source SSOT
DB = second editable source tree
```

## 4.3 `SourceRevision`

至少：

```text
project_id
repository_id
commit_sha
tree_hash
base_commit
dirty
workspace_revision
source_manifest_hash
created_by
created_at
```

## 4.4 新增 `BuildInputSnapshot`

必须明确实际参与 Build 的内容：

```text
id
project_id
source_revision_id
tracked_file_manifest_hash
allowed_untracked_input_hash
generated_input_hash
submodule_commit_map
build_config_hash
toolchain_id
toolchain_version
environment_profile_hash
source_manifest_hash
build_input_hash
created_at
```

### 文件纳入规则

必须冻结：

1. Git tracked 文件：纳入。
2. Build 实际读取的 generated-owned 文件：纳入。
3. 明确允许的 untracked build input：纳入并 hash。
4. 未声明但 Build 实际依赖的 untracked 文件：Build Fail。
5. submodule：绑定具体 commit。
6. symlink：必须经过 SafePath；目标越界直接拒绝。
7. `.gitignore` 不代表自动排除 BuildInput；以 Build 实际输入规则为准。
8. line ending 不做隐式重写；hash 针对实际 Build bytes。
9. Build cache 不属于 source input，但 cache key 必须包含 `build_input_hash`。

## 4.5 AI Edit

AI 只允许：

```text
PatchProposal(base SourceRevision)
→ Diff
→ Validate
→ Apply
→ SourceChanged Outbox
```

不得直接写 Working Tree。

## 4.6 验收

- stale PatchProposal → `409 SOURCE_REVISION_CONFLICT`
- concurrent edit 不覆盖
- BuildRun 必须有 `build_input_snapshot_id`
- 修改未声明的 untracked build dependency 会被检测
- 同一 `build_input_hash + toolchain + environment` 可追溯到相同输入集合

---

# 5. FIX-04 — Domain Composition 必须并入 M14，在 M15 之前完成

## 5.1 插入点

现有：

```text
M14 Domain Extension Infrastructure
M15 MotorControl Built-in Plugin
```

改为：

```text
M14 Domain Extension + Composition Infrastructure
→ M15 MotorControl Built-in Plugin
```

不要新建第二套插件系统。

## 5.2 M14 必须一次完成

```text
DomainExtensionRegistry
DomainDescriptor
DomainIRRef / DomainIREnvelope
DomainActivation
DomainCompositionService
CapabilityRegistry
dependency resolution
conflict resolution
Rule phase ordering
Generator DAG ordering
migration compatibility check
activation/deactivation API
```

## 5.3 `DomainDescriptor` 最终字段

至少：

```text
domain_id
version
schema_refs
rule_pack_ids
generator_ids
ui_contributions

requires_domains
optional_domains
conflicts_with

provided_capabilities
required_capabilities
priority

rule_phases
generator_phases
migration_provider
```

旧的单字段：

```text
capabilities
```

迁移为：

```text
provided_capabilities
required_capabilities
```

如已有数据，migration 可以兼容读取旧字段，但新写入使用新字段。

## 5.4 确定性要求

禁止：

```text
Python import order
plugin load order
last registered wins
```

多个 capability provider 必须：

```text
explicit project selection
→ deterministic priority
→ compatibility check
→ otherwise conflict error
```

Generator 使用 DAG，cycle 直接 BLOCKED。

## 5.5 验收

M15 开始前必须通过：

```text
0 Domain
1 mock Domain
2 compatible Domains
missing required domain
conflicting domains
duplicate capability provider
generator cycle
disable/enable
plugin version migration dry-run
```

然后 MotorControl 作为第一个真实 Domain 接入，不允许 MotorControl 自带第二套 composition 逻辑。

---

# 6. FIX-05 — Outbox 改成真正的 Durable Delivery / ACK

## 6.1 当前问题

仅有：

```text
Outbox → InProcess EventBus → SENT
```

不够。

以下窗口会丢事件：

```text
publish
→ outbox marked SENT
→ process crash
→ consumer 尚未提交业务结果/processed_event
```

## 6.2 不引入 Kafka/NATS

继续使用：

```text
SQL + InProcess EventBus
```

但 SQL 必须保存每个 critical consumer 的 durable delivery state。

## 6.3 `outbox_events`

状态改为：

```text
PENDING
DISPATCHING
COMPLETED
DEAD
```

**不要再把 `SENT` 当成完成语义。**

字段至少：

```text
id
aggregate_type
aggregate_id
event_type
payload
project_id
actor_id
aggregate_revision
idempotency_key
trace_id
job_id
created_at
available_at
status
last_error
```

## 6.4 新增 `event_deliveries`

```text
id
event_id
consumer_id
required: bool

status:
  PENDING
  PROCESSING
  ACKED
  FAILED
  DEAD

attempt_count
last_error
next_attempt_at
lease_until
created_at
acked_at

UNIQUE(event_id, consumer_id)
```

## 6.5 关键消费流程

```text
Business SQL Transaction:
    mutate aggregate
    insert outbox_event
COMMIT

Dispatcher:
    resolve registered critical consumers
    idempotently create event_deliveries

Delivery Worker:
    claim one delivery with lease
    status = PROCESSING
    call consumer

Consumer:
    perform its SQL business mutation
    write/confirm processed_event
    ACK delivery
    COMMIT
```

对于 SQL consumer：

**consumer 业务结果 + `processed_event` + delivery ACK 尽量放在同一个 SQL transaction。**

如果 consumer 有 Object/Git/Qdrant/Tool side effect：

```text
SideEffectJournal
→ idempotent/reconcile
→ ACK only after durable result is known
```

## 6.6 Outbox 完成规则

只有：

```text
all required deliveries == ACKED
```

才能：

```text
outbox_event.status = COMPLETED
```

best-effort UI/WebSocket consumer 不必阻止 COMPLETED；UI 通过 REST resync 恢复。

## 6.7 Crash Recovery

启动 Recovery Manager：

```text
PROCESSING delivery + lease expired
→ PENDING
→ retry
```

不得因为 event 曾经被 publish 就跳过。

## 6.8 验收

新增 crash injection：

1. business commit 后、dispatcher 前 crash
2. delivery 创建后 crash
3. publish 后、consumer 前 crash
4. consumer 执行中 crash
5. consumer SQL commit 前 crash
6. consumer commit 后、ACK 前 crash
7. ACK 后、outbox COMPLETED 前 crash

最终必须满足：

```text
critical event 不丢
重复投递不产生重复 Artifact
重复投递不重复 Flash
重复投递不重复 destructive Git operation
Impact propagation 最终一致
```

---

# 7. FIX-06 — Hardware Safety 必须明确 Host / Target Firmware / Hardware 三层

## 7.1 原则

EEA Host 崩溃后不能依赖 Host 再发送一次 `disable PWM`。

正式安全模型：

```text
L1 Host Safety
EEA / Permission / ResourceLock / Commissioning / SafetyLimit

L2 Target Firmware Safety
LocalSafetySupervisor / command watchdog / control watchdog /
fault latch / local shutdown

L3 Hardware Safety
gate-driver fault / timer break / comparator / default-low enable /
physical E-stop / board protection
```

L2/L3 的具体能力取决于目标硬件，但其**支持状态必须可验证**，不能假设存在。

## 7.2 `22_HARDWARE_COMMISSIONING_SAFETY_SPEC.md` 必须增加

### `TargetSafetyCapability`

至少：

```text
command_heartbeat_supported
command_heartbeat_timeout

control_loop_watchdog_supported
control_loop_deadline

local_current_trip_supported
local_voltage_trip_supported
local_overspeed_trip_supported
encoder_fault_trip_supported
gate_driver_fault_supported

timer_break_supported
hardware_enable_default_safe
physical_estop_supported

fault_latch_supported
requires_manual_rearm

verification_status:
  VERIFIED
  SUPPORTED_UNVERIFIED
  NOT_SUPPORTED
  UNKNOWN
```

### `LocalSafetySupervisor`

对 Safety-Critical Domain，目标 Firmware 必须存在等价逻辑：

```text
Host heartbeat timeout
OR control-loop deadline miss
OR current trip
OR overspeed
OR invalid encoder
OR gate-driver fault
OR local safety rule trip
    ↓
torque/current target = 0
    ↓
disable actuator / PWM
    ↓
fault latched
    ↓
requires explicit re-arm
```

**不得依赖 Host 在线才能完成本地停机。**

## 7.3 MotorControl Plugin 必须贡献

MotorControl Generator/Rules 至少检查或生成：

```text
motor enable default = false
host command heartbeat
current limit
overspeed limit
encoder plausibility
gate-driver fault handling
PWM disable path
fault latch
control-loop deadline monitor
```

对于板级硬件支持项：

```text
TIM Break
hardware comparator
physical E-stop
gate-driver nFAULT
```

必须是：

```text
VERIFIED / NOT_SUPPORTED / UNKNOWN
```

不能虚构。

若 CommissioningProfile 要求某能力而状态为 `UNKNOWN`/`NOT_SUPPORTED`：

```text
COMMISSIONING_BLOCKED
```

## 7.4 `SafetyLimit` 必须使用 `EngineeringValue`

数值型字段：

```text
max_bus_voltage
max_phase_current
max_iq
max_id
max_speed
max_position_delta
max_temperature
watchdog_timeout
current_ramp_rate
speed_ramp_rate
```

统一使用 `EngineeringValue`。

以下可保持 dimensionless/enum：

```text
max_duty_cycle
safe_brake_policy
safe_output_state
```

## 7.5 Safety Limit 层级

冻结为：

```text
Component Absolute Limit
        ↓
Board Hardware Limit
        ↓
Project Production Limit
        ↓
Commissioning Limit
        ↓
Current Test Limit
```

约束：

```text
CurrentTest ≤ Commissioning ≤ Production ≤ Hardware/Component
```

Agent/Plugin 只能自动缩小限制。

扩大上层限制必须显式审批，并且不能超过已验证硬件绝对限制。

## 7.6 验收

必须证明：

- EEA 进程被 kill，目标 Firmware heartbeat timeout 后进入本地安全状态。
- Serial/CAN/USB 断开不会让旧 velocity/torque command 无限保持。
- Emergency Stop 后不会自动恢复。
- 未验证 encoder/sign 不允许高速度闭环。
- 未设置 current limit 不允许闭环使能。
- hardware capability UNKNOWN 不冒充 VERIFIED。

---

# 8. FIX-07 — FOC Release Gate 与 Hardware Adapter 顺序必须修正

## 8.1 不重编号 M0–M36

保留 M19/M20/M35 名称，但修改含义和前置关系。

## 8.2 M19 拆成两个 Gate

### `M19A FOC Software E2E Gate`

流程：

```text
Project
→ Requirement
→ Claims/Device
→ Architecture
→ PinMap
→ Hardware/Circuit
→ Schematic/ERC
→ MCUConfig
→ Domain Composition
→ activate MotorControl
→ MotorControlIR
→ Firmware
→ SourceRevision
→ BuildInputSnapshot
→ Code
→ Real Build
→ Static Analysis
→ Protocol
→ Test
→ Review
→ Impact
```

M19A **不允许宣称真实电机运行成功**。

### `M19B FOC Commissioning Gate`

必须有最低可用 Hardware Adapter：

```text
pyOCD OR OpenOCD
probe identity
flash
reset
halt
safe run control
ResourceLock
FLASH permission
ACTUATOR_ENABLE permission
```

流程：

```text
M19A PASS
→ target identity
→ flash
→ reset
→ SafeState
→ TargetSafetyCapability verify
→ sensor sanity
→ current offset
→ encoder direction/range
→ low-power/open-loop
→ phase/sign verification
→ current-loop limited
→ velocity limited
→ E-stop
→ evidence
```

可以使用：

```text
真实硬件
OR 经认可的 HIL
```

但是普通 unit test/纯 Mock 不能冒充 M19B。

## 8.3 M20

M20 Core Neutrality 在 M19A 后必须运行。

如果当前没有真实硬件/HIL：

```text
M19A = PASS
M19B = BLOCKED_HARDWARE
M20 仍可执行
```

**不得把 M19B 写成 PASS。**

## 8.4 M35 改为 Advanced Hardware Debug

M35 不再是第一次具备 Flash 能力。

M35 聚焦：

```text
advanced debug
instrument
waveform capture
automated hardware regression
Renode/HIL expansion
multi-probe
fault injection
performance measurement
```

最低 pyOCD/OpenOCD Flash/Reset/Identity 能力必须提前供 M19B 使用。

---

# 9. FIX-08 — Job / Permission / API Error 必须全局同步

## 9.1 JobStatus

Core 唯一枚举：

```text
QUEUED
RUNNING
BLOCKED_PERMISSION
BLOCKED_RESOURCE
RECOVERING
SUCCESS
FAILED
FAILED_NEEDS_RECONCILE
CANCELLED
```

禁止各模块自创字符串状态。

数据库、Pydantic Schema、OpenAPI、TypeScript SDK、WebSocket、Frontend 状态显示统一使用这一枚举。

## 9.2 Permission

Core Permission 至少：

```text
READ
WRITE
BUILD
NETWORK
SECRET_USE
FLASH
DEBUG
HARDWARE_CONTROL
ACTUATOR_ENABLE
DELETE
PLUGIN_INSTALL
KNOWLEDGE_PROMOTE
EXPORT_PRIVATE
```

关键语义：

```text
FLASH != ACTUATOR_ENABLE
DEBUG != ACTUATOR_ENABLE
HARDWARE_CONTROL != implicit ACTUATOR_ENABLE
```

如已有 `HARDWARE_CONTROL` 逻辑，保留兼容，但 actuator enable 必须额外检查 `ACTUATOR_ENABLE`。

## 9.3 API Error Code

在原 Error Codes 基础上新增：

```text
SOURCE_REVISION_CONFLICT
DOMAIN_COMPOSITION_CONFLICT
DOMAIN_DEPENDENCY_MISSING
DOMAIN_INCOMPATIBLE

COMMISSIONING_REQUIRED
COMMISSIONING_BLOCKED
SAFETY_LIMIT_VIOLATION
TARGET_IDENTITY_MISMATCH
SAFE_STATE_FAILED
EMERGENCY_STOP_ACTIVE

RECOVERY_REQUIRED
EVENT_DELIVERY_FAILED
INDEX_REBUILD_REQUIRED
BUILD_INPUT_UNDECLARED
```

### HTTP 建议

```text
SOURCE_REVISION_CONFLICT        → 409
DOMAIN_COMPOSITION_CONFLICT     → 409
DOMAIN_DEPENDENCY_MISSING       → 422
DOMAIN_INCOMPATIBLE             → 409
COMMISSIONING_REQUIRED          → 409
COMMISSIONING_BLOCKED           → 409
SAFETY_LIMIT_VIOLATION          → 422
TARGET_IDENTITY_MISMATCH        → 409
EMERGENCY_STOP_ACTIVE           → 409
RECOVERY_REQUIRED               → 409
BUILD_INPUT_UNDECLARED          → 422
```

不要用 `400 UNKNOWN_ERROR` 替代这些确定性工程错误。

---

# 10. FIX-09 — CapabilityBroker、安全 Port 和 API 收口

## 10.1 Plugin 不得直接拿 raw Hardware Adapter

禁止给 Domain Plugin 注入：

```text
DebugProbeService raw implementation
SerialService raw implementation
CANService raw implementation
InstrumentService raw implementation
direct Flash adapter
direct actuator enable adapter
```

Domain Plugin 只能请求 capability：

```text
Domain Plugin
    ↓
CapabilityBroker / Core Application Service
    ↓
Permission
    ↓
ResourceLock
    ↓
Safety Policy / Commissioning State
    ↓
Tool Registry
    ↓
Adapter
```

## 10.2 Flash API 与 Commissioning API

旧：

```http
POST /projects/{project_id}/hardware/flash
POST /hardware/run
```

可以保留兼容，但必须映射到 Core Service。

约束：

```text
/hardware/flash
→ 只执行 flash
→ 不自动 run actuator

/hardware/run
→ 对 safety-critical target 不能绕过 commissioning
```

如果目标需要 actuator：

```text
no valid commissioning state
→ COMMISSIONING_REQUIRED
```

## 10.3 Source API

所有文件修改必须经过 Source Service。

旧 firmware direct write API 如果已经存在：

```text
route adapter only
→ SourceWorkspaceService
→ ETag/SourceRevision
→ Patch/Diff
→ Outbox SourceChanged
```

禁止保留另一套直接 filesystem write。

---

# 11. FIX-10 — Consistency Checker 不允许再靠“关键词出现”判 PASS

## 11.1 当前报告处理

当前 `CONSISTENCY_CHECK_REPORT.md` 中“全部 PASS”不再作为 V1.3.1 的架构事实。

在完成 FIX-01～FIX-09 前，状态应为：

```text
ARCHITECTURE_CANDIDATE
```

完成全部验收后才可：

```text
ARCHITECTURE_FROZEN
```

## 11.2 必须增加 Architecture Invariant Tests

至少：

```text
CORE_MUST_NOT_DEFINE_DOMAIN_IR
CORE_MUST_NOT_IMPORT_MOTOR_CONTROL

CANONICAL_UNIT_BEFORE_ENGINEERING_RULE
SOURCE_REVISION_REQUIRED_FOR_REAL_BUILD
BUILD_INPUT_SNAPSHOT_REQUIRED_FOR_REAL_BUILD

DOMAIN_COMPOSITION_REQUIRED_BEFORE_DOMAIN_ACTIVATION
DOMAIN_GENERATOR_GRAPH_MUST_BE_ACYCLIC

OUTBOX_CRITICAL_DELIVERY_REQUIRES_ACK
OUTBOX_COMPLETED_REQUIRES_ALL_REQUIRED_ACK

FLASH_MUST_NOT_IMPLY_ACTUATOR_ENABLE
SAFETY_CRITICAL_RUN_REQUIRES_COMMISSIONING
TARGET_FAILSAFE_MUST_NOT_REQUIRE_HOST_ONLINE

ACTUATOR_PERMISSION_ENUM_CONSISTENT
JOB_STATE_ENUM_CONSISTENT
API_ERROR_ENUM_CONSISTENT
```

## 11.3 建议实现方式

优先用：

```text
unit tests
schema tests
import-boundary tests
OpenAPI snapshot tests
DB enum/migration tests
crash injection tests
architecture dependency tests
```

不要为了这个功能引入新的“Architecture Checker 平台”。

---

# 12. 现有 Milestone 的精确插入关系

这是本文件最重要的施工顺序。Codex 必须按依赖关系执行，而不是机械等待 M18A–M18E。

```text
M0–M2
  ↓
M3 EngineeringValue
  └─ FIX-02 Canonical Unit foundation
  ↓
M4 Device
  ↓
M5 Sandbox
  ↓
M6 Requirement
  ↓
M7 Pin + Rule
  [必须已经完成 FIX-02]
  ↓
M8 Hardware
  ↓
M9 Circuit Rule
  [必须已经完成 FIX-02]
  ↓
M10 Schematic
  ↓
M11 MCUConfig
  ↓
FIX-03 SourceRevision + BuildInputSnapshot foundation
  ↓
M12 Firmware + Generator + Real Build
  ↓
M13 Static Analysis
  ↓
M14 Domain Extension
  └─ FIX-04 Domain Composition 完整并入 M14
  ↓
M15 MotorControl
  [必须已经完成 FIX-01 / FIX-04]
  ↓
M16 Protocol
  ↓
M17 Test / Review
  ↓
FIX-05 Durable Outbox/Recovery
  [如早期 Artifact/Event 已实现，立即 retrofit，不等待这里]
  ↓
M18 Impact Graph
  [Impact consumer 必须使用 FIX-05 durable delivery]
  ↓
FIX-06 Hardware three-layer fail-safe contract
FIX-07 minimum hardware adapter for M19B
FIX-08 enum/error sync
FIX-09 broker/API close-out
  ↓
M19A FOC Software Gate
  ↓
M19B FOC Commissioning Gate
  ↓
M20 Core Neutrality
  ↓
后续 M21–M36
```

### 对“已经实施超过此位置”的处理

例如 Codex 已经做到 M12：

```text
不要回退到 M3
→ 给 EngineeringValue 做 migration
→ 修改 M7/M9 Rules 使用 normalized value
→ 给 M12 BuildRun 补 SourceRevision/BuildInputSnapshot
→ regression
→ 继续
```

例如已做到 M15：

```text
不要删除 MotorControl
→ 检查 MotorControl 是否错误进入 core/
→ 若是，移动/抽离为 plugin，保留兼容 migration
→ 把 DomainComposition 补进 M14 infrastructure
→ MotorControl 通过 Registry 激活
→ regression
```

---

# 13. 数据库 Migration 要求

如果相应表已经存在，只做 migration，不 drop/recreate 用户数据。

最低新增/调整：

```text
source_revisions
build_input_snapshots
patch_proposals

domain_activations

outbox_events
event_deliveries
processed_events
side_effect_journal

commissioning_sessions
commissioning_step_results
safety_limits
emergency_stop_events
target_safety_capabilities
```

约束：

```text
UNIQUE(event_deliveries.event_id, event_deliveries.consumer_id)
```

已有：

```text
outbox.status = SENT
```

迁移原则：

```text
旧 SENT 不能直接推断 COMPLETED。
```

升级 migration 时：

- 若可以证明所有 required consumer 已处理 → `COMPLETED`
- 无法证明 → `PENDING/RECOVERY_REQUIRED`
- 不允许静默认为完成

---

# 14. API / OpenAPI / Frontend 同步规则

任何 Core Enum / Error / Resource 一旦修改，必须同一个 FIX 内同步：

```text
Python enum/Pydantic
→ DB schema/migration
→ FastAPI OpenAPI
→ generated TypeScript SDK
→ Frontend state handling
→ tests
```

禁止出现：

```text
Backend 有 RECOVERING
Frontend 不认识

Security 有 ACTUATOR_ENABLE
Permission enum 没有

API 返回 COMMISSIONING_BLOCKED
SDK 仍只定义 generic error
```

---

# 15. Codex 最终提交要求

不要提交一个巨型“全部重构” commit。

建议按 FIX 独立 commit，例如：

```text
fix(core): remove motor-control definitions from core boundary
fix(units): make canonical engineering values foundational
fix(source): bind real builds to build input snapshots
fix(domains): make domain composition part of M14
fix(events): add durable consumer delivery acknowledgements
fix(safety): add target-local fail-safe contract
fix(foc-gate): split software and commissioning gates
fix(api): synchronize job permission and engineering errors
fix(broker): enforce hardware capability broker path
test(architecture): add architecture invariant checks
```

如果当前仓库已有自己的 commit convention，遵守现有 convention；关键是保持改动可审查、可回滚。

---

# 16. 禁止 Codex 自行扩大范围

本次修正**明确不做**：

```text
不重写 UI 设计
不重做 ELKB
不替换 FastAPI
不替换 Tauri
不替换 SQLAlchemy
不引入 Kafka/NATS
不引入 Graph DB
不改变 Qdrant 定位
不改变 ERIS/OSDLE 总体设计
不重写所有 Milestone 编号
不增加新的 FOC 算法需求
不改变 MotorControl 已冻结的 MCUConfigIR SSOT 原则
不重新讨论 EEA 是否做成网站/桌面端
```

目标只是：

```text
消除已发现架构矛盾
+
把基础能力放到第一次使用之前
+
补齐可靠事件投递
+
补齐真实硬件 fail-safe
+
保证已经开始的实现可以平滑迁移
```

---

# 17. V1.3.1 最终验收清单

只有全部满足才允许把 Architecture 状态改为 `FROZEN`：

| ID | Hard Gate |
|---|---|
| A01 | Core 不定义/不 import MotorControl |
| A02 | Canonical Unit 在 Pin/Electrical Rule 中统一使用 |
| A03 | Real Build 必须绑定 SourceRevision + BuildInputSnapshot |
| A04 | M15 前 Domain Composition 已完成 |
| A05 | Critical Outbox consumer 有 durable per-consumer ACK |
| A06 | Crash/replay 不丢 critical event、不重复 side effect |
| A07 | Safety-critical target 具备可验证的 local fail-safe contract |
| A08 | Host crash/command timeout 不会无限保持旧执行器命令 |
| A09 | Flash 与 ACTUATOR_ENABLE 权限完全分离 |
| A10 | M19A Software Gate 与 M19B Commissioning Gate 分离 |
| A11 | M19B 不能被纯 Mock 冒充 |
| A12 | JobStatus/API/DB/Frontend enum 一致 |
| A13 | Engineering Error Code 在 OpenAPI/SDK 中一致 |
| A14 | Plugin 不能绕过 CapabilityBroker 直接操作硬件 |
| A15 | SafetyLimit 使用 EngineeringValue + 层级约束 |
| A16 | Consistency Report 由 invariant/tests 支撑，不靠文字匹配 |
| A17 | Existing Project / ELKB / Core Neutrality 原有能力无回归 |
| A18 | 所有 migration 可在现有开发数据库上执行，不丢用户数据 |

---

# 18. 给 Codex 的最终执行指令

**现在不要重新生成 EEA 项目。**

执行：

```text
1. Inspect current implementation state.
2. Map current code to FIX-01 … FIX-10.
3. Mark each FIX: DONE / PARTIAL / NOT_STARTED.
4. Apply only missing changes in the exact order defined here.
5. Preserve already-correct code and public API compatibility where possible.
6. Add migrations instead of recreating existing databases.
7. Add architecture invariants and regression tests.
8. Do not mark a hard gate PASS if it is skipped, mocked, or unverified.
9. After all FIX tasks pass, update documentation to V1.3.1 Final Architecture Freeze.
10. Continue the original M0–M36 implementation plan from the current milestone.
```

如果现有实现和本文件存在无法同时满足的真实技术冲突：

```text
STOP only that FIX
→ write a concrete conflict report:
   - current file/symbol
   - current behavior
   - conflicting requirement
   - minimal migration options
   - affected tests/data/API
→ do not invent a third architecture
```

**本修正文档不是新的 EEA 方案，而是 EEA V1.3 的精确增量补丁。**
