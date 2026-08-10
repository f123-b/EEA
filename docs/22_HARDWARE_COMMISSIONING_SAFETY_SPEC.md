# Embedded Engineering Agent
## Hardware Commissioning & Safety Specification V1.3

# 1. 目的

EEA 可以生成、修改、烧录并调试真实嵌入式硬件，因此“Build 成功”不等于“允许直接运行”。本规范定义从 Firmware Artifact 到真实硬件运行之间的安全执行层，尤其覆盖 FOC、电源、执行器、机器人关节等可能造成高速运动、过流、过压或机械损伤的场景。

核心原则：**Safe-by-default、PWM/Actuator 默认关闭、分阶段使能、硬限制优先于 AI 判断、每一步都有 Evidence 与可回滚状态。**

# 2. HardwareCommissioningSession

至少包含：

- project_id / target_id / firmware_artifact_id / firmware_hash
- hardware_identity / probe_identity / board_revision
- commissioning_profile_id
- state / current_step / started_by / approved_by
- safety_limits_snapshot
- preflight_results / step_results / evidence_ids
- emergency_stop_state / watchdog_state
- resource_lock_ids / permission_token_ids
- created_at / completed_at / aborted_at

状态：

`CREATED → PREFLIGHT → FLASHED_SAFE → SENSOR_CHECK → LOW_POWER → CLOSED_LOOP_LIMITED → USER_APPROVAL → NORMAL_OPERATION`

异常状态：

`BLOCKED / ABORTED / EMERGENCY_STOP / FAULTED / ROLLBACK_REQUIRED`

# 3. Safety Limit

SafetyLimit 必须结构化，至少支持：

- max_bus_voltage
- max_phase_current
- max_iq / max_id
- max_speed
- max_position_delta
- max_duty_cycle
- max_pwm_enable_duration
- max_temperature
- max_test_runtime
- watchdog_timeout
- current_ramp_rate
- speed_ramp_rate
- safe_brake_policy
- safe_output_state

任何 Agent/Plugin 只能请求更保守限制；扩大硬限制需要明确审批。

# 4. Commissioning Pipeline

```text
Build
→ Static Analysis
→ Rule / Safety Pre-check
→ Permission + Resource Lock
→ Target Identity Verification
→ Flash
→ Reset
→ SAFE OUTPUT STATE (PWM/Actuator Disabled)
→ Sensor Sanity Check
→ ADC/Current Offset Calibration
→ Encoder/Direction/Range Check
→ Gate Driver/Fault Input Check
→ Low-power/Open-loop Test
→ Phase/Sign Convention Verification
→ Current-loop Limited Test
→ Velocity/Position Limited Test
→ User Approval
→ Normal Operation
```

不满足任一步，后续步骤禁止自动继续。

# 5. Motor Control 专项 Gate

MotorControl Plugin 至少检查：

- encoder direction / zero / wrap / plausibility
- electrical-angle sign
- phase sequence
- current-sense polarity and channel mapping
- ADC sampling window
- PWM polarity / complementary output / deadtime / break input
- speed feedback sign
- current/speed/position PI saturation
- startup alignment strategy
- current offset
- bus voltage
- gate-driver fault status
- emergency stop / watchdog

第一次闭环运行必须使用 Commissioning Profile，而不是 Production Profile。

# 6. Safe Output State

每个 HardwareTarget 必须声明 SafeState，例如：

- PWM outputs disabled or break asserted
- MOSFET gate-enable low
- motor torque command = 0
- relay/contactor open
- heater/output disabled
- robot brake policy defined
- GPIO outputs set to safe level

系统崩溃、Agent cancel、heartbeat loss、resource-lock loss、tool timeout 时必须进入或尝试进入 SafeState，并记录结果。

# 7. Emergency Stop

EmergencyStop 可由：

- 用户
- Hardware fault input
- Watchdog
- Rule Engine
- Safety monitor
- Tool Adapter
- Agent Runtime policy

触发。触发后：

`stop command → disable actuator/PWM → preserve logs/evidence → release or quarantine resource → mark session EMERGENCY_STOP`

禁止自动恢复到 NORMAL_OPERATION。

# 8. Permission / Lock

FLASH、DEBUG、HARDWARE_CONTROL、ACTUATOR_ENABLE 分离。真正使能执行器必须具备：

- valid permission
- valid target identity
- valid ResourceLock
- safety profile
- preflight PASS
- limits snapshot
- explicit user approval when policy requires

# 9. Evidence

每一步保存：

- measured values
- thresholds
- raw tool result / waveform reference
- firmware hash
- target identity
- rule version
- tool version
- operator/agent
- timestamp

# 10. API

核心资源：

- CommissioningProfile
- HardwareCommissioningSession
- CommissioningStepResult
- SafetyLimit
- EmergencyStopEvent

API 由 Core 提供，Domain Plugin 可贡献 domain-specific preflight/step/rule，但不能绕过 Core safety state machine。

# 11. Acceptance

Hard Fail：

- Flash 后直接自动 PWM enable
- 无 target identity 执行 actuator enable
- 无 safety limit snapshot
- encoder/sign 未验证直接高速度闭环
- current limit 未设置直接运行
- emergency stop 后自动 resume
- crash/cancel 后输出状态未知却标 SUCCESS
- Safety Rule 被 Agent 文本判断覆盖

FOC Benchmark 必须加入真实或 Hardware-in-the-loop commissioning gate。
