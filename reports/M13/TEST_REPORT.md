# M13 Test Report

## Scope

本阶段实现 FirmwareStaticAnalysis Core contract、StaticAnalysisProvider Port、无 shell/无网络
Cppcheck Adapter、四条 Firmware RELEASE_GATE 规则、SQLAlchemy 持久化、Alembic `0016` 迁移与
项目级静态分析 API。

## Rule coverage

- `APP_DIRECT_HAL_CALL`：应用拥有的 C/C++ 源文件扫描，生成适配器/组件目录排除。
- `ISR_BLOCKING_API`：声明及源码 ISR 解析，阻塞 API 命中、缺失 handler 和无适用 ISR 分支。
- `DRIVER_DEPENDENCY_CYCLE`：稳定排序 DFS、环路、缺失依赖和空图 UNKNOWN。
- `MCUCONFIG_FIRMWARE_MISMATCH`：FirmwareIR 与 MCUConfigIR 的 ID/Revision 绑定校验。
- Cppcheck：执行文件缺失、执行不可用或工具返回诊断时保留 UNKNOWN/FAIL，不提升为 PASS。

## Local evidence

本阶段专用测试覆盖确定性 ID/输入哈希、正反例、缺失输入、适用性不匹配、Cppcheck UNKNOWN、
API 持久化读取和迁移升降级路径。最终本地结果：`146 passed, 1 skipped`，覆盖率 `85.57%`；
mypy 通过（83 个 source files）；clean SQLite `upgrade head + alembic check` 通过；OpenAPI
导出与 TypeScript 生成通过；desktop lint/typecheck/build 均通过。实际 Cppcheck `2.19.0`
无诊断烟测为 PASS，含未使用变量的诊断烟测为 FAIL。

## Acceptance state

本地 M13 实现完成并可验证；M12/M12A 远程 CI 与人工 acceptance 仍保持独立的未决状态，
未将本地结果标记为远程 acceptance。
