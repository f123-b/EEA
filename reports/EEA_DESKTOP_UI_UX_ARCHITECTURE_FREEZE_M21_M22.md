# EEA Desktop UI/UX Architecture Freeze
## M21 正式前端 + M22 已有嵌入式项目导入与逆向分析

**状态：Architecture Freeze**  
**用途：Codex 实施 M21/M22 的唯一 UI/UX 基线**

## 1. 产品定位

EEA Desktop 不是普通 AI 聊天网站、BI Dashboard 或 IDE 克隆，而是：

> 以工程项目为核心、AI 作为工程助手、所有事实可追踪/验证/执行的嵌入式研发工作空间。

核心原则：

- Project First
- Project Isolation
- AI 显式上下文
- 前端不创建第二事实源
- Domain UI 动态加载
- UNKNOWN 不猜
- STALE 不冒充 CURRENT
- Mock 不冒充真实能力


## 2. 项目隔离冻结

所有工程资源必须绑定 `project_id`：

- Code
- Hardware
- Requirements
- Documents
- Architecture
- PinMap
- Schematic
- MCU Config
- Firmware
- Protocol
- Build
- Test
- Debug
- Review
- Knowledge
- AI Context
- Import / Reverse Engineering

前端 cache key 必须包含 `projectId`，例如：

```text
["project", projectId, "requirements"]
["project", projectId, "documents"]
["project", projectId, "pin-map"]
["project", projectId, "builds"]
["project", projectId, "chat-thread", threadId]
```

切换 Project 后必须：

1. 清空项目级 selection。
2. 清空当前 editor context。
3. 清空 AI project binding。
4. 重新加载当前项目资源。
5. 不复用上一个项目的 optimistic state。
6. 不允许 Project A 的文件、Build、PinMap、AI 上下文泄漏到 Project B。


## 3. 总体视觉与布局

视觉关键词：

```text
简约 / 高级 / 克制 / 专业 / 工程感 / 低噪声
```

参考气质：Codex、Linear、Raycast、现代 IDE，但不直接复制。

主窗口固定四区：

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar                                                      │
├──────────────┬─────────────────────────────┬─────────────────┤
│ Left Sidebar │ Main Engineering Workspace  │ AI Panel        │
├──────────────┴─────────────────────────────┴─────────────────┤
│ Bottom Status Bar                                            │
└──────────────────────────────────────────────────────────────┘
```

AI Panel 可折叠；主工作区优先。


## 4. Top Bar

高度建议：44–48 px。

左侧：

```text
EEA / Current Project ▼
```

Project Switcher：

```text
Search projects...
FOC Controller
Gateway
Robot Joint
+ New Project
+ Import Existing Project
```

中间：Breadcrumb，例如：

```text
FOC Controller / MCU Config / TIM1
```

右侧只保留：

- Global Search
- Command Palette
- AI Panel Toggle
- Issues
- Settings

禁止塞大量操作按钮。


## 5. Left Sidebar 信息架构

```text
Overview

Engineering
  Requirements
  Documents
  Architecture
  Hardware
  Pin Planner
  Schematic
  MCU Config
  Firmware
  Protocol

Validation
  Build
  Test
  Debug
  Review

Knowledge
  Project Knowledge

Project
  Files
  History
  Settings
```

Domain Plugin 菜单由 metadata 动态注册：

```text
Engineering
  Domain Extensions
    Motor Control
    ...
```

禁止 Core UI 硬编码 MotorControl / FOC / Robot。


## 6. AI Engineering Panel

建议宽度 360–440 px，支持折叠/展开/全屏。

顶部必须显示：

```text
AI Engineer

Context
FOC Controller
MCU Config / TIM1
3 files
2 claims
1 issue
```

用户必须始终知道 AI 当前操作的 Project 和工程上下文。

AI Response 不只是聊天气泡，可包含：

- Answer
- Reasoning Summary
- Engineering Claims
- Evidence
- Issues
- Proposed Changes
- Artifacts
- Actions

危险动作必须显式按钮：

```text
[Build] [Generate] [Apply Patch] [Flash] [Enable Output]
```

不得自动执行。


## 7. AI Context Selector

输入框上方：

```text
Context
[Current Page]
[Selected Files 3]
[Claims 4]
[Documents 1]
[+ Add Context]
```

可添加：

- File
- Requirement
- Claim
- Document
- Pin Assignment
- Hardware Component
- MCU Config Node
- Build/Test Result
- Issue
- Knowledge Entry

禁止默认把整个项目无差别塞进模型。


## 8. Projects 首页

启动后默认：

```text
Projects

