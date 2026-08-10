# Embedded Engineering Agent
## Plugin SDK Specification V1.3

# 1. 目标

新增 MCU、Tool、Protocol、Instrument、Agent、Generator、Domain、Importer、Knowledge Source 不修改 Core。

# 2. Plugin Types

AgentPlugin、DevicePlugin、RulePlugin、ToolPlugin、GeneratorPlugin、ParserPlugin、RepositoryPlugin、InstrumentPlugin、DomainPlugin、ImporterPlugin、KnowledgeSourcePlugin、UIExtensionMetadataPlugin。

# 3. Built-in Domain Plugin

MotorControl 是首个官方 Built-in Domain Plugin，目录 `plugins/builtin/motor_control/`，使用与外部 DomainPlugin 相同的 manifest/schema/rule/generator/UI contribution 契约。

Core 只认识 DomainDescriptor/DomainIRRef/Capabilities，不认识 FOC 字段。

# 4. Manifest

```yaml
id: org.eea.motor_control
name: Motor Control
version: 1.3.0
api_version: "1"
plugin_type: domain
trust_tier: bundled
entrypoint: eea_motor_control.plugin:Plugin
capabilities: [motor_control.ir, motor_control.review, motor_control.codegen]
permissions: [READ, WRITE, BUILD]
dependencies: []
```

# 5. Domain Contract

DomainPlugin 可以新增 schema/rules/generators/knowledge/context/UI metadata，但不得：
- 修改 Core Schema 既有语义；
- 在 Core DB 私自建无命名空间表；
- 复制 MCUConfigIR 的实际 Timer/ADC/DMA/IRQ 配置成为第二事实源；
- 要求所有 Project 激活该 Domain。

# 6. Dynamic API/UI

Domain 通过 `/projects/{id}/domains` 注册 capability。Frontend 使用 `/ui/extensions` 动态增加导航/表单/动作。固定 `/motor-control` 路径只能作为 builtin plugin compatibility alias。

# 7. Generator / Device / Rule / Tool

Generator 输入使用 Core IR + registered Domain IR。  
DevicePlugin 实现 find/get/pin/peripheral/validate/get_claims。  
RulePlugin 提供 stable rule id/version/tests/no uncontrolled side effect。  
ToolPlugin 提供 ToolInfo/capability/health/permission/Port implementation。

# 8. Importer / Repository / Knowledge Source

RepositoryPlugin：search/metadata/clone-fetch/issues/PR/releases。  
ImporterPlugin：detect/parse/extract facts/generate IR candidates/diagnostics。  
KnowledgeSourcePlugin：发现或访问 Technical Learning Sources，返回 metadata/authority/license/extraction policy；不得绕过 ELKB Curator。

# 9. Trust Tier / Isolation

- `bundled`：EEA 官方随产品发布，可受控 In-Process。
- `signed_trusted`：组织信任签名插件，策略决定 In/Out Process。
- `community_untrusted`：必须 Out-of-Process + Sandbox。

Manifest Permission 不是 OS 安全边界。V1.3 Release 只要求 bundled plugin 完整支持。

# 10. Agent / UI Extension

AgentPlugin 声明 input/output schema、allowed tools、required knowledge domains、prompt、budget profile。UI Extension 第一阶段只允许 navigation/action/form metadata，不允许任意 remote JS。

# 11. Security / Data / Test

安装显示 publisher/source/signature/trust tier/permissions/network/filesystem/dependencies。私有数据 namespaced。必须测试 manifest、compatibility、permission、schema、unit、integration、health、sandbox、core-neutrality。

# 12. V1.3 Domain Composition Contract

DomainDescriptor 声明 requires/optional/conflicts/capabilities/priority/rule phases/generator phases/migration provider。Registry 构建 composition DAG，禁止用插件加载顺序决定语义。

Domain 可贡献 CommissioningStep/Rule，但 Core SafetyState、Permission、ResourceLock、EmergencyStop 不可被绕过或降级。Plugin disable 不删除项目 Domain 数据；upgrade 先 compatibility + migration plan。
