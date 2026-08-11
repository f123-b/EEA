# EEA M5R + M13R + Project Scope Hardening  
## Codex 修改任务与新对话接续文档

> 项目：Embedded Engineering Agent（EEA）  
> 仓库：`f123-b/EEA`  
> 基线：当前 `main`，实际开发已进入 M13  
> 本任务性质：**架构基础加固 / P0-P1 修复，不是新增业务功能**  
> 后续阶段：本任务验收完成后，才允许进入 M14 Domain Extension Infrastructure

---

# 0. 新 Codex 对话启动提示词

如果需要更换 Codex 对话，请将**本文件保留在仓库中**，然后把下面整段提示词直接发送给新的 Codex 对话。

```text
你现在接手 Embedded Engineering Agent（EEA）项目。

仓库：
https://github.com/f123-b/EEA

首先不要直接修改代码。

第一步必须完整阅读：

1. docs/README.md
2. docs/11_CODEX_IMPLEMENTATION_AND_ACCEPTANCE.md
3. docs/CODEX_M5R_M13R_PROJECT_SCOPE_HARDENING_TASK.md
4. 与 Sandbox、M13 Static Analysis、Document、Evidence、Project Scope 相关的现有代码和测试
5. reports/M12/
6. reports/M13/

然后检查当前 Git HEAD 和工作区状态，确认仓库是否已经有人部分执行本修复任务。

注意：

- 不要假设之前 Codex 对话的上下文仍然存在。
- 以仓库当前代码、本任务文档和 Architecture Freeze 文档为 SSOT。
- 不要重新设计 EEA 总体架构。
- 不要开始 M14。
- 不要把 MotorControl/FOC 逻辑加入 Core。
- 不要顺手重构无关模块。
- 不要为了让测试通过而降低安全策略。
- 不允许把 UNKNOWN 改成 PASS 来绕过 Release Gate。
- 不允许通过 mock 假装真实安全隔离已经实现。
- 所有不具备真实安全能力的平台必须 fail closed。
- 修改数据库结构时必须使用 Alembic migration。
- 修改 API 时必须同步 OpenAPI、TypeScript API 和相关测试。
- 必须保持已有 M1-M13 能力兼容，除非本任务明确要求改变接口。

本轮只解决三个问题：

P0/P1-1：
Sandbox 的安全能力目前大量只是策略声明，没有形成真实执行边界。

P1-2：
M13 RELEASE_GATE 对 C/C++ 的关键规则依赖 regex + 手工花括号扫描，确定性不足。

P1-3：
Document / Evidence 没有完全贯彻 Project Scope Isolation，存在跨项目资源读取和 Document 去重导致作用域污染的风险。

执行方式必须为：

Inspect
→ 写实施计划
→ M5R
→ M5R 测试
→ M13R
→ M13R 测试
→ Project Scope Hardening
→ 跨项目隔离测试
→ 全量 Regression
→ 文档/报告更新
→ 最终 Review

不要一次性无验证地大规模修改。

每完成一个阶段都先运行对应测试。

最终必须给出：

1. 修改文件清单
2. 每个问题的根因
3. 每个问题的最终实现
4. 新增测试清单
5. 全量测试结果
6. 尚未解决的问题
7. 是否满足进入 M14 的条件

只有所有 P0/P1 验收项 PASS，才允许给出：

M5R = ACCEPTED
M13R = ACCEPTED
PROJECT_SCOPE_HARDENING = ACCEPTED
READY_FOR_M14 = YES

否则必须：

READY_FOR_M14 = NO

现在开始先审查代码和本任务文档，然后实施，不要向我重复询问已经在文档中明确的需求。
```

---

# 1. 本次任务目标

本次不开发新的 EEA Domain，不开发 MotorControl Plugin，不进入 M14。

本轮只修复以下三个架构基础问题。

## P0/P1-1：Sandbox Security Hardening

当前 Sandbox 已经存在：

- executable allowlist
- runtime timeout
- network_access
- max_memory_bytes
- max_processes
- max_output_bytes
- environment allowlist
- SafePath
- archive extraction protection

但其中若干能力实际上只是 Policy 字段，底层仍主要依赖普通：

```python
subprocess.Popen(...)
```

因此现在不能把它视为可信的“不可信代码执行安全边界”。

本轮定义为：

**M5R — Sandbox Security Hardening**

---

## P1-2：M13 RELEASE_GATE Deterministic C/C++ Analysis

当前：

`application/src/eea_application/static_analysis.py`

使用 regex 和手工 brace counting 实现：

- APP_DIRECT_HAL_CALL
- ISR_BLOCKING_API

这对于 RELEASE_GATE 不够可靠。

本轮定义为：

**M13R — Deterministic Static Analysis Hardening**

---

