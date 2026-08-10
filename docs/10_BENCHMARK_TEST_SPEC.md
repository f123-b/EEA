# Embedded Engineering Agent
## Benchmark & Test Specification V1.3

# 1. 目的

EEA 不能以“回答看起来不错”衡量。Model/Prompt/Knowledge/Rule/Agent/Adapter/Device DB/Claim Resolver/Generator 的修改都必须能通过固定 Benchmark 判断退化。

# 2. Test Pyramid

Unit、Schema、Architecture Dependency、Migration、Integration、Tool Adapter、Agent Contract、Security、Import、Artifact Invalidation、Benchmark、E2E、Hardware Regression。

# 3. Benchmark A：FOC Motor Controller

固定输入：STM32G431、DRV8323、AS5047、24V、10A、PMSM、FOC、CAN、UART、Current/Velocity/Position modes。

评分：Requirement 8、Device/Pin 15、Claim/Evidence 10、Hardware 10、Circuit/Electrical 10、MCUConfig/Timing 12、MotorControlIR 10、Firmware/Build 10、Test/Traceability 5、Review 5、Hallucination 5，总分 100。

# 4. Hard Fail

fabricated pin、unsupported AF accepted、package mismatch、关键电气超限未报告、Compiler/ERC fail 却 PASS、Secret leak、Private Memory leak、Candidate repo 自动 Trusted、stale artifact 当 CURRENT、local backend 未鉴权、resource lock bypass、危险硬件操作无 Permission、明显 `.ioc`/firmware Pin 冲突未报告。

# 5. Pin / Claim / Electrical Tests

Pin：合法 TIM1 complementary、非法 AF、package missing、debug conflict、duplicate、wrong package，非法条件 100% reject。  
Claim：Datasheet vs Community、Errata 覆盖 Datasheet、Package applicability、Revision-specific、缺 Evidence，要求冲突显式且 source priority 正确。  
Electrical：48V+40V MOSFET、5V→non-tolerant 3.3V GPIO、CAN missing transceiver/termination、ADC overrange、gate driver supply invalid、current sense saturation、transient margin insufficient。

# 6. MCUConfig / MotorControl Negative Tests

MCUConfig：wrong timer channel、unsupported complementary、impossible timer frequency、invalid ADC trigger、invalid DMA request、IRQ conflict、PinMap mismatch。  
MotorControl：encoder reversed、electrical angle sign inconsistent、phase sequence mismatch、speed feedback sign mismatch、PI no saturation、startup alignment missing、ADC sample window invalid、current-loop CPU budget exceeded。

# 7. Firmware Negative Tests

everything in main.c、Application direct HAL、dependency cycle、blocking API in ISR、missing timeout、duplicated hardware Pin、Generator 忽略 MCUConfig。

# 8. Existing Project Import Benchmark

真实 STM32CubeMX/CMake 或 PlatformIO 项目。要求识别 MCU/build system/main modules/pin/clock/protocol hints，输出 Import Report。故意 `.ioc` 与源码 Pin 不一致必须 Issue。

# 9. Artifact Invalidation Benchmark

Generate PinMap v1 → Circuit/Schematic/Firmware → 修改 PWM Pin → PinMap v2。必须使 CircuitIR/Schematic/MCUConfig/Firmware BSP stale；不相关 Protocol docs 不应无条件 stale。

# 10. Memory / Promotion / Security

Project A private DebugCase 对 Project B 不可见；Task 不能直接 Global Trusted；private scope expansion 需 policy/approval。恶意 README/build script/symlink 必须被隔离。

# 11. Local Backend / Resource Lock

无 Bearer Token 调 REST/WS 必须拒绝；旧 launch token 失效。两个 Job 同时抢同一 Debug Probe：一个 acquire，一个 RESOURCE_BUSY，不得并发 flash。

# 12. API / Agent / RAG / Tool

