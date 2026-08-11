# M13 下一阶段：Firmware 静态分析与规则门禁（当前 NO-GO）

M13 暂不启动。必须先完成 M12R/M12A 的远程 CI 绿色验证与人工 acceptance，确认本地真实 STM32G431 DEVICE 构建证据在远程环境可复现，并关闭报告中的未决项。

## 后续计划

- 在远程 CI 重新运行 backend、迁移、OpenAPI、desktop 与设备构建门禁。
- 完成 M12 acceptance 后，再实现 Firmware 静态分析与规则模型：`APP_DIRECT_HAL_CALL`、`ISR_BLOCKING`、`DEPENDENCY_CYCLE`、`MCUCONFIG_FIRMWARE_MISMATCH`。
- 静态分析工具缺失必须保留 UNKNOWN 诊断，不能把工具不可用转换为 PASS。
