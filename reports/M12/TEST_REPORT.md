# M12 FirmwareIR 与真实构建验证报告

## 结论

M12 已完成并通过验证。FirmwareIR、确定性源码候选、SourceRevision、BuildInputSnapshot、CMake/PlatformIO 构建适配器以及构建 API 已接入；构建结果不会在工具链缺失、MCUConfigIR 未知或产物缺失时被错误标记为 PASS。

## 交付范围

- Core 新增 FirmwareIR、FirmwareBundle、SourceRevision、BuildInputSnapshot、BuildRun 与构建诊断模型。
- Application 从当前 MCUConfigIR 生成确定性的 host STM32 skeleton 源码，并保留 MCUConfigIR 的 ID、revision、时钟和结构化追溯关系。
- Backend 新增 firmware/build 持久化、迁移 `0014_m12_firmware_build` 和 API：
  - `POST/GET /projects/{project_id}/firmware`
  - `POST /projects/{project_id}/build`
  - `GET /projects/{project_id}/builds`
  - `GET /projects/{project_id}/builds/{build_id}`
- BuildRun 强制绑定 `build_input_snapshot_id`；快照 hash 覆盖 generated input、source manifest、build config、toolchain 和环境 profile。
- 构建命令通过 SafePath 与 allowlisted structured argv 执行，编译器临时目录保持在隔离 workspace 内。

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff format/check | PASS |
| mypy strict | PASS，56 个源文件 |
| 全量 pytest（无覆盖率） | 132 passed，1 skipped |
| 全量 pytest + coverage | 132 passed，1 skipped，89.29% |
| M11/M12、迁移、OpenAPI 聚焦测试 | 9 passed |
| 真实 CMake host skeleton build | PASS，artifact hash 已生成 |
| Desktop lint/typecheck/build | PASS |

## 追溯与门禁

- M11 `FAIL` rule result 会阻止 FirmwareIR 生成。
- M11 `UNKNOWN` rule result 会生成源码候选，但阻止实际构建并返回 `MCU_CONFIG_UNKNOWN`。
- 生成源码不写入用户工作树；当前 SourceRevision 明确标记 `dirty=true`、`commit_sha=null`，表示待应用的 generated candidate。