## P1-3：Project Scope Isolation

当前大部分 Firmware / MCUConfig / Build 等主链路已经按：

```text
project_id
```

隔离。

但 Document / Evidence 仍存在作用域缺口。

例如当前存在：

```text
GET /documents/{document_id}
```

DocumentRepository：

```python
get(document_id)
```

Evidence：

```text
GET /evidence/{evidence_id}
```

其中 `project_id` 还是 optional。

这意味着 Project A 只要拿到 Project B 的 UUID，就可能绕开项目作用域读取。

另外当前 Document 通过 `content_hash` 做全局数据库去重，也可能导致两个项目上传相同内容时复用另一个项目的 Document metadata。

本轮定义为：

**Project Scope Hardening**

---

# 2. 总体架构约束

修改过程中必须保持以下原则。

## 2.1 Core Neutrality

Core 只能存在通用工程能力。

禁止：

```text
FOC
MotorControl
PMSM
BLDC
特定 STM32 项目
机器人业务
```

直接进入 Core。

Sandbox、Static Analysis、Scope Policy 都必须保持领域无关。

---

## 2.2 Project 是工程数据隔离边界

默认规则：

```text
Project A
├── Requirements
├── Architecture
├── Hardware
├── Circuit
├── Schematic
├── MCUConfig
├── Firmware
├── Builds
├── Static Analysis
├── Tests
├── Documents
├── Evidence
└── Future Memory / Knowledge
```

不得直接读取 Project B 的 private resources。

即：

```text
A.resource ≠ B.resource
```

项目之间不得因为：

```text
UUID
content_hash
storage path
缓存
DocumentIR
Evidence
ContextBuilder
```

发生作用域串扰。

---

## 2.3 Fail Closed

以下场景不得返回 PASS：

```text
解析失败
Sandbox 能力不可用
Sandbox 能力无法验证
工具输出不完整
Cppcheck XML 损坏
C/C++ AST 不完整
资源作用域无法确认
执行环境无法保证网络隔离
执行环境无法保证要求的资源限制
```

必须：

```text
UNKNOWN
DENIED
UNAVAILABLE
```

或直接拒绝执行。

绝对禁止：

```text
“不知道，所以先 PASS”
```

---

# 3. Task A — M5R Sandbox Security Hardening

重点文件至少检查：

```text
core/src/eea_core/sandbox.py
adapters/src/eea_adapters/sandbox.py
tests/test_m5_sandbox.py
```

并检查所有：

```text
StructuredCommandExecutor
SandboxPolicy
CommandSpec
CppcheckAdapter
build executor
external tool invocation
archive materializer
```

调用关系。

必要时新增：

```text
ports/src/eea_ports/sandbox.py
```

以及具体 Runtime Adapter。

---

# 4. M5R-1：修复 executable basename allowlist

当前禁止继续使用这种安全判断：

```python
Path(executable).name
```

与：

```python
Path(allowed).name
```

比较。

例如：

```text
/usr/bin/cmake
/tmp/untrusted/cmake
```

basename 都是：

```text
cmake
```

不能认为是同一个可信 executable。

## 必须改为

启动前解析实际 executable：

```text
requested executable
↓
canonical absolute path
↓
resolve symlink
↓
trusted executable identity
↓
execute
```

最少验证：

```text
exact canonical path
```

推荐模型：

```text
TrustedExecutable
- canonical_path
- optional_sha256
- optional_version
```

禁止 basename 成为授权依据。

### 验收测试

必须存在攻击测试：

```text
allow:
/trusted/bin/cmake

execute:
/tmp/fake/cmake
```

即使名字相同，也必须：

```text
COMMAND_NOT_ALLOWED
```

---

# 5. M5R-2：Sandbox Capability 必须代表真实能力

建议引入类似：

```python
SandboxCapabilities
```

至少表达：

```text
network_isolation
memory_limit
process_limit
process_tree_kill
streaming_output_limit
filesystem_isolation
```

Sandbox Runtime 必须明确报告自己真实具备哪些能力。

禁止：

```text
policy.network_access = False
```

但操作系统实际上仍然允许进程访问网络。

---

# 6. M5R-3：建立 SandboxRuntime 抽象

建议增加 Core-neutral Port：

```python
class SandboxRuntime(Protocol):
    def capabilities(...) -> SandboxCapabilities:
        ...

    def execute(...) -> CommandResult:
        ...
```

注意：

**Core 只定义 capability / contract。**

Linux、Windows 等 OS 实现放 Adapter。

不要把：

```text
Linux namespace
Windows Job Object
bubblewrap
AppContainer
cgroup
```

直接写进 Core。

---

# 7. M5R-4：区分 TRUSTED_TOOL 与 UNTRUSTED_CODE

建议增加执行信任等级，例如：

