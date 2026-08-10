# Embedded Engineering Agent
## Security & Permission Specification V1.3

# 1. 威胁模型

EEA 会读源码、Clone Repo、运行编译器、解析文档、执行 Build Script、连串口/CAN、烧录 MCU、控制仪器、保存 API Key。假设外部仓库/文件可恶意、README 可 Prompt Injection、Build Script 可执行任意命令、Plugin 可越权、多项目可泄漏、本机其他进程可攻击 local backend。

# 2. 原则

Least privilege、deny by default、explicit permission、sandbox untrusted execution、secrets never in prompts、project isolation、auditable side effects、resource locking、human confirmation。

# 3. Permission / Risk

Permission：READ、WRITE、BUILD、NETWORK、SECRET_USE、FLASH、DEBUG、HARDWARE_CONTROL、DELETE、PLUGIN_INSTALL、KNOWLEDGE_PROMOTE、EXPORT_PRIVATE。

LOW：读公开数据/纯验证。MEDIUM：修改项目/trusted build。HIGH：sandbox network/private credential/flash/memory write/hardware control/delete/global promotion/destructive Git。

# 4. Secret

LLM API Key、Git token、SSH、private registry、instrument credential。前端仅显示 configured + masked。AgentContext 默认不含 Secret，Backend 在 Tool Adapter 执行时注入，LLM 不看到真实值。

# 5. Repository Prompt Injection / Sandbox

Repository content 永远作为 untrusted data。Sandbox 默认 no host home/no SSH agent/no API token/no user project mount/read-only base/writable temp/process+CPU+RAM+timeout limit/network off or allowlist。

公共 Repo 的 Make/CMake/Python hook 不可信，依赖下载走 controlled resolver/allowlist/cache。

# 6. Path / Shell / Upload

防 `../`、absolute breakout、symlink escape、UNC/Windows drive escape、archive traversal。禁止 Agent 自由 `shell=True`，优先 structured argv/predefined command template。Upload 做 MIME/extension/size/archive bomb/filename normalize/safe extraction。

# 7. Plugin Security

Manifest 声明 permissions/network/filesystem/dependencies/entrypoint/publisher，未声明能力不得调用。企业可禁止未签名 Plugin。

# 8. Knowledge Privacy / Logs

Private → broader scope 必须 policy/redaction/license/approval。日志禁止 API key/token/private key/secret env/proprietary full source；必要时保存 hash/reference。

# 9. Hardware Safety

FLASH/HARDWARE_CONTROL 必须显示 target/device identity/firmware hash/probe/expected effect，并要求 Permission Token + Resource Lock + timeout。仪器后续增加 voltage/current hard limits、emergency stop、watchdog。

# 10. Destructive Git

Hard reset、force push、delete unmerged branch、clean、overwrite user changes 必须确认。AI Repair 默认新 branch。

# 11. Desktop Local Backend Security

Tauri + FastAPI sidecar 必须：仅绑定 loopback；动态随机端口；每次启动 256-bit session secret；前端通过 Tauri IPC 获取；REST Bearer；WS 握手鉴权；broad CORS 关闭；不监听 LAN；token 不写日志；退出即失效。

# 12. Resource Lock

FLASH/DEBUG/HARDWARE_CONTROL 前 acquire → verify target → execute → release。同一 probe/device 不允许并发控制。

# 13. Auth/RBAC / Audit

团队版 OIDC/OAuth + Organization + Project Role：Viewer/Engineer/Maintainer/Admin。审计 permission、flash、hardware control、secret use、plugin install、global promotion、destructive Git、export、force lock release、override critical。

# 14. Security Tests

覆盖 repository prompt injection、path traversal、symlink escape、secret log leak、cross-project leak、sandbox secret access、permission bypass、malicious plugin、idempotency replay、local backend unauthorized access、WS auth bypass、resource lock bypass。

# 15. Plugin Trust Tier

- Bundled Trusted Plugin：可在受控策略下 In-Process。
- Signed Trusted Plugin：按组织策略决定 In-Process/Out-of-Process。
- Community/Untrusted Plugin：必须 Out-of-Process + Sandbox，不能仅靠 Manifest Permission 作为安全边界。

V1.3 首发只要求 Bundled Trusted Domain Plugin 完整可用；第三方 Marketplace 不作为 Release 必需能力。

# 16. ELKB Source Safety / Copyright

Learning Document、课程资料、论文、Blog 同样视为外部不可信输入，防 Prompt Injection/恶意文件。用户私有资料不进入公共索引；Technical Knowledge Discovery 必须检查 license/storage/extraction policy。

# 17. Desktop Renderer / WebView Security

EEA 渲染 README、Repository docs、ELKB、Issue/Log 等不可信内容时必须 sanitize Markdown/HTML、strict CSP、deny arbitrary remote navigation、external URL isolation、最小 Tauri capability allowlist、禁止 remote JS plugin，并隔离 backend token/secret。

# 18. Actuator Safety Permission

新增 `ACTUATOR_ENABLE` 或等价高风险 capability。FLASH 与 ACTUATOR_ENABLE 分离；Emergency Stop 后重新使能需重新通过审批/策略检查。
