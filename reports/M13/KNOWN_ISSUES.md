# M13 Known Issues

- Cppcheck 是可选外部工具。未安装或无法启动时，分析结果会是 `UNKNOWN`，这是设计的安全
  门禁行为，不是 PASS。
- M12/M12A 历史远程运行仍有 backend 失败记录；本次 M13 仅做本地实现与验证，未推送、未
  改写远程结果。
- Starlette/httpx 的 deprecation warning 仍来自依赖组合，不影响当前测试结果。