```text
TRUSTED_TOOL
UNTRUSTED_CODE
```

### TRUSTED_TOOL

例如：

```text
cmake
ninja
arm-none-eabi-gcc
cppcheck
```

这些必须仍然验证：

```text
canonical executable
environment
cwd
timeout
output limit
```

### UNTRUSTED_CODE

例如未来：

```text
外部 GitHub repository
第三方 Plugin
用户上传项目中的脚本
AI 生成并准备执行的程序
```

必须要求 Strong Sandbox。

如果当前平台不存在强隔离能力：

```text
必须拒绝运行
```

禁止自动退化到普通 subprocess。

---

# 8. M5R-5：network_access=False 必须真实生效

当前仅检查：

```python
if spec.network_required and not policy.network_access
```

不足。

恶意程序不会主动声明：

```text
network_required=True
```

所以：

```text
network_access=False
```

必须由 Runtime 强制隔离。

如果当前系统无法可靠执行网络隔离：

```text
capabilities.network_isolation = False
```

请求要求：

```text
network_access=False
```

且属于必须隔离的执行类型时：

```text
拒绝 spawn
```

禁止：

```text
先运行，再假装无网络
```

---

# 9. M5R-6：max_memory_bytes 必须真实执行

当前存在 Policy，不代表真正限制。

要求：

```text
max_memory_bytes
```

要么：

```text
由 Runtime 在执行前强制设置
```

要么：

```text
Runtime 声明 memory_limit=False
并 fail closed
```

绝对不能：

```text
字段存在
但什么也没做
然后继续执行
```

---

# 10. M5R-7：max_processes 必须真实执行

同理：

```text
max_processes
```

必须限制整个 sandbox workload 的进程树。

不是只限制父进程。

需要防止：

```text
fork bomb
child process escape
detached process
```

如果平台无法提供该保证：

```text
capability unavailable
```

不得宣称 Secure Sandbox。

---

# 11. M5R-8：Timeout 必须杀死整个 process tree

当前：

```python
process.kill()
```

只杀直接 child 的设计不够。

要求：

```text
timeout
↓
terminate sandbox process group/job
↓
确认 children 全部结束
↓
cleanup
```

POSIX / Windows 使用各自 Adapter。

Core 不感知 OS。

---

# 12. M5R-9：Output Limit 改为 streaming enforcement

当前模式：

```python
stdout, stderr = process.communicate()
```

然后：

```python
if len(stdout) > max_output_bytes:
```

太晚。

进程可能先输出：

```text
500 MB
2 GB
...
```

Python 已经把输出读入内存。

要求改成：

```text
spawn
↓
concurrent stdout/stderr streaming
↓
incremental byte counter
↓
超过 max_output_bytes
↓
立即 kill process tree
↓
RESOURCE_LIMIT_EXCEEDED
```

Windows 与 POSIX 都必须避免 stdout/stderr pipe deadlock。

---

# 13. M5R-10：Sandbox 降级策略

必须明确区分：

```text
Functional Command Executor
Strong Security Sandbox
```

如果只是普通 subprocess：

不得把它标记为：

```text
secure
isolated
untrusted-safe
```

最低原则：

```text
Capability unavailable
→ fail closed
```

而不是：

```text
Capability unavailable
→ fallback subprocess
```

---

# 14. M5R 测试要求

扩展：

```text
tests/test_m5_sandbox.py
```

或拆分：

```text
tests/sandbox/
```

至少加入：

### SBOX-01

Fake executable basename spoof。

结果：

```text
DENY
```

### SBOX-02

Executable symlink identity attack。

结果：

```text
DENY
```

或解析到受信任 canonical target 后进行严格判断。

### SBOX-03

Network denied。

实际尝试建立 socket。

如果 Runtime 声明支持 network isolation：

```text
socket 必须失败
```

如果不支持：

```text
执行必须在 spawn 前被拒绝
```

### SBOX-04

Memory cap。

如果支持：

```text
超过 limit → terminate
```

否则：

```text
fail closed
```

### SBOX-05

Process count。

尝试创建多个 child。

必须限制或拒绝执行。

### SBOX-06

Timeout child tree。

父进程创建 child 后超时。

最终：

```text
parent dead
child dead
```

### SBOX-07

Output flood。

生成远超：

```text
max_output_bytes
```

的数据。

不能先完整缓存。

必须提前终止。

### SBOX-08

Environment secret。

已有测试继续保持。

### SBOX-09

Path traversal / symlink / archive bomb。

原有 M5 能力不得回归。

---

# 15. M5R 验收条件

只有全部满足才能：

```text
M5R = ACCEPTED
```

必须满足：