Search projects...

Recent
────────────────────────
FOC Controller
STM32G431 · Updated 12 min ago

Gateway
RK3506 · Updated yesterday

Robot Joint
STM32G4 + ROS2 · Updated 3 days ago

[New Project]
[Import Existing Project]
```

只显示有助于继续工作的内容，不做 KPI 卡片墙。


## 9. Project Overview

```text
FOC Controller

STM32G431
Motor Control Plugin
Last validated: 12 min ago

Progress
Requirements      12 / 15 complete
Pin assignment    Ready
Hardware          2 open issues
Firmware          Build passing
Tests             18 / 18 passing

Current Issues
...

Recent Activity
...
```

Overview 是导航与工程状态摘要，不是 BI。


## 10. Requirements

布局：

```text
┌──────────────────────────┬───────────────────────┐
│ Requirement List         │ Inspector             │
│ REQ-001                  │ Title                 │
│ REQ-002                  │ Statement             │
│ REQ-003                  │ Status                │
│                          │ Evidence              │
│                          │ Claims                │
│                          │ Acceptance Criteria   │
└──────────────────────────┴───────────────────────┘
```

状态：

```text
Complete / Incomplete / Ambiguous / Needs Evidence
```

Follow-up Question 直接显示在 Inspector。


## 11. Documents

```text
Documents
[Upload]

Datasheets
App Notes
User Requirements
Schematics
Reference Documents
```

Document Viewer 同时显示：

- Metadata
- Extracted Claims
- Evidence
- Related Engineering Nodes

AI 操作：

```text
Ask about selected page
Extract requirement
Extract claim
Compare with current config
```


## 12. Architecture / Hardware

Architecture 用于：

- SystemArchitectureIR
- HardwareIR
- interfaces
- power domains
- subsystems

默认采用列表 + 简单 topology；只有用户进入 Graph 模式时显示完整图。

Hardware：

```text
Components
Power Domains
Interfaces
Signals
Issues
```

Component Inspector：

```text
Part
Role
Package
Source
Claims
Electrical constraints
Connections
Evidence
Issues
```


## 13. Pin Planner

M7 能力在 M21 的正式 UI：

```text
┌──────────────────┬──────────────────────┬─────────────────┐
│ Requirements     │ Assignment Table     │ Inspector       │
│ PWM_U            │ PA8 TIM1_CH1         │ Pin Detail      │
│ PWM_U_N          │ PB13 TIM1_CH1N       │ AF              │
│ ADC_PHASE_A      │ PA0 ADC1_IN1         │ Constraints     │
│ CAN_TX           │ PB9 FDCAN_TX         │ Evidence        │
└──────────────────┴──────────────────────┴─────────────────┘
```

状态仅使用：

```text
valid / warning / conflict / locked / unknown
```

AI 不得猜 Pin。


## 14. Schematic

不是 KiCad 替代品。

```text
Schematic

[Open Generated]
[Open in KiCad]
[Run ERC]

Preview
Nets
Issues
```

必须显示：

- Artifact Status
- SourceRevision
- ERC Result
- Related HardwareIR


## 15. MCU Config

树：

```text
Clock
GPIO
Timers
PWM
ADC
DMA
Interrupts
Communication
```

右侧 Inspector：

```text
Source
Derived From
Constraints
Claims
Evidence
Dependencies
Affected Artifacts
```

真实 Timer / Channel / Deadtime / ADC Trigger / DMA / IRQ 必须来自 MCUConfigIR，不允许 UI 自己维护副本。


## 16. Firmware

```text
Firmware

Modules
Generated Files
Source Files
Configuration
Dependencies
```

文件显示 ownership：

```text
Generated
User Owned
Imported
Modified
Diverged
```

支持 File Tree + Editor/Diff Viewer，为 M18C Source Authority 兼容。


## 17. Protocol

```text
Protocols

CAN
UART
SPI
Modbus
EtherCAT
...
```

详情：

```text
Messages
Fields
Codec
Generated C
Generated Python
DBC
Tests
```

同一个 ProtocolIR 是唯一事实源。


## 18. Build / Test / Debug / Review

### Build

显示：

```text
Latest Build
PASS
Target: STM32G431
SourceRevision: abc123
0 errors / 2 warnings
[Run Build]
```

每次 Build 绑定 SourceRevision、Toolchain、Result、Artifacts、Diagnostics。

### Test

```text
18 Passed
0 Failed
2 Not Run
```

Test 绑定 Requirement / Artifact / SourceRevision。

### Debug

M21 只建立真实 shell；M34/M35 尚未存在的能力明确标记 Coming Later，不许 Mock 冒充可用。

### Review

```text
Release Readiness
BLOCKED

