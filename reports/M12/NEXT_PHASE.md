# M13 下一阶段：Firmware 静态分析与规则门禁（已按用户指令启动）

M12R/M12A 的远程 CI 绿色验证与人工 acceptance 仍是 M12 正式标记 ACCEPTED 的前置条件；本地任务已按用户最新指令继续进入 M13 实施。M13 的远程验收仍不得以本地结果替代。

## 后续计划

- 在远程 CI 重新运行 backend、迁移、OpenAPI、desktop 与设备构建门禁。
- 实现并验证 Firmware 静态分析与规则模型：`APP_DIRECT_HAL_CALL`、`ISR_BLOCKING_API`、`DRIVER_DEPENDENCY_CYCLE`、`MCUCONFIG_FIRMWARE_MISMATCH`。
- 接入无 shell、无网络的 Cppcheck Adapter；工具缺失或执行不可用必须保留 `UNKNOWN`。
- 持久化分析运行、工具结果与归一化 RuleResult，并暴露项目级创建、列表和详情 API。
- 静态分析工具缺失必须保留 UNKNOWN 诊断，不能把工具不可用转换为 PASS。
