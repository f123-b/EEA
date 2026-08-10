# Embedded Engineering Agent
## Release & Versioning Specification V1.3

# 1. 版本对象

Product、Backend API、Schema、DB Migration、Prompt、Rule Pack、Plugin API、Tool Adapter、Knowledge Snapshot、Benchmark Dataset、Generator 都必须版本化。

# 2. Product / API

Product 使用 SemVer，V1.3 文档基线为 `1.3.0`。API 路径 `/api/v1`，Breaking API 新建 `/api/v2`。

# 3. Schema / Migration

核心 IR 自带 schema_version。Breaking change bump major，并提供 Migration。读取旧项目必须经过 migration chain。

# 4. Prompt / Rule / Plugin

Agent Prompt 保存 name/version/hash，AgentRun 绑定版本。Rule 使用 stable id + version，Issue 保存 rule version。Plugin Manifest 声明 api_version，Core 不兼容则 INCOMPATIBLE。

# 5. Knowledge Snapshot

Release 保存 global knowledge snapshot id、device DB snapshot、reference repo commits、rule pack versions，使旧 Decision 可解释。

# 6. Tool / Generator Version

KiCad、SKiDL、CMake、PlatformIO、Cppcheck、pyOCD、Renode 等关键工具版本进入 Release Report。Schematic/Firmware/Protocol Generator 版本写入 Artifact。

# 7. Compatibility Matrix

至少记录 API、Schema、Plugin API、DB migration、Desktop、Device DB snapshot、Knowledge snapshot。

# 8. Release Gate

必须通过 tests、security、migration、FOC benchmark、import benchmark、artifact invalidation benchmark、API compatibility，且无已知 P0。

# 9. Release Report

包含 Version、Build SHA、Benchmark、Known Issues、Tool Versions、Model Config、Prompt Versions、Rule Versions、Knowledge Snapshot、Schema Version、Migration Version、Plugin API Version。

# 10. Domain / ELKB Compatibility

Release Snapshot 额外记录 active built-in domain versions、Domain Plugin API version、ELKB taxonomy/schema version、Authority policy version、Learning source license policy version。

MotorControl Plugin 可以独立 minor/patch 升级，但 Core major compatibility 必须由 Plugin API matrix 约束。

# 11. V1.3 Additional Release Gate

Release Snapshot 增加 SourceRevision policy、Domain Composition contract、Commissioning/Safety schema、Outbox/Recovery schema、Unit normalization policy、Renderer security policy。Release 必须通过 crash recovery、Domain composition、Source conflict、Hardware commissioning、backup/restore、renderer security 与 NFR benchmark。
