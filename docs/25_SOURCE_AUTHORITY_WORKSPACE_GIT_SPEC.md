# Embedded Engineering Agent
## Source Authority, Workspace & Git Specification V1.3

# 1. 目的

明确 FirmwareIR、Generated Source、Git Working Tree、Artifact、BuildResult 的权威关系，防止 AI edit、手工 edit、RepairAgent、Generator 形成多套互相覆盖的“源码事实源”。

# 2. Source of Truth

```text
Requirements / IR
      ↓ generation intent
Generated Source Candidate
      ↓ accepted/applied
Git Working Tree  ← 源码实际可编辑 SSOT
      ↓ commit
SourceRevision
      ↓ build
BuildRun / Binary Artifact
```

FirmwareIR 是结构/设计事实源，不是用户源码字节的最终事实源。
Artifact 保存不可变快照/生成物/Build 结果，不替代 Git Working Tree。

# 3. SourceRevision

至少：

- project_id
- repository_id
- commit_sha (nullable for working-tree snapshot)
- tree_hash
- dirty
- base_commit
- workspace_revision
- source_manifest_hash
- created_by / created_at

所有 Build/Test/Review/AgentPatch 绑定 SourceRevision。

# 4. Write Path

任何源码修改：

```text
SafePath
→ Symlink/Workspace boundary check
→ Permission
→ Expected content hash / ETag
→ Git dirty/base check
→ Apply to temp
→ Diff
→ Optional syntax/static validation
→ Atomic replace
→ workspace_revision++
→ Outbox SourceChanged
→ Impact Analysis
```

# 5. AI Edit

AI 不直接写磁盘。AI 生成 PatchProposal：

- base SourceRevision
- affected files
- unified diff/structured edits
- rationale/evidence
- expected impact
- required build/tests

用户或 Repair Workflow apply 后才改变 Working Tree。

# 6. Generator

Generator 对已存在用户代码默认产生 candidate/diff，除非文件标记为 generated-owned。Generated-owned 文件必须有 generator marker/version/input hash，用户改动后进入 diverged 状态，禁止静默覆盖。

# 7. Git

Repair 默认：

`new branch → patch → diff → build/test/review → commit`

Destructive Git 仍需 Permission。Import 项目可选择 external repo mirror/worktree 模式，但所有路径必须受 Workspace Boundary 管理。

# 8. API

文件读取返回 content_hash/SourceRevision/ETag。写入必须提交 expected hash 或 If-Match。

推荐：

```http
GET  /projects/{id}/source/status
GET  /projects/{id}/source/revision
GET  /projects/{id}/source/files/content?path=
POST /projects/{id}/source/patch-proposals
POST /patch-proposals/{id}/apply
GET  /patch-proposals/{id}/diff
POST /projects/{id}/source/commit
```

旧 firmware files write API 映射到 Source Service，不允许绕过安全路径。

# 9. Artifact

Source snapshot、generated output、binary、map、ELF、reports 可成为 Artifact。Artifact 不可变；修改等于创建新版本。

# 10. Acceptance

- concurrent edit → 409
- stale PatchProposal 不可直接 apply
- symlink escape reject
- AI edit 不能绕过 diff
- generator 不能覆盖 diverged user file
- Build 必须绑定精确 SourceRevision
- crash 后 Workspace/DB 可 reconcile
