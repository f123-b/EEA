import { useState } from "react";

import type { JsonRecord, M21Api } from "../api/m21";
import { useI18n } from "../i18n";
import { asArray, asRecord, shortId, statusTone, stringValue } from "./uiModel";

function memoryItems(value: unknown): JsonRecord[] {
  return asArray(value).map(asRecord);
}

export function MemoryPanel({ api, projectId }: { api: M21Api; projectId: string }) {
  const { text } = useI18n();
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<JsonRecord[]>([]);
  const [auditId, setAuditId] = useState<string | null>(null);
  const [includeNonActive, setIncludeNonActive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const recall = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.recallMemory({
        project_id: projectId,
        actor_ref: "desktop:m23",
        scope_context: ["GLOBAL_PUBLIC", "PROJECT_PRIVATE"],
        query,
        limit: 8,
        include_non_active: includeNonActive,
      });
      setItems(memoryItems(result.items));
      setAuditId(stringValue(result.audit_id) || null);
    } catch (recallError: unknown) {
      setError(recallError instanceof Error ? recallError.message : text("Memory recall failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel-card memory-panel" data-testid="memory-panel">
      <div className="panel-heading">
        <span className="panel-kicker">{text("M23 MEMORY")}</span>
        <span className="ai-spark" aria-hidden="true">⌁</span>
      </div>
      <h3>{text("Knowledge & Memory")}</h3>
      <p className="muted">{text("Recall reviewed project knowledge without creating a second source of truth.")}</p>
      <div className="memory-search">
        <input
          aria-label={text("Memory query")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => { if (event.key === "Enter") void recall(); }}
          placeholder={text("Search project memory")}
        />
        <button className="ghost-button" data-testid="memory-recall" disabled={busy} onClick={() => void recall()}>
          {busy ? text("Recalling…") : text("Recall")}
        </button>
      </div>
      <label className="memory-history-toggle">
        <input
          type="checkbox"
          data-testid="memory-include-history"
          checked={includeNonActive}
          onChange={(event) => setIncludeNonActive(event.target.checked)}
        />
        {text("Include stale and conflicted history")}
      </label>
      {error && <p className="feedback-inline error-text">{error}</p>}
      {items.length === 0 ? (
        <p className="muted memory-empty">{text("No memory recalled yet.")}</p>
      ) : (
        <div className="memory-results">
          {items.map((item, index) => {
            const entry = asRecord(item.entry);
            const lifecycle = stringValue(entry.lifecycle, "UNKNOWN");
            const provenance = asRecord(entry.provenance);
            const freshness = asRecord(entry.freshness);
            const claimIds = asArray(provenance.canonical_claim_ids);
            const evidenceIds = asArray(provenance.evidence_ids);
            return (
              <article className="memory-result" key={stringValue(entry.id, String(index))}>
                <div className="memory-result-header">
                  <strong>{stringValue(entry.title, text("Untitled memory"))}</strong>
                  <span className={`status-pill tone-${statusTone(lifecycle)}`}>{lifecycle}</span>
                </div>
                <p>{stringValue(entry.summary, text("No summary"))}</p>
                <small>
                  {stringValue(entry.scope)} · {stringValue(entry.knowledge_type)} · {text("score")} {stringValue(item.score)} · {text("freshness")} {stringValue(freshness.status, stringValue(item.freshness_status, "UNKNOWN"))}
                </small>
                {stringValue(item.stale_reason) && <small className="error-text">{stringValue(item.stale_reason)}</small>}
                <div className="memory-provenance" data-testid="memory-provenance">
                  <small>{text("Canonical claims")}: {claimIds.length ? claimIds.map((value) => shortId(value)).join(", ") : text("none")}</small>
                  <small>{text("Evidence")}: {evidenceIds.length ? evidenceIds.map((value) => shortId(value)).join(", ") : text("none")}</small>
                  <small>{text("Source revision")}: {shortId(provenance.source_revision_id, 16)}</small>
                  <small>{text("Origin")}: {stringValue(provenance.origin, "manual")}</small>
                </div>
              </article>
            );
          })}
        </div>
      )}
      {auditId && <small className="muted">{text("Recall audit")}: {auditId.slice(0, 12)}…</small>}
    </section>
  );
}