Requirements
Pin Planner
Electrical Rules
Build
Static Analysis
Tests
Evidence
Traceability

[Run Review]
```

AI 不得覆盖 Compiler / ERC / Rule 明确失败。


## 19. Knowledge / Files / History / Settings

### Project Knowledge

先建立稳定容器，M23+ 接入 Facts / Theory / References / Experience，并显示 scope / authority / trust / source / lifecycle。

### Files

Project-scoped 文件树：

```text
src/
firmware/
hardware/
generated/
docs/
tests/
```

支持 open/search/diff/history/ask AI，不能突破 project workspace root。

### History

统一时间线：

```text
Requirement analyzed
Claim changed
PinMap updated
Firmware generated
Build passed
Test failed
AI proposed patch
User approved patch
```

### Settings

Project Settings：

```text
General
Target
Domains
AI
Build
Security
Danger Zone
```

Global Settings：

```text
Appearance
Language
AI Provider
Secrets
Toolchains
Paths
Updates
Advanced
```

默认语言中文，支持 English。


## 20. 视觉规范

主题：

```text
Light / Dark / System
```

默认 System。

Typography：

```text
UI: system-ui / Segoe UI / Inter fallback
Code: monospace fallback
```

字号建议：

```text
Page title      18–22
Section title   14–16
Body            13–14
Secondary       12–13
Code            12–13
```

Spacing：4px 基线。

```text
4 / 8 / 12 / 16 / 20 / 24 / 32
```

Radius：6–10 px。

主界面以 subtle border 为主，Shadow 只用于 dialog / popover / floating panel。

禁止：

- 霓虹
- 大量渐变
- 玻璃拟态主视觉
- 超大圆角
- 卡片墙
- BI Dashboard 风格


## 21. 状态系统

所有资源必须明确：

```text
Loading
Empty
Loaded
Error
Stale
Permission Required
Capability Unavailable
```

Empty State 必须告诉用户下一步。

例如：

```text
No requirements yet.

[Add Requirement]
[Analyze Text]
```

EngineeringError 显示：

```text
code
message
user action
optional details
```

例如：

```text
PIN_CONFLICT
PA8 is already assigned to TIM1_CH1.
[Open Pin Planner]
```

STALE 必须显式：

```text
Firmware — STALE
Reason: MCUConfig changed after generation.
[Regenerate]
```

Revision Conflict：

```text
This engineering object changed elsewhere.
[Reload Latest] [Compare]
```


## 22. Command Palette 与快捷键

```text
Ctrl/Cmd + K       Command Palette
Ctrl/Cmd + P       Search Files
Ctrl/Cmd + Shift+F Global Search
Ctrl/Cmd + Enter   Run current action
Esc                Close overlay
```

Command Palette 支持：

```text
Go to Requirements
Open Pin Planner
Run Build
Search Symbols
Ask AI About Selection
Import Project
Create Requirement
Open Latest Issue
```


# M22 — Existing Project Import & Reverse Engineering

## 23. 入口

M21 就预留：

```text
Projects → Import Existing Project
Command Palette → Import Project
```

M22 使用五步 Wizard：

```text
1 Source
2 Scan
3 Understand
4 Review
5 Create Workspace
```


## 24. Step 1 — Source

```text
Import Existing Project

○ Local Folder
○ Git Repository
○ Archive
```

Git 需要：

```text
Repository URL
Branch / Tag / Commit
```

安全提示：

```text
External project content is imported into an isolated EEA workspace.
Build scripts are not executed during initial scanning.
```

初始 Import 默认只允许 Scan / Parse，不允许自动 Build / Execute。


## 25. Step 2 — Scan

扫描过程显示真实阶段：

```text
Reading files
Detecting build systems
Detecting MCU / SoC
Detecting generated files
Detecting configuration files
Detecting hardware files
Classifying source
Building dependency index
```

检测：

- C / C++
- CMake
- Makefile
- PlatformIO
- STM32Cube `.ioc`
- KiCad
- DeviceTree
- Zephyr
- FreeRTOS
- HAL / LL / CMSIS
- Linker Scripts
- CAN DBC
- Protocol Definitions

不得执行不可信 Build。


## 26. Step 3 — Understand

页面：

```text
Project Understanding
```

结果：

```text
Detected Platform
Detected Build
Detected RTOS
Detected Hardware
Detected Protocols
Detected Generated Code
```

主区：

```text
Architecture
Modules
Entry Points
Drivers
Dependencies
Hardware Resources
Build Configuration
```

Summary 示例：

```text
Target: STM32G431
Build: CMake
Framework: STM32 HAL
RTOS: FreeRTOS
Motor Control: Detected
Protocols: CAN / UART
Configuration: STM32Cube .ioc detected
Hardware: KiCad project detected
```

每一条都必须显示：

```text
confidence
source
evidence
```


## 27. Source Classification / Module Graph

Files 分类：

```text
User Source
Generated Source
Third-party
Build
Configuration
Hardware
Documentation
Tests
Unknown
```

Module Graph：

```text
main
 ├─ app
 │   ├─ motor
 │   └─ protocol
 ├─ bsp
 ├─ drivers
 └─ platform
