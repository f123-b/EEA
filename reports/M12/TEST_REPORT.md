# M12R / M12A FirmwareIR 与 ESCR 集成验证报告

## 结论

本地实现与验证已完成，但 M12 仍保持 **NOT ACCEPTED**：基线远程 CI run `31467030846` 曾报告 backend 3 failed / 130 passed，desktop PASS；本次按用户要求未推送，因此没有新的远程绿灯证据。M13 继续 **NO-GO**，不得据此宣称 M12 最终通过。

## 交付范围

- M12R 修复：`BuildRun` 使用同一 `now` 初始化时间戳；100 次、全部终态回归；构建时长聚合；`HOST_SMOKE`/`DEVICE` 分型；CMake 标识/flags/defines 注入防护；PlatformIO native fallback 禁用；FirmwareIR hash 覆盖 MCUConfigIR、target、board、DependencyLock 与 adapter。
- M12A ESCR：Core-neutral `SoftwareComponent`、immutable `ComponentRelease`、`DependencyLock`、license/compatibility/reference-only policy、确定性解析、依赖环/冲突检测、离线 content-addressed materialization/cache。
- Provider：官方 STM32CubeG4 `v1.6.3`，固定 commit `d11b194a9f05d1b143d154771f3dbc282c8052a`，包含 CMSIS Core/Device、HAL、GCC G431 startup 与 linker script；FreeRTOS 与 CMSIS-DSP 使用 deterministic resolution fixtures。
- Backend：组件 catalog/detail、resolve、lock、materialize API；`0015_m12a_software_components` migration；FirmwareIR/BuildInputSnapshot/BuildRun 的 dependency lock 追溯字段。

## 验证结果

| 检查 | 结果 |
|---|---|
| Ruff format/check | PASS |
| mypy | PASS，77 个源文件 |
| 全量 pytest + coverage | 139 passed，1 skipped，85.58% |
| M12/M12A/M11/迁移聚焦测试 | 15 passed |
| OpenAPI 与后端生成结果 | PASS |
| 真实 STM32G431 DEVICE CMake build | PASS，ARM ELF；GCC 14.2.1；2154 ms；artifact `0ce741db36933c70a27f880f4a28a8c9542936f16279eac7aebe8d6199ee905c` |
| Desktop lint/typecheck/build | PASS |

## 门禁与残余状态

- `FAIL` MCUConfigIR rule 阻止 FirmwareIR 生成；`UNKNOWN` 阻止实际构建和 PASS 结论。
- DEVICE 构建必须绑定 LOCKED DependencyLock，并从离线缓存 materialize；禁止构建阶段联网或隐式下载。
- SourceRevision 仍是 generated candidate 的确定性 manifest，不是完整 Git 工作区扫描；FIX-03 继续 PARTIAL。
- 远程 CI 需要在下一次提交后重新执行并取得绿色结果，随后再进行人工 M12 acceptance；在此之前停止于 M12，不实现 M13。
