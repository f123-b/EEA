# Embedded Engineering Agent
## Domain Composition & Multi-Domain Contract Specification V1.3

# 1. 目的

EEA Project 可以激活 0..N Domain Plugin。V1.3 正式定义多个 Domain 同时存在时的依赖、冲突、规则、生成器、UI、Migration 与执行顺序，避免 MotorControl 单插件场景掩盖组合问题。

# 2. DomainActivation

字段至少：

- project_id
- domain_id
- plugin_id / plugin_version
- domain_schema_version
- status: ACTIVE/DISABLED/INCOMPATIBLE/BLOCKED
- configuration
- activated_at / activated_by
- capability_snapshot
- dependency_snapshot

# 3. DomainDescriptor 扩展

至少增加：

- requires_domains
- optional_domains
- conflicts_with
- provided_capabilities
- required_capabilities
- priority
- rule_phases
- generator_phases
- migration_provider
- context_contributions
- ui_contributions

# 4. Composition Resolution

激活前：

```text
Manifest Validation
→ Plugin API Compatibility
→ Required Domain Resolution
→ Capability Resolution
→ Conflict Detection
→ Schema Compatibility
→ Rule/Generator Phase Ordering
→ Migration Check
→ Activation Plan
→ User/Policy Approval
→ Activate
```

存在不可解冲突必须 BLOCKED，禁止“最后加载者覆盖”。

# 5. Capability Routing

Capability 由 Registry 路由，调用者不得写死具体 Domain。若多个 provider 提供同 capability：

- explicit project selection
- deterministic priority
- compatibility policy
- conflict error

禁止依赖 Python import 顺序。

# 6. Rule Ordering

统一 phase：

`PRE_SCHEMA → PRE_DESIGN → PRE_GENERATION → POST_GENERATION → PRE_EXECUTION → POST_EXECUTION → RELEASE_GATE`

Domain Rule 注册 stable rule id/version/phase/inputs/severity/authority。Core safety rule 优先级不可被 Domain 降级。

# 7. Generator Ordering

Generator 声明：

- consumes
- produces
- requires_capabilities
- before/after constraints
- deterministic version
- side effects

Registry 构建 DAG；cycle 必须拒绝激活或生成。

# 8. Cross-domain Dependency

跨 Domain 使用 `DomainIRRef`、Core IR ref、Engineering Dependency Edge，不直接访问另一插件内部表或 Python class。

例：

```text
MotorControlIR
→ requires deterministic cyclic transport
→ EtherCATDomain capability
→ Protocol/MCUConfig/Firmware dependency
```

# 9. Database Namespace

Plugin 表必须 namespace；Domain 数据有 project/domain/version ownership。禁用插件后数据不删除，状态变为 inactive；重新启用需 compatibility/migration。

# 10. UI

Frontend 只基于 `/projects/{id}/domains` 与 `/ui/extensions` 构造页面。

UI contribution 仅声明 metadata/action/form/schema，不注入任意 remote JS。

# 11. API

正式 Core API：

```http
GET  /projects/{project_id}/domains
GET  /projects/{project_id}/domains/available
POST /projects/{project_id}/domains/{domain_id}/activate
POST /projects/{project_id}/domains/{domain_id}/deactivate
GET  /projects/{project_id}/domains/{domain_id}/state
GET  /projects/{project_id}/domains/{domain_id}/schema
POST /projects/{project_id}/domains/{domain_id}/validate
GET  /projects/{project_id}/domains/{domain_id}/artifacts
POST /projects/{project_id}/domains/resolve-composition
```

固定 `/motor-control` 仅作为 builtin compatibility alias。

# 12. Migration

升级 Core/Plugin 时先计算 Domain Migration Plan。任何 schema/plugin API 不兼容导致 project BLOCKED_UPGRADE，不静默丢数据。

# 13. Benchmark

至少：

- 0 Domain：普通 MCU 项目
- 1 Domain：MotorControl
- 2 Domain：MotorControl + EtherCAT/mock deterministic transport
- 3 Domain：MotorControl + Transport + Robotics/ROS2-facing mock
- conflict case
- missing dependency case
- generator cycle case
- plugin disable/enable migration case
