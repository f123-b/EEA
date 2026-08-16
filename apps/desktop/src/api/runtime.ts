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
