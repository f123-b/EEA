# M12R / M12A 已知问题

1. 远程 CI run `31467030846` 的 backend 仍有 3 个失败；本地修复尚未推送，远程绿色验证与人工 acceptance pending。
2. SourceRevision 当前记录生成候选的确定性 manifest，不是完整 Git working tree 扫描；未声明 untracked 依赖、SourceWorkspaceService、patch proposal/apply 仍属于 FIX-03 后续范围。
3. PlatformIO native fallback 已禁用；DEVICE 只允许真实 CMake + `arm-none-eabi-gcc` 路径。缺少工具链或离线组件缓存时必须返回明确的 blocked/unavailable，而非伪造 PASS。
4. STM32CubeG4 provider 固定为官方 `v1.6.3`/commit `d11b194a9f05d1b143d154771f3dbc282c8052a`；FreeRTOS/CMSIS-DSP 当前完成解析 fixture，尚未作为首个设备构建的必需组件。
5. BuildRun 已保存 artifact hash 与诊断，但尚未建立独立 ArtifactRecord/对象存储生命周期；构建产物仍只存在于隔离 workspace 生命周期内。