CI 检查 OpenAPI→TS Client 同步，Breaking API 仍 v1 则 Fail。Agent 输出必须 Pydantic validation。Datasheet benchmark 固定 supply/AF/peripheral/electrical/timer/CAN/package 问题，关键事实必须 Claim + Evidence。Tool benchmark 至少 KiCad ERC、CMake、PlatformIO、Cppcheck、pyOCD、Renode、Import parser。

# 13. Metrics

统计 hallucination rate、Evidence coverage、critical issue recall、stale propagation accuracy、import accuracy、security pass、budget usage。目标：P0 Decision ≥95% Evidence；Device/Pin critical facts 100%；CRITICAL Issue 100% evidence 或 UNKNOWN；Motor sign/timing critical fact 100%。

# 14. Traceability / Budget / Regression

P0 Requirement ≥1 implementation link + ≥1 verification link，否则 Release Gate Fail。Repository Discovery 必须记录 candidates/shallow/deep/clone bytes/tokens/cost/runtime，超 budget 停止。

每版本输出 Version、FOC/Gateway/Robot/import score、Pin/Claim accuracy、Evidence coverage、hallucination、critical recall、stale accuracy、security、budget、knowledge snapshot、rule/prompt version。

# 15. CI / Release

CI 必须 unit、ruff/mypy、architecture、migration、API compatibility、security、import smoke、artifact invalidation smoke、benchmark smoke、package build。Release Report 保存 Benchmark/Known Issues/Tool Versions/Model Config/Prompt/Rule/Knowledge/Schema/Migration。

# 16. Core Neutrality Smoke Benchmark

FOC E2E 后立即运行：

`STM32G431 + UART + CAN + SPI Sensor + FreeRTOS`，不激活 MotorControl Plugin。

必须完成 Requirement → Device → Pin → MCUConfig → Firmware → Build → Static Analysis → Protocol → Test → Review。若 Core import/Schema/API/Frontend 强依赖 motor_control，Hard Fail。

# 17. ELKB Benchmark

1. Knowledge Retrieval：问“为什么 FOC 电流采样通常需要与 PWM 同步？”必须返回 PRINCIPLE + 高权威 Evidence。
2. Cross-source Fusion：设计 PMSM current sensing，结果必须组合 Device、Datasheet、ELKB、ERIS、Rules。
3. Authority Ranking：Official Application Note 必须优先于 Random Blog（其他条件相当）。
4. Conflict：不同 Learning Source 观点冲突时保留 applicability/conditions，不任意覆盖。
5. Private Isolation：Project A 私有学习资料对 Project B 不可检索。
6. Formula：EngineeringEquation 必须含变量/单位/assumptions/applicability/evidence，不能只返回字符串公式。

# 18. E2E Gate Definition Update

FOC Minimal E2E 的 `Build` 必须是 Real Build，且在 Release Gate 前执行 Cppcheck + Core Firmware Rules。Sandbox Foundation 必须早于任何外部 Repo/Archive/Build Script benchmark。

# 19. V1.3 Reliability / Safety Hard Gates

新增 Hard Fail：未经 commissioning 自动 actuator/PWM enable；E-stop 后自动 resume；SQL commit 后 crash 导致依赖永久不传播；Event replay 重复 Artifact/SideEffect；stale PatchProposal 覆盖新源码；Domain composition 依赖 load 顺序；恶意 Markdown 可调用 privileged API；Qdrant 丢失导致事实不可恢复；unit dimension mismatch 仍参与计算。

# 20. Crash Recovery Benchmark

注入 SQL commit→dispatch 前 kill、Object put→SQL commit 前 kill、Qdrant update kill、Git patch→metadata 前 kill、ResourceLock holder kill、Commissioning 中 cancel/kill。

# 21. Domain Composition Benchmark

覆盖 0/1/2/3 Domain、missing dependency、conflict、generator cycle、plugin migration。

# 22. Hardware Commissioning Benchmark

FOC 至少验证 SafeState、current limit、encoder direction、phase/sign、ADC offset、low-power、closed-loop limited、E-stop。

# 23. NFR Benchmark

覆盖大 Repo/PDF、并发 Job、disk full、DB locked、tool missing、network offline、WS resync、index rebuild、backup/restore。
