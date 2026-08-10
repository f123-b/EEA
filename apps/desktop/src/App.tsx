const foundations = [
  "FastAPI service",
  "Alembic migrations",
  "Versioned OpenAPI",
  "React + Tauri shell",
] as const;

export function App() {
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
          M0 repository skeleton ready
        </div>
      </section>

      <section className="foundation" aria-labelledby="foundation-title">
        <h2 id="foundation-title">Foundation</h2>
        <ul>
          {foundations.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <p className="next">Next gated milestone: M1 Core Domain</p>
      </section>
    </main>
  );
}