```text
[ ] 不再使用 basename 作为 executable 安全身份
[ ] network policy 与真实 Runtime capability 一致
[ ] memory policy 与真实 capability 一致
[ ] process count policy 与真实 capability 一致
[ ] timeout 杀死 process tree
[ ] output streaming 限制
[ ] unsupported capability fail closed
[ ] untrusted code 不允许降级 subprocess
[ ] adversarial tests PASS
[ ] 原 M5 archive/path tests PASS
```

---

# 16. Task B — M13R Deterministic Static Analysis

重点：

```text
application/src/eea_application/static_analysis.py
adapters/src/eea_adapters/static_analysis/cppcheck.py
tests/test_m13_static_analysis.py
```

---

# 17. M13R-1：禁止 RELEASE_GATE 仅依赖 regex 理解 C/C++

当前：

```text
_HAL_CALL
_IRQ_NAME
_FUNCTION_START
_BLOCKING_CALL
_function_body()
```

不能继续作为 authoritative parser。

Regex 可以保留：

```text
快速预筛选
辅助诊断
fallback hint
```

但不能成为 RELEASE_GATE PASS/FAIL 的唯一依据。

---

# 18. M13R-2：引入真正的 C/C++ Syntax Parser

实现一个独立 abstraction，例如：

```python
CppSourceAnalyzer
```

或：

```python
CppSyntaxProvider
```

推荐使用：

```text
Tree-sitter C/C++
```

如果仓库依赖策略最终选择：

```text
Clang AST / libclang
```

也可以。

关键不是库名称，而是必须基于：

```text
syntax tree / AST
```

识别：

```text
function_definition
call_expression
identifier
function body
comments
strings
parse error
```

不要自行继续扩大正则解析器。

---

# 19. M13R-3：APP_DIRECT_HAL_CALL

目标：

Application-owned source 不得直接调用：

```text
HAL_*
LL_*
```

检测对象必须是真实：

```text
call expression
```

例如：

```c
HAL_GPIO_WritePin(...);
```

应：

```text
FAIL
```

但：

```c
// HAL_GPIO_WritePin(...)
```

必须：

```text
PASS
```

下面字符串：

```c
printf("HAL_GPIO_WritePin(...)");
```

必须：

```text
PASS
```

Documentation text：

```c
const char *help = "Call HAL_Delay() here";
```

也不能触发。

---

# 20. M13R-4：ISR_BLOCKING_API

必须通过 Syntax Tree 找到真实：

```text
function_definition
```

例如：

```c
void TIM1_UP_TIM16_IRQHandler(void)
{
    HAL_Delay(10);
}
```

必须：

```text
FAIL
```

如果仅存在：

```c
// void TIM1_UP_TIM16_IRQHandler(void) { HAL_Delay(10); }
```

不得 FAIL。

如果 interrupt 在 FirmwareIR 声明：

```text
TIM1_UP_TIM16_IRQHandler
```

但源码无法找到对应定义：

```text
UNKNOWN
```

不能 PASS。

---

# 21. M13R-5：Parser Uncertainty

以下情况：

```text
syntax tree error
source truncated
无法完整解析 function
关键节点受 preprocessing/macro 影响而无法确定
encoding/parser failure
```

不得：

```text
PASS
```

应该：

```text
UNKNOWN
```

并输出：

```text
affected_refs
diagnostic
parser status
```

Release Gate 的核心原则：

```text
确定安全 → PASS
确定违反 → FAIL
无法确定 → UNKNOWN
```

---

# 22. M13R-6：结构化规则保持不动

下面两类当前基于结构化 IR 的规则：

```text
DRIVER_DEPENDENCY_CYCLE
MCUCONFIG_FIRMWARE_MISMATCH
```

原则上不要改造成 AST。

除非发现明确 Bug，否则只保持现有行为并跑 regression。

---

# 23. M13R-7：Cppcheck XML 必须严格解析

当前禁止继续使用类似：

```python
re.search("<error", output)
```

作为最终判定。

使用标准 XML Parser。

Cppcheck：

```text
--xml
--xml-version=2
```

输出必须实际解析。

逻辑：

### 情况 A

Cppcheck 不存在：

```text
UNKNOWN
```

### 情况 B

Sandbox 无法运行：

```text
UNKNOWN
```

### 情况 C

Timeout：

```text
UNKNOWN
```

### 情况 D

Output truncated：

```text
UNKNOWN
```

### 情况 E

XML malformed：

```text
UNKNOWN
```

### 情况 F

XML root/schema 基本结构不完整：

```text
UNKNOWN
```

### 情况 G

XML 完整且包含 diagnostics：

```text
FAIL
```

### 情况 H

XML 完整、无 diagnostics、execution 正常：

```text
PASS
```

### 情况 I

XML 完整、无 diagnostics，但进程异常退出：

```text
UNKNOWN
```

不要把 tool crash 当成 source PASS。

