# EEA V1.2 Documentation Changelog

## Architecture Freeze Changes

- MotorControl 从 Core Domain 迁移为 Built-in Domain Plugin。
- Core Workflow 支持 0..N Active Domain IRs。
- AIProvider Foundation 前移，Full Agent Runtime 后移。
- Sandbox Foundation 前移至所有外部执行之前。
- Static Analysis/Firmware Rules 前移至 FOC E2E Gate。
- MCUConfigIR / MotorControlIR 重复事实源被消除。
- Artifact Dependency 升级为 Engineering Dependency & Impact Graph。
- 新增 ClaimPredicateRegistry。
- 新增 Core Neutrality Smoke Benchmark。
- Plugin 增加 Trust Tier / Out-of-Process policy。
- 新增 ELKB 一级知识系统及 LearningKnowledge/EngineeringEquation/Authority/Relations。
- Technical Knowledge Discovery 合并进统一 Discovery Provider 架构。
- API/Frontend/Codex Phase/Release Gate 同步升级。
