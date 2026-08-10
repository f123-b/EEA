# Embedded Engineering Agent
## Existing Project Import & Reverse Engineering Specification V1.3

# 1. 目标

Existing Project Import 是 V1.3 核心能力。用户真实场景往往是分析、修 Bug、改 Pin、升级 MCU、做协议、Review 现有项目，而不是只从空目录生成。

# 2. 输入

V1.3 最少支持 Local folder、Git repository、ZIP/TAR、CMake、Makefile、PlatformIO、STM32CubeMX `.ioc`、STM32CubeIDE project、KiCad project、raw C/C++ source。后续扩 Keil/IAR/Zephyr/Yocto/Buildroot。

# 3. Pipeline

```text
Source
→ Safe Materialization
→ File Inventory
→ Build System Detection
→ Toolchain Detection
→ MCU/Board Detection
→ Config Parser
→ Source/Symbol Scan
→ Dependency
→ Pin/Clock/Peripheral Facts
→ Protocol Hints
→ Claim Extraction
→ IR Candidate Generation
→ Build(optional)
→ Static Analysis
→ Consistency Review
→ Import Report
```

# 4. 安全与只读

导入阶段 read-only、no silent rewrite、no auto cleanup。外部 archive/repo 做 path/symlink safety 和 sandbox；Build 默认需策略允许。

# 5. CubeMX `.ioc`

优先提取 MCU/Package、Pin assignment、Clock tree、TIM/PWM、ADC、DMA、NVIC、UART、CAN/FDCAN、SPI/I2C，转为 Claims + PinMap candidate + MCUConfigIR candidate。

# 6. Build / MCU Detection

识别 CMakeLists.txt、platformio.ini、Makefile、CubeIDE metadata、compile_commands.json、linker script、startup file。

MCU 证据优先级：explicit config(.ioc/board) > compiler defines > linker/startup > CMSIS header > build flags > filename inference。冲突生成 ClaimConflict。

# 7. Firmware Reverse Engineering

提取 modules/public APIs/interrupt handlers/RTOS tasks/HAL-LL calls/global state/peripheral init/pin macros/protocol handlers，形成 FirmwareIR + MCUConfigIR candidate + Issues。

# 8. Hardware Reverse Engineering

KiCad 提取 symbols/nets/MCU pins/power/interfaces/connectors/transceiver/gate driver，形成 CircuitIR candidate。

# 9. Cross-source Consistency

必须检查 `.ioc` pin vs source、schematic pin vs firmware、MCU package vs Device DB、clock config vs bitrate/timer、protocol docs vs source IDs。

# 10. Import Report

包含 Detected Project Type/MCU/Board/Build/Toolchain/Peripherals/Protocols/Hardware Files/Claim Count/IR Candidates/Build Result/Static Analysis/Conflicts/Critical Issues/Unknowns/Recommended Next Actions。

# 11. Evidence / Merge

Imported Fact 保存 file path/line/symbol/parser-tool version/content hash，可标 IMPORT_VERIFIED，但不自动等价于 Datasheet Verified。

Imported candidate 与 current IR 使用 compare/merge/accept imported/keep current/manual resolve，禁止 silent overwrite。

# 12. Acceptance

FOC Existing Project Import Benchmark：MCU detected、`.ioc` Pin extracted、build system detected、firmware module summary；故意 `.ioc` vs source pin mismatch → HIGH Issue。

# 13. V1.3 Sandbox Precondition

Safe Materialization/Sandbox Foundation 是 Import 的硬前置依赖。Archive extraction、Git checkout、Build/Configure Script 不得直接在宿主工作区无隔离执行。只读扫描也必须做 path/symlink/size safety。

Import 输出的 motor-control hints 只能形成 Domain IR Candidate；只有项目激活 MotorControl Plugin 后才解析成 MotorControlIR。

# 14. V1.3 SourceRevision Import

Import 完成后必须创建初始 SourceRevision/tree hash；Imported facts/IR candidate/Build 绑定该 revision。后续用户代码变化不能让旧 Import Report 继续冒充当前状态。
