import { useEffect, useState } from "react";

import { bootstrapConfiguredWebRuntime, bootstrapRuntime, type RuntimeBootstrap } from "./api/runtime";
import { createM21Api } from "./api/m21";
import { M21Workspace } from "./m21/M21Workspace";

type RuntimeState = "starting" | "ready" | "error" | "web";

export function App() {
  const [runtime, setRuntime] = useState<RuntimeState>("starting");
  const [bootstrap, setBootstrap] = useState<RuntimeBootstrap | null>(null);
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const isTauri = "__TAURI_INTERNALS__" in window;
        const configuredWeb = !isTauri ? await bootstrapConfiguredWebRuntime() : null;
        if (!isTauri && !configuredWeb) {
          if (active) setRuntime("web");
          return;
        }
        const session = configuredWeb ?? await bootstrapRuntime();
        if (active) {
          setBootstrap(session);
          setRuntime("ready");
        }
      } catch (error: unknown) {
        if (active) {
          setRuntime("error");
          setRuntimeError(error instanceof Error ? error.message : "Runtime bootstrap failed");
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  if (runtime === "starting") return <RuntimeSplash label="Starting authenticated backend…" />;
  if (runtime === "error") return <RuntimeSplash label={runtimeError ?? "Backend runtime unavailable"} error />;
  if (!bootstrap) return <WebRuntimeNotice />;
  return <M21Workspace api={createM21Api(bootstrap.client)} runtimeVersion={bootstrap.version} />;
}

function RuntimeSplash({ label, error = false }: { label: string; error?: boolean }) {
  return <main className="runtime-splash"><div className={`runtime-orb ${error ? "error" : ""}`}>EE</div><span className="eyebrow">EEA · M21 DESKTOP WORKBENCH</span><h1>{error ? "Backend session unavailable" : "Booting engineering workspace"}</h1><p>{label}</p>{error && <p className="muted">The Tauri runtime must start the loopback backend and complete the authenticated version handshake before the renderer can show project state.</p>}</main>;
}

function WebRuntimeNotice() {
  return <main className="runtime-splash"><div className="runtime-orb">EE</div><span className="eyebrow">EEA · RENDERER TEST MODE</span><h1>Desktop runtime is required for live project state.</h1><p>Launch the Tauri desktop package, or provide the explicit VITE_EEA_API_URL and VITE_EEA_SESSION_TOKEN values for a controlled renderer E2E session. No credential is persisted by the frontend.</p></main>;
}
