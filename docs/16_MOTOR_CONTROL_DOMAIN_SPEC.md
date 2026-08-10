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

CurrentLoop：frequency/period、Id/Iq target、Kp/Ki、output limit、anti-windup、decoupling、sample-to-actuation latency、CPU budget。  
VelocityLoop：frequency、Kp/Ki、speed/acceleration/current limit、feedback source。  
PositionLoop：frequency、controller type、position/velocity limit、wrap handling。

# 8. Startup / Calibration

encoder alignment、electrical zero、current sensor offset、cogging calibration(optional)、open-loop ramp(optional)。每步保存 prerequisites、current/voltage limit、timeout、failure behavior、test result。

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

1. Plugin disable 后 Core Neutrality benchmark 仍 PASS。
2. Plugin enable 后 FOC E2E PASS。
3. 修改 MCUConfig PWM/ADC 时 MotorControl cross-validation 能检测 mismatch。
4. Core repo 不出现 motor-only schema import。
5. API/Frontend 通过 Domain Registry 动态出现 Motor Control 页面。

# 13. V1.3 Commissioning Safety

MotorControl 必须贡献 current offset/polarity、encoder direction/zero/wrap、phase sequence/electrical-angle sign、PWM polarity/deadtime/break、ADC sample window、gate-driver fault、bus voltage/current、loop saturation 等 Commissioning Preflight。

Production loop enable 只能通过 Core HardwareCommissioningService。sign convention 不确定时状态 UNKNOWN/BLOCKED，禁止“高速试转确认”。
