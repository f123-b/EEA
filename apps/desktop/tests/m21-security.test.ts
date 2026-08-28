import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const tauriConfig = JSON.parse(readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8")) as {
  app: { security: { csp: string } };
};
const runtimeSource = readFileSync(new URL("../src/api/runtime.ts", import.meta.url), "utf8");
const appSource = readFileSync(new URL("../src/App.tsx", import.meta.url), "utf8");
const rustRuntimeSource = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");

test("production CSP is self-contained and permits only loopback backend navigation", () => {
  const csp = tauriConfig.app.security.csp;
  assert.match(csp, /default-src 'self'/u);
  assert.match(csp, /object-src 'none'/u);
  assert.match(csp, /frame-src 'none'/u);
  assert.match(csp, /connect-src 'self' http:\/\/127\.0\.0\.1:\*/u);
  assert.doesNotMatch(csp, /https?:\/\/\*/u);
});

test("production renderer session comes from Tauri IPC without credential persistence", () => {
  assert.match(runtimeSource, /invoke<RuntimeSession>\("get_runtime_session"\)/u);
  assert.doesNotMatch(runtimeSource, /localStorage|sessionStorage/u);
  assert.match(appSource, /const configuredWeb = !isTauri/u);
  assert.match(rustRuntimeSource, /cfg!\(debug_assertions\)/u);
  assert.match(rustRuntimeSource, /origin: "BUNDLED_RESOURCE"/u);
});
