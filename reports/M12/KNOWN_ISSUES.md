# M12 已知问题

1. SourceRevision 当前记录的是 M12 生成候选的确定性 manifest，不是完整 Git 工作区扫描结果。FIX-03 的 Git tracked/untracked/submodule 取证、未声明 untracked 依赖阻断、SourceWorkspaceService 和 patch proposal/apply 流程仍待后续阶段补齐。
2. 默认 CMake/PlatformIO 输出是 host skeleton。真实 STM32 device header、启动文件、linker script、HAL/LL 包和板级 BSP 需要在目标 MCU/工具链适配阶段接入；当前不会伪造 PinMap 或硬件寄存器配置。
3. PlatformIO 构建在未安装 `pio` 时会返回 `UNKNOWN/TOOL_UNAVAILABLE`，这是预期的诚实状态，不会降级为成功。
4. BuildRun 保存 artifact hash 和诊断，但尚未建立独立 ArtifactRecord/对象存储生命周期；产物当前只存在于一次隔离构建 workspace 中。