---

# 24. M13R adversarial test matrix

至少增加：

### STATIC-01 Comment False Positive

```c
// HAL_Delay(100);
```

结果：

```text
APP_DIRECT_HAL_CALL != FAIL
```

### STATIC-02 String False Positive

```c
const char *x = "HAL_GPIO_WritePin(...)";
```

不得 FAIL。

### STATIC-03 Actual HAL Call

```c
HAL_GPIO_WritePin(...);
```

Application layer：

```text
FAIL
```

### STATIC-04 Driver HAL Call

合法 Driver/Platform 目录调用。

不得触发 APP_DIRECT_HAL_CALL。

### STATIC-05 ISR comment

注释中的：

```text
IRQHandler
HAL_Delay
```

不得误判。

### STATIC-06 Real ISR blocking call

真实 ISR 调：

```text
HAL_Delay
vTaskDelay
osDelay
xQueueReceive
...
```

必须 FAIL。

### STATIC-07 Nested braces

函数里：

```text
if
switch
struct initializer
nested scopes
```

不得破坏 function body 判断。

### STATIC-08 String containing braces

```c
printf("{ }");
```

不得影响 AST。

### STATIC-09 Parser damaged input

不完整 C/C++：

```text
UNKNOWN
```

### STATIC-10 C++ source

至少覆盖：

```text
.cpp
namespace
class method
```

不应因为文件是 C++ 就退化为 regex。

### STATIC-11 Broken Cppcheck XML

结果：

```text
UNKNOWN
```

### STATIC-12 Truncated Cppcheck XML

结果：

```text
UNKNOWN
```

### STATIC-13 Valid XML diagnostics

结果：

```text
FAIL
```

### STATIC-14 Valid XML clean

结果：

```text
PASS
```

---

# 25. M13R 验收标准

```text
[ ] RELEASE_GATE 不再依赖 regex 作为 authoritative C/C++ parser
[ ] APP_DIRECT_HAL_CALL 基于 syntax tree
[ ] ISR_BLOCKING_API 基于 syntax tree
[ ] comment/string false-positive 被消除
[ ] parse uncertainty → UNKNOWN
[ ] Cppcheck XML 严格解析
[ ] incomplete Cppcheck output → UNKNOWN
[ ] dependency-cycle regression PASS
[ ] MCUConfig mismatch regression PASS
[ ] M13 adversarial tests PASS
```

通过后：

```text
M13R = ACCEPTED
```

---

# 26. Task C — Project Scope Hardening

重点检查：

```text
apps/backend/src/eea_backend/api.py
apps/backend/src/eea_backend/document_repositories.py
apps/backend/src/eea_backend/repositories.py
application/src/eea_application/intelligence.py
core Document / Evidence model
tests/
OpenAPI
desktop generated API
```

同时全仓搜索：

```text
DocumentRepository.get(
EvidenceRepository.get(
DocumentService.get(
document_id
evidence_id
project_id=None
```

所有调用都必须审计。

---

# 27. Scope 基本规则

当前阶段先使用简单、明确的语义：

```text
project_id != None
→ PROJECT_PRIVATE

project_id == None
→ GLOBAL
```

不要本轮一次性实现：

```text
USER_PRIVATE
WORKSPACE_PRIVATE
PUBLIC_VERIFIED
```

完整知识权限系统。

那属于未来 Knowledge / ELKB 阶段。

但是当前 API 和 Repository 必须为未来扩展保留清晰边界。

---

# 28. Project-private lookup 必须携带 project_id

禁止：

```python
get(document_id)
```

作为 Project Resource 的最终访问方法。

应改成类似：

```python
get(
    document_id,
    *,
    project_id=project_id,
)
```

Evidence 同理。

Repository 查询必须直接包含：

```sql
WHERE
    id = ?
AND project_id = ?
```

不是：

```text
先按 ID 取出来
然后忘记检查
```

---

# 29. API 改造

项目 Document 推荐统一：

```text
GET /projects/{project_id}/documents/{document_id}
```

项目 Evidence：

```text
GET /projects/{project_id}/evidence/{evidence_id}
```

Project endpoint 内：

```text
project_id
```

必须是强制参数。

禁止 Project-private resource 继续依赖：

```text
?project_id=
```

可选 query 参数。

---

# 30. Legacy route

现有：

```text
GET /documents/{document_id}
GET /evidence/{evidence_id}
```

必须审查。

对于 PROJECT_PRIVATE resource，不允许通过它们绕过 scope。

如果当前确实没有公开全局资源 API 的必要：

```text
直接移除 legacy unscoped route
```

并同步：

```text
OpenAPI
TypeScript API
Tests
```

如果存在 Global resource 业务：

必须建立显式 global API，不能混用 Project endpoint。

