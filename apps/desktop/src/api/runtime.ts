import { invoke } from "@tauri-apps/api/core";

import { createBackendClient, type BackendClient } from "./client";

export type RuntimeSession = Readonly<{
  backend_url: string;
  session_token: string;
}>;

export type RuntimeBootstrap = Readonly<{
  client: BackendClient;
  version: unknown;
}>;

export type RendererSmokeState = Readonly<{
  renderer_ready: boolean;
  workbench_ready: boolean;
  url_clean: boolean;
  storage_clean: boolean;
  dom_clean: boolean;
}>;

type DesktopImportMeta = ImportMeta & {
  env?: Record<string, string | undefined>;
};

/** Obtain the Tauri-managed session; the token stays in this closure-owned path. */
export async function loadRuntimeSession(): Promise<RuntimeSession> {
  return invoke<RuntimeSession>("get_runtime_session");
}

/** Prove the complete Tauri → backend → renderer bearer path before rendering ready state. */
export async function bootstrapRuntime(): Promise<RuntimeBootstrap> {
  const session = await loadRuntimeSession();
  const client = createBackendClient(session.backend_url, session.session_token);
  const response = await client.request("/api/v1/meta/version");
  if (!response.ok) {
    throw new Error(`backend readiness request failed (${response.status})`);
  }
  return { client, version: await response.json() };
}

/** Test-only observation hook. Rust ignores it unless the packaged smoke evidence env is set. */
export async function reportDesktopSmokeReady(rendererState: RendererSmokeState): Promise<boolean> {
  return invoke<boolean>("record_desktop_smoke_ready", { rendererState });
}

/**
 * Renderer E2E/dev path. Production desktop sessions still come only from Tauri IPC;
 * this opt-in path requires both values at build time and never persists the token.
 */
export async function bootstrapConfiguredWebRuntime(): Promise<RuntimeBootstrap | null> {
  const env = (import.meta as DesktopImportMeta).env ?? {};
  const backendUrl = env.VITE_EEA_API_URL;
  const sessionToken = env.VITE_EEA_SESSION_TOKEN;
  if (!backendUrl || !sessionToken) {
    return null;
  }
  const client = createBackendClient(backendUrl, sessionToken);
  const response = await client.request("/api/v1/meta/version");
  if (!response.ok) {
    throw new Error(`backend readiness request failed (${response.status})`);
  }
  return { client, version: await response.json() };
}
