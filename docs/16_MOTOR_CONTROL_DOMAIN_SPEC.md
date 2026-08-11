# Embedded Engineering Agent
## Motor Control Built-in Domain Plugin Specification V1.3

# 1. 定位

MotorControl 是 EEA 首个高价值 **Built-in Domain Plugin**。FOC Motor Controller 是第一个 Reference Benchmark。MotorControl 不属于 Core Domain，不能成为所有 Project 的必经步骤。

# 2. 目录与依赖

```text
plugins/builtin/motor_control/
├── domain/
├── schemas/
├── rules/
├── agents/
├── generators/
├── knowledge/
├── ui/
└── benchmarks/
```

依赖方向：`MotorControl Plugin → Core public services/IR`。Core 禁止反向 import MotorControl。

# 3. MotorControlIR

M15R 冻结的 `MotorControlIR` schema version 是 `1.0.0`。Schema 中的控制需求不替代
`MCUConfigIR` 的已实现硬件事实；所有 `EngineeringValue` 必须携带与字段语义一致的
dimension，量纲不一致时必须 fail closed。

```text
MotorControlIR
├── motor_ref / motor_parameters
├── inverter_ref
├── encoder_ref
├── current_sense_ref
├── pwm_requirement
├── adc_sampling_requirement
├── mcu_config_refs
├── electrical_angle
├── sign_convention
├── startup
├── current_loop
├── velocity_loop
├── position_loop
├── limits
└── fault_policy
```

# 4. Single Source of Truth

**MCUConfigIR 是 MCU 硬件配置唯一事实源（Single Source of Truth）。**

实际 MCU 配置只在 MCUConfigIR：

- timer / channel / complementary channel
- center-aligned mode
- realized switching frequency
- realized deadtime
- ADC instance/channel/trigger
- DMA request
- IRQ priority

MotorControlIR 只保存“控制需求、目标值、允许范围、控制语义、引用”。

例如：

```text
MotorControlIR.pwm_requirement.target_frequency = 20 kHz
MotorControlIR.pwm_requirement.center_aligned_required = true
MotorControlIR.mcu_config_refs.pwm = MCUConfigIR.peripherals[TIM1]

MCUConfigIR.PWMConfig.timer = TIM1
MCUConfigIR.PWMConfig.realized_frequency = 20 kHz
```

Rule 检查 requirement ↔ realized config 是否一致。

# 5. Hardware References

Inverter、Encoder、CurrentSense 尽量通过 HardwareIR DeviceInstance/Module 引用；Domain IR 可保存 motor-specific semantics（phase mapping、sign、offset、latency），不重复器件 MPN、电气 rating 等 Hardware Fact。

# 6. Electrical Angle / Sign Convention

显式建模 mechanical direction、electrical angle direction、phase order、positive torque current、speed feedback sign、Park convention、SVPWM phase mapping、zero offset。任何隐式 sign 都视为 Review 风险。

# 7. Loops

`LoopRequirement` 的 `frequency` 是 `FREQUENCY`，`period` 是 `TIME`；二者是互补的
控制语义，不允许用错误量纲互相替代。`latency` 与 `cpu_budget` 也是 `TIME`。

- `CurrentLoopRequirement`：`id_target`、`iq_target` 必须是 `CURRENT`；`frequency`、
  `period`、`latency`、`cpu_budget` 继承上述 loop 语义；`kp`、`ki`、`output_limit`、
  `anti_windup` 和 `decoupling` 是可选控制器需求字段。
- `VelocityLoopRequirement`：`speed_limit` 是 `ANGULAR_VELOCITY`，
  `acceleration_limit` 是 `ANGULAR_ACCELERATION`，`current_limit` 是 `CURRENT`，
  `feedback_source` 必须显式声明来源。
- `PositionLoopRequirement`：`controller` 与 `wrap_handling` 必须显式声明；
  `position_limit` 是 `ANGLE`，`velocity_limit` 是 `ANGULAR_VELOCITY`。

缺少运行时执行预算、反馈极性或规范化 phase-map 证据时，相关规则返回 `UNKNOWN` 或
`BLOCKED`，不能降级为 `PASS`。

# 8. Startup / Calibration

encoder alignment、electrical zero、current sensor offset、cogging calibration(optional)、open-loop ramp(optional)。每步保存 prerequisites、current/voltage limit、timeout、failure behavior、test result。`StartupCalibration.test_result` 只允许 `PASS`、`FAIL`、`UNKNOWN`、`BLOCKED`；M15R 不执行硬件校准，声明的 `PASS` 不等于真实硬件测试通过。

# 9. Fault Policy

overcurrent、bus over/undervoltage、driver fault、encoder loss、overspeed、stall、current-sense invalid、control overrun。Action：disable PWM/safe state/retry/latched/log/evidence。

# 10. Rules

COMPLEMENTARY_PWM、DEADTIME_REQUIRED、CURRENT_SENSE_ADC_RANGE、ADC_TRIGGER_ALIGNMENT、CURRENT_LOOP_TIMING_BUDGET、SIGN_CONVENTION_COMPLETE、SPEED_FEEDBACK_SIGN_CONSISTENT、ELECTRICAL_ANGLE_DIRECTION_CONSISTENT、PI_OUTPUT_SATURATION_LIMIT、STARTUP_ALIGNMENT_REQUIRED、MOTOR_REQUIREMENT_MCUCONFIG_MISMATCH。

# 11. ELKB / ERIS / Debug

MotorControlAgent 查询：
- ELKB：FOC theory、current sampling、bandwidth、SVPWM、encoder/control principles；
- ERIS：VESC/ODrive/SimpleFOC 的真实实现；
- Project Experience：本项目历史故障；
- Device/Claims：MCU/encoder/driver facts；
- Rules：确定性限制。

速度反向高速：encoder raw direction → mechanical speed sign → electrical angle sign → phase order → Park/SVPWM convention → speed error sign → PI saturation → current direction。  
低速抖动：encoder quantization、current offset、minimum pulse、deadtime distortion、friction/cogging、angle latency、current loop noise、speed estimator、loop-rate ratio。

# 12. Acceptance

M15/M15R 只验收 MotorControl Plugin Contract：

1. Plugin disable 后 Core Neutrality benchmark 仍 PASS。
2. Plugin enable 后 Domain Validate action 实际执行 executable validator。
3. 修改 MCUConfig PWM/ADC 时 MotorControl cross-validation 能检测 mismatch；未知或
   阻断状态不得转成 PASS。
4. 11 条冻结规则均有 deterministic evaluator，或明确返回 `UNKNOWN`/`BLOCKED`。
5. Core/Application 不出现 motor-only schema import；API/OpenAPI/TypeScript contract
   保持同步。
6. API 可通过 Domain Registry 暴露 Motor Control metadata contribution。

Plugin-enabled FOC Minimal E2E 属于 M19；完整 Desktop UI Vertical Slice 属于 M21。
二者不是 M15/M15R 的验收项，不能在 M15 报告中标记为已完成。

# 13. V1.3 Commissioning Safety

MotorControl 必须贡献 current offset/polarity、encoder direction/zero/wrap、phase sequence/electrical-angle sign、PWM polarity/deadtime/break、ADC sample window、gate-driver fault、bus voltage/current、loop saturation 等 Commissioning Preflight。

Production loop enable 只能通过 Core HardwareCommissioningService。sign convention 不确定时状态 UNKNOWN/BLOCKED，禁止“高速试转确认”。
