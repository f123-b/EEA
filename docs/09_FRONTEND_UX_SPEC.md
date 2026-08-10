# Embedded Engineering Agent
## Frontend UX Specification V1.3

# 1. 定位

前端是工程 IDE，不是聊天 UI。AI 是右侧持续辅助能力，中央区域管理真实工程对象。

# 2. Simple / Expert Mode

Simple：New Project、Import Project、上传资料、输入需求、AI Design、AI Check、AI Debug。  
Expert：Requirement DSL、Claims、Device Facts、Pin Planner、Hardware/Circuit/MCU/Firmware/Motor IR、RTOS、Rules、Evidence、Artifacts、Agent Runs、Memory、Repository Intelligence、Dependency Graph。

# 3. App Shell

顶部：Project / Branch / Build / Search / Active Jobs / Settings。左侧导航工程对象，中间 Workspace，右侧 AI Assistant/Evidence/Actions/Issues。

# 4. Dashboard

New Project、Import Project、Recent Projects、Active Jobs、Critical/High Issues、Tool Health、Stale Artifacts、Knowledge Updates。

# 5. New Project / Import

New Project：Name/Type → Stage → MCU/SoC → optional source → Tool capability check → Create。  
Import：Git URL/Local folder/Archive/.ioc/KiCad；显示 detected build system/MCU/toolchain/files/facts/conflicts/IR candidates/build issues；用户 Accept/Compare/Ignore/Lock fact。

# 6. Project Overview

Requirement completeness、Device/Pin status、HW/FW status、Build status、Test coverage、Review issues、Verification、Stale count、Engineering Score、Current Stage、Recommended Next Action。

# 7. Documents / Claims / Requirements

Documents：左列表，中 PDF/Text，右 extracted claims/evidence/conflicts/AI question。  
Claims：subject/predicate/value/applicability/source/verification/conflict，可打开 source locator。  
Requirements：表格+Form，Analyze/Extract/Validate/Missing/Recommendation Accept/Edit。

# 8. Architecture / Pin Planner

Architecture block diagram 支持 regenerate/lock/explain/compare/stale marker。  
Pin Planner 左 required signals，中 package/pin view，右 candidates/hard constraints/conflicts/evidence；支持 auto/manual/lock/validate/export。非法 Pin 必须后端 reject。

# 9. Hardware / Circuit / Schematic

Hardware Tabs：System、Power、Components、Interfaces、PinMap、Circuit、Schematic、BOM。  
Circuit 显示 Net/critical nets/power nets/EngineeringValue/Evidence，Expert 可编辑 IR。  
Schematic 显示 version/backend/ERC/dependency status/stale reason/compare/export；V1.3 不自研完整 EDA 编辑器。

# 10. MCUConfig / Firmware / MotorControl

MCUConfig：Clock tree、GPIO、Timer/PWM、ADC、DMA、IRQ、Debug，每项可定位 Device Claim/Evidence。  
Firmware：Architecture、Modules、MCU Config、RTOS、Code、Build、Static Analysis；Code View tree/diff/AI edit/build error jump/stale marker。  
Motor Control：Motor params、Encoder、Current sense、PWM、ADC timing、Electrical angle、Sign convention、Current/Velocity/Position loops、Limits/Faults。

# 11. Protocol / Tests / Review / Debug

Protocol 表格编辑 Message/ID/Direction/Period/Fields，实时显示 CAN Payload 与 C/Python/DBC generator status。  
Tests 显示 Plan/Coverage/Cases/Runs/Results，失败 Case 一键 Create Debug Session。  
Review Issue Board 显示 evidence/claim/rule/tool/recommendation/repair。  
Debug 左 Symptom/Logs/Attachments，中 Root Cause/Verification Plan，右 AI/Evidence/Related MCU/Motor objects。

# 12. Knowledge / Repository

Knowledge Center：Global、Project Memory、Reference Projects、Patterns、Anti-Patterns、Debug Cases、Candidates、Gaps、Claims。  
Repository Candidate Card 显示 repo/domain/score/freshness/license/analysis level/estimated cost/status，支持 shallow/deep/project reference/global candidate/reject。

# 13. AI Panel / Evidence

Context chips：project、module、issue、claim、document、code、artifact。Actions：Explain、Review、Generate、Compare、Fix、Create Test、Why stale?。Evidence icon 可定位 Datasheet page/Device claim/Rule/Repo commit/Tool result/Hardware test/Import source。

# 14. Staleness / Long Job / Permission

Artifact 显示 CURRENT/STALE/INVALID、stale cause、old/new hash、recommended regenerate order。  
Job 显示 status/progress/phase/logs/budget/cancel。  
危险操作显示 target/firmware hash/risk/expected effect/resource lock/Confirm。  
Resource Busy 显示 owner job/operation/lock expiry，不静默抢占。

# 15. Style

简约高级、专业工程工具、高信息密度、清晰层级、深浅色、中文默认、i18n 预留，不用巨型聊天气泡主导。

# 17. Knowledge Center / Learning Knowledge

Knowledge Center：

```text
Overview
Device Knowledge
Datasheet
Learning Knowledge
Reference Projects
Architectures
Patterns
Debug Cases
Knowledge Gaps
Candidates
```

Learning Knowledge 页面：Domain Navigation、Search、Knowledge Type、Authority、Trust、Source、Related Concepts/Algorithms/Rules/Debug Cases。

Detail：Definition、Explanation、Applicable Conditions、Limitations、Formula、Examples、Source、Authority、Trust、Verification、Relations。

ELKB 主要消费者仍是 Engineering Agent；V1.3 不把前端做成在线课程系统。Explain/Learning/Interview Mode 仅作为后续扩展。

# 18. Dynamic Domain Navigation

Frontend 不固定假设 MotorControl 存在。通过 `/projects/{id}/domains` + `/ui/extensions` 获取导航、表单、动作和 capability；未激活 Domain 不显示对应页面。

# 19. V1.3 Safety / Source / Recovery UX

新增 Source Status、Domain Extensions、Commissioning、Recovery Center。Actuator Enable 页面持续显示 Target identity、firmware hash、Safety Profile/limits、ResourceLock 与 Emergency Stop；不得用普通 “Run” 按钮模糊表达。