例如未来可以：

```text
/global/documents/{document_id}
```

但不要为了兼容旧 API 而制造新的模糊作用域。

---

# 31. Document 全局 content_hash 去重问题

这是本任务必须修复的重点。

当前 Document persistence 不能因为：

```text
content_hash 相同
```

就把：

```text
Project A Document
```

直接返回给：

```text
Project B
```

即：

```text
same bytes
≠
same project metadata entity
```

正确模型：

```text
Blob deduplication
```

可以跨项目共享物理 bytes。

但：

```text
Document metadata
```

必须属于自己的作用域。

例如：

```text
Project A
Document A
content_hash = XYZ

Project B
Document B
content_hash = XYZ
```

这是合法的。

可以：

```text
Document A.storage_uri
Document B.storage_uri
```

都指向同一个 content-addressed blob。

但：

```text
Document A.id != Document B.id
Document A.project_id = A
Document B.project_id = B
```

---

# 32. Document 数据库约束修改

审查当前：

```text
content_hash UNIQUE
```

相关 schema。

如果它导致跨项目 metadata identity 合并：

必须移除这一全局 metadata 唯一语义。

最简单、安全的当前实现：

```text
DocumentRecord 可以存在多个相同 content_hash
content_hash 保留 INDEX
```

物理文件：

```text
data/documents/<sha256>.bin
```

仍然可以 deduplicate。

即：

```text
storage dedup
≠
metadata dedup
```

如果数据库结构改变：

**必须新增 Alembic migration。**

禁止直接修改 model 而没有 migration。

---

# 33. DocumentIR Isolation

DocumentIR 通过：

```text
document_id
```

关联。

因此 Project A/B 即使上传同一 PDF：

```text
Document A
Document B
```

也必须拥有独立逻辑 Document identity。

DocumentIR 不得因为 hash 相同跨项目直接复用 private metadata。

未来如果要共享解析缓存：

可以共享 immutable parsing artifact。

但：

```text
scope ownership
metadata
claims
evidence relations
```

仍必须隔离。

本轮不要提前设计复杂 ELKB shared cache。

---

# 34. Evidence Isolation

EvidenceRepository 禁止只有：

```python
get(evidence_id)
```

作为 Project-private lookup。

应提供：

```python
get(
    evidence_id,
    *,
    project_id: UUID,
)
```

Project A 请求：

```text
Evidence(project_id=B)
```

必须失败。

使用统一错误：

```text
KNOWLEDGE_SCOPE_DENIED
```

或当前项目定义的等价 scope-denied error。

禁止返回 Evidence 内容后再处理。

---

# 35. Service 层也必须强制 Scope

不能只依赖 API 路由。

因为未来：

```text
Agent
ContextBuilder
ELKB
Repository Intelligence
```

可能直接调用 Application Service。

因此：

```text
DocumentService
Evidence service / repository access
```

本身必须要求 Project Context。

原则：

```text
API protection
+
Application protection
+
Repository query protection
```

至少两层，不能仅靠前端。

---

# 36. 跨项目负向测试

必须新增：

```text
Project A
Project B
```

测试。

## SCOPE-01 Document Read

创建：

```text
Document A → Project A
```

调用：

```text
Project B / Document A
```

必须：

```text
DENIED
```

---

## SCOPE-02 Evidence Read

创建：

```text
Evidence A → Project A
```

Project B 请求：

```text
DENIED
```

---

## SCOPE-03 Same Content Upload

Project A 上传：

```text
test.pdf
hash = XYZ
```

Project B 上传完全相同 bytes。

必须：

```text
DocumentA.id != DocumentB.id
DocumentA.project_id == A
DocumentB.project_id == B
```

允许：

```text
storage hash/path 相同
```

---

## SCOPE-04 Direct Repository Access

Repository：

```text
get(documentA.id, project_id=B)
```

不得返回 A。

Evidence 同理。

---

## SCOPE-05 Service Access

Application Service 直接调用也必须拒绝跨项目。

不能只测试 HTTP。

---

## SCOPE-06 Unknown UUID

不存在 UUID 的行为保持稳定。

不得因为 Scope Hardening 导致服务器异常。

---

## SCOPE-07 Global Resource

如果当前保留 Global Document：

必须明确测试：

```text
global
project private
```

访问语义。

如果本阶段没有 Global Document API：

不要为了测试创造无意义公开入口。

---

# 37. Future ContextBuilder 安全不变量

虽然 ContextBuilder 不是本阶段主要实现对象，但此次修复必须形成以下 invariant：

```text
ContextBuilder(project=A)
```

默认只允许消费：

```text
A PROJECT_PRIVATE
+
明确允许的 GLOBAL
```

绝不能消费：

```text
B PROJECT_PRIVATE
```

