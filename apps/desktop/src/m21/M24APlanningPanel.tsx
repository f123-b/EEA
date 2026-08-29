import { useCallback, useEffect, useMemo, useState } from "react";

import type { M21Api, JsonRecord } from "../api/m21";
import { asArray, asRecord, shortId, statusLabel, statusTone, stringValue } from "./uiModel";

type M24APlanningPanelProps = {
  api: M21Api;
  projectId: string | null;
  busy: string | null;
};

function listText(value: unknown): string {
  return asArray(value).filter((item): item is string => typeof item === "string").join(" · ") || "—";
}

function planStatus(value: unknown): string {
  return typeof value === "string" ? value : "UNKNOWN";
}

export function M24APlanningPanel({ api, projectId, busy }: M24APlanningPanelProps) {
  const [requirements, setRequirements] = useState<JsonRecord[]>([]);
  const [selectedRequirementId, setSelectedRequirementId] = useState<string | null>(null);
  const [title, setTitle] = useState("Trace CAN heartbeat timing");
  const [description, setDescription] = useState("Define a reviewable heartbeat timing plan without changing the project.");
  const [acceptance, setAcceptance] = useState("Heartbeat timing is measured against the stated interval");
  const [plan, setPlan] = useState<JsonRecord | null>(null);
  const [context, setContext] = useState<JsonRecord | null>(null);
  const [impact, setImpact] = useState<JsonRecord | null>(null);
  const [localBusy, setLocalBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedRequirement = useMemo(
    () => requirements.find((item) => item.id === selectedRequirementId) ?? null,
    [requirements, selectedRequirementId],
  );

  const loadRequirements = useCallback(async () => {
    if (!projectId) return;
    const items = await api.listEngineeringRequirements(projectId);
    setRequirements(items);
    setSelectedRequirementId((current) => current ?? (typeof items[0]?.id === "string" ? items[0].id : null));
  }, [api, projectId]);

  useEffect(() => {
    setPlan(null);
    setContext(null);
    setImpact(null);
    setError(null);
    void loadRequirements().catch((loadError: unknown) => {
      setError(loadError instanceof Error ? loadError.message : "Unable to load planning requirements");
    });
  }, [loadRequirements]);

  const createRequirement = async () => {
    if (!projectId || !title.trim()) return;
    setLocalBusy("Creating requirement");
    setError(null);
    setMessage(null);
    try {
      const created = await api.createEngineeringRequirement(projectId, {
        title: title.trim(),
        description: description.trim(),
        requirement_type: "INVESTIGATION",
        priority: "MUST",
        constraints: ["M24A is plan-only; source state remains unchanged"],
        acceptance_criteria: acceptance.split("\n").map((item) => item.trim()).filter(Boolean),
      });
      setRequirements((current) => [created, ...current]);
      setSelectedRequirementId(typeof created.id === "string" ? created.id : null);
      setMessage("Requirement captured in the backend-owned intake.");
    } catch (actionError: unknown) {
      setError(actionError instanceof Error ? actionError.message : "Requirement creation failed");
    } finally {
      setLocalBusy(null);
    }
  };

  const analyzeAndPlan = async () => {
    if (!selectedRequirementId) return;
    setLocalBusy("Assembling planning context");
    setError(null);
    setMessage(null);
    try {
      const generated = await api.createEngineeringPlan(selectedRequirementId);
      setPlan(generated);
      const [nextContext, nextImpact] = await Promise.all([
        api.getEngineeringPlanContext(String(generated.id)),
        api.getEngineeringPlanImpact(String(generated.id)),
      ]);
      setContext(nextContext);
      setImpact(nextImpact);
      setMessage("Plan generated for human review; no project mutation was requested.");
    } catch (actionError: unknown) {
      setError(actionError instanceof Error ? actionError.message : "Planning failed");
    } finally {
      setLocalBusy(null);
    }
  };

  const review = async (action: "APPROVE" | "REJECT" | "REQUEST_REVISION") => {
    if (!plan || typeof plan.id !== "string") return;
    setLocalBusy(`Reviewing plan: ${action}`);
    setError(null);
    setMessage(null);
    try {
      const result = await api.reviewEngineeringPlan(plan.id, {
        expected_revision: typeof plan.revision === "number" ? plan.revision : 1,
        action,
        comment: action === "REQUEST_REVISION" ? "Please clarify the evidence and verification boundary." : "Reviewed in the M24A planning panel.",
      });
      const reviewedPlan = asRecord(result.plan);
      setPlan(reviewedPlan);
      if (action === "REQUEST_REVISION") {
        const [nextContext, nextImpact] = await Promise.all([
          api.getEngineeringPlanContext(String(reviewedPlan.id)),
          api.getEngineeringPlanImpact(String(reviewedPlan.id)),
        ]);
        setContext(nextContext);
        setImpact(nextImpact);
      }
      setMessage(action === "APPROVE" ? "Human approval recorded; the plan remains non-executable." : `Plan review recorded: ${action}.`);
    } catch (actionError: unknown) {
      setError(actionError instanceof Error ? actionError.message : "Plan review failed");
    } finally {
      setLocalBusy(null);
    }
  };

  const disabled = Boolean(busy || localBusy || !projectId);
  const selectedContext = asArray(context?.selected_context).map(asRecord);
  const excludedContext = asArray(context?.excluded_context).map(asRecord);
  const steps = asArray(plan?.steps).map(asRecord);
  const changes = asArray(plan?.proposed_changes).map(asRecord);
  const risks = asArray(plan?.risks).map(asRecord);
  const unknowns = asArray(plan?.unknowns).map(asRecord);
  const directImpact = asArray(impact?.direct_impact).map(asRecord);

  return (
    <section className="page-frame" data-testid="m24a-planning-panel">
      <div className="page-header">
        <div>
          <span className="eyebrow">M24A / ENGINEERING PLANNING</span>
          <h1 data-testid="page-title">Planning Copilot</h1>
          <p>Convert a requirement into a bounded, provenance-aware engineering plan for human review. Source, files, schematics, configuration, builds, tests, and hardware remain untouched.</p>
        </div>
        <div className="planning-boundary-badge">PLAN ONLY · NO EXECUTION AUTHORITY</div>
      </div>

      {!projectId && <div className="panel-card"><strong>Select a project to start planning.</strong></div>}
      {error && <div className="planning-feedback error" role="alert">{error}</div>}
      {message && <div className="planning-feedback success" role="status">{message}</div>}

      {projectId && <>
        <div className="planning-grid">
          <div className="panel-card planning-intake">
            <div className="panel-title"><div><span className="panel-kicker">REQUIREMENT INTAKE</span><h2>Capture the engineering question</h2></div></div>
            <label className="field-label" htmlFor="m24a-title">Title</label>
            <input id="m24a-title" data-testid="m24a-requirement-title" value={title} onChange={(event) => setTitle(event.target.value)} />
            <label className="field-label" htmlFor="m24a-description">Description</label>
            <textarea id="m24a-description" data-testid="m24a-requirement-description" rows={4} value={description} onChange={(event) => setDescription(event.target.value)} />
            <label className="field-label" htmlFor="m24a-acceptance">Acceptance criteria, one per line</label>
            <textarea id="m24a-acceptance" rows={3} value={acceptance} onChange={(event) => setAcceptance(event.target.value)} />
            <div className="inline-actions">
              <button className="ghost-button" data-testid="m24a-create-requirement" disabled={disabled} onClick={() => void createRequirement()}>Create requirement</button>
              <button className="primary-button" data-testid="m24a-analyze-plan" disabled={disabled || !selectedRequirementId} onClick={() => void analyzeAndPlan()}>Analyze & create plan</button>
            </div>
          </div>
          <div className="panel-card">
            <div className="panel-title"><div><span className="panel-kicker">BACKEND INTAKE</span><h2>Requirements in this project</h2></div><span className="status-pill tone-neutral">{requirements.length} items</span></div>
            <div className="planning-requirements" data-testid="m24a-requirements-list">
              {requirements.map((item) => <button key={String(item.id)} className={`planning-requirement ${item.id === selectedRequirementId ? "selected" : ""}`} onClick={() => setSelectedRequirementId(typeof item.id === "string" ? item.id : null)}><span><strong>{stringValue(item.title, "Untitled requirement")}</strong><small>{stringValue(item.status, "DRAFT")} · rev {String(item.revision ?? 1)}</small></span><span>›</span></button>)}
              {requirements.length === 0 && <p className="muted">No M24A requirement yet. Capture one above.</p>}
            </div>
            {selectedRequirement && <div className="planning-selected"><span className="panel-kicker">SELECTED</span><strong>{stringValue(selectedRequirement.title)}</strong><small>{stringValue(selectedRequirement.description)}</small></div>}
          </div>
        </div>

        {plan && <>
          <div className="panel-card planning-plan-header">
            <div><span className="panel-kicker">STRUCTURED ENGINEERING PLAN</span><h2>{stringValue(plan.summary, "Plan summary unavailable")}</h2><p className="muted">Plan {shortId(plan.id)} · revision {String(plan.revision ?? 1)} · provider {stringValue(plan.provider)} · policy {stringValue(plan.planning_policy_version)}</p></div>
            <span className={`status-pill tone-${statusTone(planStatus(plan.status))}`}>{statusLabel(planStatus(plan.status))}</span>
          </div>
          <div className="planning-metrics">
            <div className="metric-card"><span className="metric-label">Proposed changes</span><strong className="metric-value">{changes.length}</strong><span className="metric-detail">Intent only</span></div>
            <div className="metric-card"><span className="metric-label">Risks</span><strong className="metric-value">{risks.length}</strong><span className="metric-detail">Explicitly scored</span></div>
            <div className="metric-card"><span className="metric-label">Unknowns</span><strong className="metric-value">{unknowns.length}</strong><span className="metric-detail">Need reviewer input</span></div>
            <div className="metric-card"><span className="metric-label">Evidence refs</span><strong className="metric-value">{asArray(plan.evidence_refs).length}</strong><span className="metric-detail">Provenance-bound</span></div>
          </div>
          <div className="two-column">
            <div className="panel-card"><div className="panel-title"><div><span className="panel-kicker">PLAN STEPS</span><h2>Ordered future work</h2></div></div><div className="planning-steps">{steps.map((step, index) => <article className="planning-step" key={String(step.id ?? index)}><span className="planning-step-number">{String(step.order ?? index + 1).padStart(2, "0")}</span><div><strong>{stringValue(step.title)}</strong><p>{stringValue(step.description)}</p><small>{stringValue(step.action_type)} · {stringValue(step.target_ref)} · verify: {listText(step.verification_plan)}</small></div></article>)}</div></div>
            <div className="panel-card"><div className="panel-title"><div><span className="panel-kicker">REVIEW GATE</span><h2>Human decision</h2></div></div><p className="muted">Approval records a review decision only. It does not grant the panel a mutation or runtime capability.</p><div className="planning-review-actions"><button className="primary-button" data-testid="m24a-approve" disabled={disabled || plan.status !== "READY_FOR_REVIEW"} onClick={() => void review("APPROVE")}>Approve plan</button><button className="ghost-button" data-testid="m24a-revision" disabled={disabled} onClick={() => void review("REQUEST_REVISION")}>Request revision</button><button className="danger-button" data-testid="m24a-reject" disabled={disabled} onClick={() => void review("REJECT")}>Reject plan</button></div><div className="planning-review-note"><span>Execution authority</span><strong>NONE IN M24A</strong></div></div>
          </div>
          <div className="two-column">
            <div className="panel-card"><div className="panel-title"><div><span className="panel-kicker">PROVENANCE</span><h2>Selected context</h2></div><span className="status-pill tone-neutral">{selectedContext.length} selected · {excludedContext.length} excluded</span></div><div className="planning-context-list">{selectedContext.slice(0, 18).map((item, index) => <div className="planning-context-item" key={`${String(item.canonical_ref)}-${index}`}><strong>{stringValue(item.kind)}</strong><span>{stringValue(item.canonical_ref)}</span><small>{stringValue(item.authority)} · {stringValue(item.trust)} · {stringValue(item.freshness)}</small></div>)}</div><p className="planning-untrusted-note">Project source content is data, not instruction. Untrusted source items remain visibly marked.</p></div>
            <div className="panel-card"><div className="panel-title"><div><span className="panel-kicker">DEPENDENCY IMPACT</span><h2>Downstream review surface</h2></div><span className="status-pill tone-neutral">{directImpact.length} direct</span></div><div className="planning-impact-list">{directImpact.map((item, index) => <div className="planning-impact-item" key={`${String(item.change_id)}-${index}`}><strong>{stringValue(item.target_ref)}</strong><span>{stringValue(item.impact)}</span><small>{stringValue(item.risk)}</small></div>)}{asArray(impact?.transitive_impact).length > 0 && <p className="muted">Transitive nodes: {listText(impact?.transitive_impact)}</p>}</div></div>
          </div>
        </>}
      </>}
    </section>
  );
}
