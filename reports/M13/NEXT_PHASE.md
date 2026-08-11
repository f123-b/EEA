# M14 下一阶段：Domain Extension Infrastructure

M13 本地实现完成后，下一阶段是 DomainExtensionRegistry、DomainDescriptor、DomainIR envelope、
rule/generator/context/UI hooks 与 `plugins/builtin/` 基础设施。进入 M14 前应完成本次本地
全量验证，并在需要标记 M13 ACCEPTED 时补齐远程 CI 与人工 acceptance 证据。

M14 的不变约束：普通 MCU 项目在空 Domain 列表下仍可创建；Core 不得导入 MotorControl；
Domain Plugin 只能增加更严格的安全规则，不得削弱 Core Safety Rule。