未来实现 ContextBuilder 时必须能够复用现在的 scope semantics。

不要在本次提前开发完整 ContextBuilder。

---

# 38. API / Schema 同步要求

如果 API 路由修改：

必须同步：

```text
OpenAPI snapshot
TypeScript generated API
backend API tests
desktop typecheck
```

禁止出现：

```text
Backend route changed
Desktop generated client still是旧接口
```

---

# 39. Database Migration

若修改：

```text
DocumentRecord
unique constraint
index
scope column
foreign key
```

必须：

```text
Alembic revision
```

并测试：

```text
fresh DB upgrade head
existing DB upgrade
alembic check
```

禁止手工要求用户删除数据库重建。

---

# 40. 禁止的实现方式

本轮明确禁止以下做法。

### 禁止 1

```text
只修改测试，让现有代码 PASS
```

### 禁止 2

```text
删除 SandboxPolicy 中没实现的字段，
然后声称问题解决
```

正确方式是：

```text
真实实现
或 capability fail-closed
```

### 禁止 3

继续增加 regex 来修 regex。

例如：

```text
再加 20 个正则处理 comments
```

不接受。

### 禁止 4

把：

```text
UNKNOWN
```

变成：

```text
PASS
```

### 禁止 5

为了 Document dedup：

```text
Project B 直接复用 Project A 的 Document entity
```

### 禁止 6

仅在前端隐藏 Project B 数据。

隔离必须在 Backend / Application / Repository。

### 禁止 7

开始：

```text
M14
MotorControl Plugin
FOC
ELKB
Agent Runtime
```

这些不属于本任务。

### 禁止 8

大规模重写已经通过的：

```text
M7-M12
FirmwareIR
MCUConfigIR
CircuitIR
Schematic
```

除非修复本问题所必需。

---

# 41. 建议实施顺序

严格按照：

```text
Phase 0
Current State Audit

Phase 1
M5R Sandbox Runtime contract

Phase 2
Trusted executable identity

Phase 3
Resource / network / process / output enforcement

Phase 4
M5R adversarial tests

Phase 5
M13R syntax parser abstraction

Phase 6
APP_DIRECT_HAL_CALL migration

Phase 7
ISR_BLOCKING_API migration

Phase 8
Cppcheck XML strict parser

Phase 9
M13R adversarial tests

Phase 10
Document project scope

Phase 11
Evidence project scope

Phase 12
Document hash/storage dedup separation

Phase 13
Alembic migration

Phase 14
Cross-project negative tests

Phase 15
OpenAPI + TypeScript synchronization

Phase 16
Full regression

Phase 17
Reports + Acceptance
```

不要把三个模块同时改完以后才第一次测试。

---

# 42. 全量验证命令

Codex 必须根据仓库实际工具链执行等价检查。

至少包括：

```text
ruff check
ruff format --check
mypy
pytest
```

以及：

```text
alembic upgrade head
alembic check
OpenAPI export/check
TypeScript API generation/check
desktop lint
desktop typecheck
desktop build
```

如果现有 CI 中命令名称不同：

以：

```text
.github/workflows/ci.yml
```

为准。

---

# 43. Security Test 不能全部 Mock

允许：

```text
Unit Test mock Runtime
```

验证 capability routing。

但必须存在至少部分真实 integration test 验证：

```text
process termination
stream output cap
canonical executable identity
```

对于 OS-level capability：

如果当前 CI 不支持：

测试必须明确：

```text
SKIP: CAPABILITY_NOT_AVAILABLE
```

并证明 Production 行为是：

```text
fail closed
```

不能：

```text
测试 skip
+
生产 fallback 普通 subprocess
```

然后声称 Security PASS。

---

# 44. Regression 要求

本次加固不得破坏：

```text
Requirement
Architecture
HardwareIR
CircuitIR
Schematic
MCUConfigIR
FirmwareIR
Build
Component Registry
Existing static analysis structured rules
Desktop
API envelope
Error contract
```

已有测试全部必须继续 PASS。

---

# 45. 新增报告

完成后新增或更新：

```text
reports/M5R/TEST_REPORT.md
reports/M5R/KNOWN_ISSUES.md

reports/M13R/TEST_REPORT.md
reports/M13R/KNOWN_ISSUES.md

reports/PROJECT_SCOPE_HARDENING/TEST_REPORT.md
reports/PROJECT_SCOPE_HARDENING/KNOWN_ISSUES.md
```

并生成：

```text
reports/SECURITY_HARDENING_ACCEPTANCE.md
```

---

# 46. SECURITY_HARDENING_ACCEPTANCE.md 格式

至少包含：