```

点击 module：

```text
Files
Symbols
Dependencies
Referenced Hardware
Related Config
```

不能只凭文件名把推断提升为事实。


## 28. MCU / Hardware / Protocol Reverse Engineering

### MCU Resource

解析：

```text
GPIO
Timer
PWM
ADC
DMA
IRQ
Clock
CAN
UART
SPI
I2C
```

交叉验证：

```text
.ioc
source
device database
```

例如 `.ioc` 与源码冲突时必须生成：

```text
CONFIG_SOURCE_MISMATCH
```

不能偷偷选一边。

### Hardware

KiCad 项目解析：

```text
Schematic
PCB
Nets
Components
Power
Interfaces
```

形成 `HardwareIR candidate`，默认 CANDIDATE。

### Protocol

扫描：

```text
CAN ID
packet struct
UART protocol
Modbus
EtherCAT
message enums
serialization
```

形成 `ProtocolIR candidate`，显示 Source / Confidence / Unresolved Fields。


## 29. Step 4 — Review

```text
Review Import

Platform
✓ STM32G431

Build
✓ CMake

RTOS
✓ FreeRTOS

Hardware
! KiCad hardware partially detected

Pin Configuration
! 2 conflicts

Generated Files
✓ STM32Cube generated source detected
```

用户可以：

```text
Accept
Edit
Reject
Mark Unknown
```

Import Issues 单独列出：

```text
HIGH   .ioc pin configuration differs from source.
MEDIUM Two CAN bitrate definitions were found.
LOW    Generated source directory not explicitly marked.
```

禁止为了“导入成功”隐藏问题。


## 30. Step 5 — Create Workspace

确认后生成：

```text
Project
SourceRevision
Imported Files
Project Structure
Detected Configuration
Candidate Claims
Candidate HardwareIR
Candidate MCUConfigIR
Candidate ProtocolIR
Issues
Evidence
```

无足够证据：

```text
UNKNOWN
```

禁止猜。

完成页：

```text
FOC Controller imported

Platform  STM32G431
Files     248
Modules   12
Issues    4
Unknowns  6

[Open Project]
[Review Issues]
```


## 31. SourceRevision / Rescan

Imported Project Overview 显示：

```text
Import Source
SourceRevision
Import Time
Last Rescan
```

Rescan 必须创建新的 `SourceRevision`，不得原地覆盖。

Diff：

```text
+ New timer config
~ CAN bitrate changed
- obsolete UART module
```

同时显示：

```text
Affected Engineering Nodes
MCU Config
Protocol
Firmware
Tests
```

Git Import 必须绑定具体 commit，禁止只记录“某 Git 仓库”。


## 32. 路由冻结

```text
/projects

/projects/:projectId/overview
/projects/:projectId/requirements
/projects/:projectId/documents
/projects/:projectId/architecture
/projects/:projectId/hardware
/projects/:projectId/pins
/projects/:projectId/schematic
/projects/:projectId/mcu-config
/projects/:projectId/firmware
/projects/:projectId/protocol
/projects/:projectId/build
/projects/:projectId/tests
/projects/:projectId/debug
/projects/:projectId/review
/projects/:projectId/knowledge
/projects/:projectId/files
/projects/:projectId/history
/projects/:projectId/settings

/import
/import/source
/import/scan
/import/understand
/import/review
/import/create
```


## 33. 前端目录建议

```text
apps/desktop/src/

app/
  router/
  providers/
  layout/

features/
  projects/
  requirements/
  documents/
  architecture/
  hardware/
  pins/
  schematic/
  mcu-config/
  firmware/
  protocol/
  build/
  tests/
  debug/
  review/
  knowledge/
  import/
  ai/

components/
  ui/
  engineering/
  layout/

api/
  generated/
  client/

state/
  project/
  ui/

