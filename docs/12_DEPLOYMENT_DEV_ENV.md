# Embedded Engineering Agent
## Deployment & Development Environment V1.3

# 1. 支持目标

Windows 11、Linux、Local Desktop、Backend Service、CI；后续 Docker/企业部署。

# 2. 工具链

Python 3.12+、Node.js LTS、pnpm、Rust stable、Tauri stable、Git、Docker/Podman。第三方工程工具版本由 ToolRegistry 探测，不在 Domain 硬编码。

# 3. Backend / Frontend

```bash
python -m venv .venv
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

pnpm install
pnpm dev
pnpm tauri dev
```

# 4. Config / Local Data

Config 层级 System Default < User Config < Project Override，Secret 独立。环境变量可 EEA_ENV/EEA_LOG_LEVEL/EEA_DATA_DIR/EEA_DB_URL。

Windows `%LOCALAPPDATA%/EEA/`；Linux `~/.local/share/eea/`，包含 db/objects/cache/logs/tool metadata/session metadata。

# 5. Tool Discovery

启动探测 kicad-cli/platformio/cmake/cppcheck/pyocd/openocd/renode。缺失不阻止 App 启动，由 `/capabilities` 告知前端。

# 6. Desktop Sidecar

Tauri → choose random loopback port → generate random session token → start FastAPI sidecar → health/auth handshake → frontend 通过 IPC 获得 token。Backend 只监听 loopback。

# 7. Sandbox

初期 Docker/Podman Adapter，接口 `SandboxService`，后续可替换 Windows Sandbox/VM/bwrap/firejail。

# 8. CI

Python lint/typecheck/unit/architecture/migration → Frontend typecheck/lint → OpenAPI client diff → Security → Import smoke → Artifact invalidation smoke → Benchmark smoke → Package build。

# 9. OpenAPI Client

CI 启动 Backend/export OpenAPI → generate TypeScript Client → generated code dirty 则 Fail。

# 10. Packaging / Service Deployment

Tauri 输出 Windows installer/Linux package。团队版：Web/Desktop → Backend → PostgreSQL/Qdrant/Object Storage/Worker/Sandbox Runner。V1.x 单机可单进程 JobExecutor。

# 11. Observability / Backup / Upgrade

Structured logs 使用 request_id/job_id/agent_run_id/tool_run_id/import_run_id/resource_lock_id，Secret redaction。单机 Project export + DB/Object/Qdrant snapshot；团队 PostgreSQL backup + Qdrant snapshot + Object versioning。

升级前 Compatibility Check、Migration Dry-run、Backup、Schema Migration、Plugin Compatibility、Knowledge index migration，失败可 rollback。

# 12. Offline Mode / Profiles

后续支持 local LLM/Embedding/cached Device DB/ERIS snapshot；Offline 时 OSDLE 停止。

推荐 dev profiles：minimal、foc-dev、full、ci。`foc-dev` 默认 KiCad、CMake/PlatformIO、Cppcheck、pyOCD、optional Renode。

# 13. V1.3 Profiles

`minimal`：Core + AIProvider mock/real selectable + no external execution。  
`foc-dev`：Core + builtin.motor_control + KiCad/CMake/PlatformIO/Cppcheck + Sandbox Foundation。  
`knowledge-dev`：Document/Embedding/ELKB/ERIS/Discovery adapters。  
`full`：全部已安装 capabilities。  
`ci`：固定 Tool versions + isolated sandbox + benchmark datasets。

外部 Repo/Build 测试默认走 Sandbox Foundation，不能因为本地开发方便而直接执行不可信脚本。

# 14. V1.3 Recovery / Desktop Security

App 启动：`Compatibility Check → DB Migration → Recovery Scan → Outbox Worker → Index Health → Tool Discovery → API Ready`。存在 unresolved hardware session、blocking migration 或关键一致性问题时进入 Recovery Mode。

Tauri package 强制 CSP、禁止任意 remote navigation、最小 IPC capability。CI 增加 crash/failure injection、backup-restore、Qdrant rebuild、workspace reconcile、renderer security。