```text
Repository:
Branch:
Commit SHA:

M5R:
IMPLEMENTED:
TESTED:
SECURITY_TESTED:
ACCEPTED:

M13R:
IMPLEMENTED:
TESTED:
ADVERSARIAL_TESTED:
ACCEPTED:

PROJECT_SCOPE_HARDENING:
IMPLEMENTED:
DB_MIGRATION:
CROSS_PROJECT_TESTED:
ACCEPTED:

CI:
BACKEND:
MIGRATION:
OPENAPI:
TYPESCRIPT:
DESKTOP:

Known P0:
Known P1:

READY_FOR_M14:
```

---

# 47. Acceptance Gate

必须同时：

```text
M5R = ACCEPTED
M13R = ACCEPTED
PROJECT_SCOPE_HARDENING = ACCEPTED
```

才可以：

```text
READY_FOR_M14 = YES
```

任何一个存在：

```text
P0 OPEN
P1 OPEN
security capability fake-enforced
scope bypass
parser uncertainty incorrectly PASS
```

都必须：

```text
READY_FOR_M14 = NO
```

---

# 48. 最终验收表

## Sandbox

```text
[ ] canonical executable identity
[ ] basename spoof blocked
[ ] symlink executable attack handled
[ ] network policy actually enforced or fail closed
[ ] memory policy enforced or fail closed
[ ] process policy enforced or fail closed
[ ] process tree terminated
[ ] output streaming cap
[ ] no unsafe subprocess downgrade
[ ] archive protections preserved
```

## M13

```text
[ ] AST/syntax parser introduced
[ ] regex no longer authoritative
[ ] comments ignored
[ ] strings ignored
[ ] actual HAL calls detected
[ ] actual ISR blocking calls detected
[ ] malformed source → UNKNOWN
[ ] Cppcheck XML structurally parsed
[ ] incomplete XML → UNKNOWN
[ ] diagnostics → FAIL
[ ] clean complete run → PASS
```

## Project Scope

```text
[ ] Document project-scoped get
[ ] Evidence project-scoped get
[ ] unscoped private routes removed/blocked
[ ] repository scope enforced
[ ] service scope enforced
[ ] same-content cross-project upload isolated
[ ] Document metadata no longer globally merged by hash
[ ] storage-level dedup remains possible
[ ] Alembic migration PASS
[ ] cross-project negative tests PASS
```

## Regression

```text
[ ] ruff PASS
[ ] format PASS
[ ] mypy PASS
[ ] pytest PASS
[ ] migration PASS
[ ] OpenAPI PASS
[ ] TypeScript client PASS
[ ] desktop lint PASS
[ ] desktop typecheck PASS
[ ] desktop build PASS
```

---

# 49. Codex 最终回复格式

任务完成以后，不要只回复：

```text
Done
```

必须严格给出：

```text
# EEA Hardening Result

## 1. Repository State
Branch:
Commit:
Previous HEAD:
Final HEAD:

## 2. M5R
Root Cause:
Files Changed:
Implementation:
Tests:
Status:

## 3. M13R
Root Cause:
Files Changed:
Implementation:
Tests:
Status:

## 4. Project Scope Hardening
Root Cause:
Files Changed:
Migration:
Implementation:
Tests:
Status:

## 5. Full Regression
Ruff:
Format:
Mypy:
Pytest:
Migration:
OpenAPI:
TypeScript:
Desktop:

## 6. Security Remaining Issues
P0:
P1:
P2:

## 7. Architecture Impact
Core Neutrality:
Project Isolation:
API Compatibility:

## 8. Gate
M5R:
M13R:
PROJECT_SCOPE_HARDENING:
READY_FOR_M14:
```

如果：

```text
READY_FOR_M14 = NO
```

必须明确写出阻塞原因。

---

# 50. 最终原则

本轮目标不是：

```text
代码看起来更复杂
```

而是确保三件事真正成立。

第一：

```text
Sandbox Policy
=
真实能够执行的 Security Boundary
```

不能只是字段。

第二：

```text
RELEASE_GATE PASS
=
有足够确定性证明没有发现对应违规
```

不能因为 regex 没匹配到就 PASS。

第三：

```text
Project A
永远不能意外读取、复用或污染
Project B 的 private engineering context
```

这三个基础能力修好以后，才进入：

```text
M14 Domain Extension Infrastructure
↓
M15 MotorControl Plugin
↓
Domain Composition
↓
FOC Minimal E2E
```

---

# 51. 本任务完成定义 Definition of Done

只有以下条件全部成立，本任务才结束：

```text
1. 三个问题均从根因层修复
2. adversarial tests 存在
3. cross-project tests 存在
4. fail-closed semantics 建立
5. DB migration 正常
6. API client 同步
7. full regression PASS
8. 报告与代码状态一致
9. 无 P0/P1 blocker
10. READY_FOR_M14 = YES
```

在此之前：

**禁止进入 M14。**