styles/
```

禁止继续把正式前端都堆在 `App.tsx`。


## 34. 前端数据规则

`apps/desktop/src/api/generated.ts` 继续作为 API Schema 来源，在外面包 `api/client` 统一处理：

- auth
- request id
- error normalization
- project scope

工程事实不能只存在前端 store。

UI store 只放：

```text
sidebar collapsed
AI panel open
selected tab
panel size
theme
```

高风险工程事实修改必须等服务端确认。

Mutation 只 invalidate 当前 Project 的相关 query。


## 35. M21 实施顺序

```text
1 App Shell
2 Router
3 Project Switcher + isolation
4 Left Sidebar
5 Main Workspace
6 AI Panel
7 Projects/Home
8 Overview
9 Requirements
10 Documents
11 Pin Planner
12 Hardware
13 MCU Config
14 Firmware
15 Build/Test/Review
16 Protocol
17 Files/History/Settings
18 Domain dynamic navigation
19 Loading/Error/Empty/Stale
20 Command Palette
21 full backend integration
22 UI regression / desktop build
```

不要先做动画。


## 36. M22 实施顺序

```text
1 Import Entry
2 Source selector
3 Isolated scan
4 File classification
5 Build-system detection
6 MCU/device detection
7 Source architecture graph
8 .ioc/config reverse engineering
9 Hardware/KiCad reverse engineering
10 Protocol reverse engineering
11 Candidate Claims/IR
12 Conflict generation
13 Review UI
14 Accept/Edit/Reject
15 Create Project Workspace
16 SourceRevision binding
17 Rescan
18 Diff / Impact UI
19 Import acceptance tests
```


## 37. M21 Acceptance

必须满足：

- Project switch 无状态泄漏
- 所有工程页面 project scoped
- AI Context 显示当前 Project
- AI Panel 可折叠
- Requirement / Documents 使用真实后端
- Pin Planner 使用真实 M7 API
- MCU Config 使用真实 M11 API
- Build/Test/Review 使用真实结果
- Domain 菜单动态加载
- EngineeringError 有统一 UX
- STALE 明确显示
- Revision Conflict 可处理
- 无 Mock 冒充真实能力
- Desktop lint/typecheck/build PASS


## 38. M22 Acceptance

必须满足：

- Local Folder Import
- Git Import
- SourceRevision 固定
- 不执行未授权外部 Build
- Build System Detection
- MCU/Resource Detection
- `.ioc` mismatch → Issue
- Source Classification
- Architecture / Module Summary
- Hardware candidate extraction
- Protocol candidate extraction
- UNKNOWN 不猜
- Candidate 不自动 Trusted
- Review 可 Accept/Edit/Reject
- Project Workspace 可生成
- Rescan 不覆盖旧 Revision
- Cross-project Import 不泄漏
- Sandbox Boundary PASS


## 39. 禁止事项

Codex 不得：

```text
做成数据大屏
做成 ChatGPT clone
做 KPI 卡片墙
大量渐变/霓虹/玻璃拟态
每个模块独立视觉体系
硬编码 MotorControl 到 Core UI
不同项目共享工程状态
前端自己维护第二套 MCUConfig
前端自己计算 Pin legality
AI 输出直接覆盖工程事实
Mock 冒充尚未实现的能力
UNKNOWN 自动变成确定值
Imported Candidate 自动 Trusted
外部项目导入时自动执行 build script
```


## 40. Architecture Freeze

以下从 M21 起冻结：

```text
Project First
Project Isolation
Left Navigation + Main Workspace + AI Panel
AI explicit context
Engineering page hierarchy
Dynamic Domain UI
No second fact source
No mock-as-real
M22 five-step Import workflow
SourceRevision-bound reverse engineering
Candidate / Unknown semantics
```

任何修改必须形成新的 Architecture Decision，Codex 不得自行改变。

## 给 Codex 的执行指令

```text
严格按照本文件实施 M21 与 M22。

M21 前不要提前实现正式 Desktop UI，但后续 API 设计需要保持与该信息架构兼容。

到 M21：
先完成 App Shell、项目隔离、Router、AI Panel、Project Workspace，
再逐页接入真实后端能力。
禁止 Mock 冒充已实现能力。

到 M22：
按 Source → Scan → Understand → Review → Create Workspace 五阶段实施已有嵌入式项目导入与逆向分析。
所有导入结果绑定 SourceRevision；
未知保持 UNKNOWN；
推断只能作为 CANDIDATE；
外部 Build/Execute 继续受 Sandbox + Permission 约束。

不得重构无关 Core。
不得创建前端第二事实源。
不得硬编码 MotorControl 到 Core UI。
```
