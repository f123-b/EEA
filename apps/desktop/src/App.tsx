const foundations = [
  "FastAPI service",
  "Alembic migrations",
  "Versioned OpenAPI",
  "React + Tauri shell",
] as const;

export function App() {
  const [runtime, setRuntime] = useState<"starting" | "ready" | "error" | "web">("starting");

  useEffect(() => {
    if (!("__TAURI_INTERNALS__" in window)) {
      setRuntime("web");
      return;
    }
    let active = true;
    void bootstrapRuntime()
      .then(() => {
        if (active) setRuntime("ready");
      })
      .catch(() => {
        if (active) setRuntime("error");
      });
    return () => {
      active = false;
    };
  }, []);

  const runtimeLabel = {
    starting: "Starting authenticated backend…",
    ready: "Backend ready · authenticated",
    error: "Backend runtime unavailable",
    web: "Desktop runtime available in the Tauri shell",
  }[runtime];

  return (
    <main className="shell">
      <section className="hero" aria-labelledby="product-title">
        <p className="eyebrow">EEA · Architecture Freeze 1.3</p>
        <h1 id="product-title">Embedded Engineering Agent</h1>
        <p className="summary">
          A verifiable engineering workspace built on IR, evidence, deterministic rules, and tool
          validation.
        </p>
        <div className="status" role="status">
          <span className="status-dot" aria-hidden="true" />
          {runtimeLabel}
        </div>
      </section>

      <section className="foundation" aria-labelledby="foundation-title">
        <h2 id="foundation-title">Foundation</h2>
        <ul>
          {foundations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="next">Next gated milestone: M2 AI Provider Foundation</p>
      </section>
    </main>
  );
}
import { useEffect, useState } from "react";

import { bootstrapRuntime } from "./api/runtime";
