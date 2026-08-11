# M13 下一阶段：Firmware 静态分析与规则门禁

## 目标

在 M12 的 FirmwareIR、源码 manifest 和 BuildRun 之上，建立构建前后的静态分析与固件工程规则门禁，让源码生成、编译诊断和规则结果形成可追溯闭环。

## 计划交付

- Core 规则模型和确定性结果：规则 ID、版本、阶段、severity、status、证据、输入 hash。
- FirmwareIR 结构规则：模块依赖环、ISR 阻塞操作、任务/中断共享资源、启动/时钟树缺失、BSP 与 MCUConfigIR 不一致。
- 源码规则：直接 HAL 调用、未声明外部依赖、生成文件 ownership、编译器告警升级策略。
- Backend 持久化与 API：firmware validation、diagnostics 查询、规则结果与 BuildRun/source snapshot 的关联。
- CMake/PlatformIO 静态分析适配器，缺少工具时返回 UNKNOWN 并保留可审计诊断。

## 关键验收

1. 同一 FirmwareIR 与同一 source snapshot 产生相同的规则输入 hash 和结果排序。
2. `FAIL` 规则阻止构建；`UNKNOWN` 规则阻止宣称 PASS，但保留构建候选和诊断。
3. 每条规则结果可追溯到 FirmwareIR、SourceRevision、BuildInputSnapshot 及具体源码路径/行号。
4. 覆盖循环依赖、ISR 阻塞、HAL 直调、工具链缺失和 stale MCUConfigIR 的正反例测试。
