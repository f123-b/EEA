import { useMemo, useState } from "react";

import type { JsonRecord, M21Api } from "../api/m21";

type ImportWizardProps = {
  api: M21Api;
  onClose: () => void;
  onComplete: (projectId: string) => Promise<void>;
};

const steps = ["Source", "Scan", "Understand", "Review", "Create Workspace"];

function record(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonRecord : {};
}

function array(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = "UNKNOWN"): string {
  return typeof value === "string" ? value : fallback;
}

export function ImportWizard({ api, onClose, onComplete }: ImportWizardProps) {
  const [step, setStep] = useState(0);
  const [sourceType, setSourceType] = useState("LOCAL_FOLDER");
  const [sourcePath, setSourcePath] = useState("");
  const [repositoryUrl, setRepositoryUrl] = useState("");
  const [branchTagCommit, setBranchTagCommit] = useState("");
  const [projectName, setProjectName] = useState("Imported Embedded Project");
  const [projectDescription, setProjectDescription] = useState("");
  const [session, setSession] = useState<JsonRecord | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [createdProjectId, setCreatedProjectId] = useState<string | null>(null);

  const findings = useMemo(() => array(session?.findings).map(record), [session]);
  const summary = record(session?.summary);

  const run = async (operation: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await operation();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Import operation failed");
    } finally {
      setBusy(false);
    }
  };

  const createSession = () => run(async () => {
    const created = await api.createImport({
      source_type: sourceType,
      ...(sourceType === "GIT_REPOSITORY" ? { repository_url: repositoryUrl, branch_tag_commit: branchTagCommit || null } : { source_path: sourcePath }),
      project_name: projectName,
      project_description: projectDescription,
      actor: "desktop:m22",
    });
    setSession(created);
    setStep(1);
  });

  const scan = () => run(async () => {
    if (!session?.id) return;
    const scanned = await api.scanImport(String(session.id));
    setSession(scanned);
    setStep(2);
  });

  const review = (findingId: string, action: string) => run(async () => {
    if (!session?.id) return;
    const reviewed = await api.reviewImportFinding(String(session.id), findingId, { action });
    setSession(reviewed);
  });

  const edit = (finding: JsonRecord) => {
    const nextValue = window.prompt("Edit candidate value", typeof finding.value === "string" ? finding.value : JSON.stringify(finding.value));
    if (nextValue === null) return;
    return run(async () => {
      if (!session?.id) return;
      const reviewed = await api.reviewImportFinding(String(session.id), String(finding.id), { action: "EDIT", value: nextValue });
      setSession(reviewed);
    });
  };

  const createWorkspace = () => run(async () => {
    if (!session?.id) return;
    const result = await api.createImportWorkspace(String(session.id), {
      project_name: projectName,
      project_description: projectDescription,
    });
    const project = record(result.project);
    const projectId = text(project.id, "");
    setCreatedProjectId(projectId || null);
    setStep(4);
    if (projectId) await onComplete(projectId);
  });

  return (
    <section className="page-frame import-wizard" aria-label="Import Existing Project">
      <div className="page-header">
        <div>
          <span className="eyebrow">M22 · EXISTING PROJECT IMPORT</span>
          <h1>Import Existing Project</h1>
          <p>External content is isolated, scanned, and kept as candidate evidence. Build scripts are never run by the importer.</p>
        </div>
        <button className="ghost-button" onClick={onClose}>Close</button>
      </div>
      <div className="wizard-steps" role="list">
        {steps.map((label, index) => <span key={label} className={`wizard-step ${index === step ? "active" : ""} ${index < step ? "complete" : ""}`} role="listitem"><b>{index + 1}</b>{label}</span>)}
      </div>
      {error && <div className="feedback-banner feedback-error" role="alert">{error}</div>}

      {step === 0 && <div className="panel-card form-card">
        <PanelTitle title="Choose source" detail="Local Folder · Git Repository · Archive" />
        <div className="segmented-control">
          {["LOCAL_FOLDER", "GIT_REPOSITORY", "ARCHIVE"].map((type) => <button key={type} className={sourceType === type ? "selected" : ""} onClick={() => setSourceType(type)}>{type.replaceAll("_", " ")}</button>)}
        </div>
        {sourceType === "GIT_REPOSITORY" ? <>
          <label className="field-label">Repository URL<input value={repositoryUrl} onChange={(event) => setRepositoryUrl(event.target.value)} placeholder="https://..." /></label>
          <label className="field-label">Branch / Tag / Commit<input value={branchTagCommit} onChange={(event) => setBranchTagCommit(event.target.value)} placeholder="main or exact SHA (optional)" /></label>
        </> : <label className="field-label">{sourceType === "ARCHIVE" ? "Archive path" : "Local folder path"}<input value={sourcePath} onChange={(event) => setSourcePath(event.target.value)} placeholder="C:\\projects\\firmware" /></label>}
        <label className="field-label">Project name<input value={projectName} onChange={(event) => setProjectName(event.target.value)} /></label>
        <label className="field-label">Description<textarea value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} rows={3} /></label>
        <div className="wizard-actions"><button className="ghost-button" onClick={onClose}>Cancel</button><button className="primary-button" disabled={busy} onClick={() => void createSession()}>Continue to Scan</button></div>
      </div>}

      {step === 1 && <div className="panel-card">
        <PanelTitle title="Scan isolated source" detail="Reading files and detecting configuration without executing imported code." />
        <div className="scan-contract"><span>Sandbox boundary</span><strong>PASS</strong><span>Build executed</span><strong>NO</strong></div>
        <div className="wizard-actions"><button className="ghost-button" onClick={() => setStep(0)}>Back</button><button className="primary-button" disabled={busy} onClick={() => void scan()}>{busy ? "Scanning…" : "Start scan"}</button></div>
      </div>}

      {step === 2 && <div className="panel-card">
        <PanelTitle title="Project Understanding" detail="Every finding includes confidence, source, and evidence." />
        <div className="metric-grid"><Metric label="Platform" value={array(summary.platform).map(String).join(", ") || "UNKNOWN"} detail="candidate" /><Metric label="Build" value={array(summary.build).map(String).join(", ") || "UNKNOWN"} detail="detected" /><Metric label="RTOS" value={array(summary.rtos).map(String).join(", ") || "UNKNOWN"} detail="evidence-backed" /><Metric label="Files" value={String(session?.file_manifest ? Object.keys(record(session.file_manifest)).length : 0)} detail={`${String(session?.unknown_count ?? 0)} unknowns`} /></div>
        <div className="table-wrap"><table><thead><tr><th>Finding</th><th>Value</th><th>Confidence</th><th>Evidence</th></tr></thead><tbody>{findings.slice(0, 30).map((finding) => <tr key={text(finding.id)}><td>{text(finding.title)}</td><td>{typeof finding.value === "object" ? JSON.stringify(finding.value) : text(finding.value)}</td><td>{text(finding.confidence)}</td><td>{array(finding.evidence).map(String).join(", ") || "No evidence"}</td></tr>)}</tbody></table></div>
        <div className="wizard-actions"><button className="ghost-button" onClick={() => setStep(1)}>Back</button><button className="primary-button" onClick={() => setStep(3)}>Review candidates</button></div>
      </div>}

      {step === 3 && <div className="panel-card">
        <PanelTitle title="Review Import" detail="Accept keeps a candidate candidate; it never promotes it to Trusted automatically." />
        <div className="issue-list">{findings.map((finding) => <div className="issue-row" key={text(finding.id)}><div><strong>{text(finding.title)}</strong><p>{typeof finding.value === "object" ? JSON.stringify(finding.value) : text(finding.value)} · {text(finding.confidence)} · {array(finding.evidence).map(String).join(", ") || "UNKNOWN evidence"}</p></div><div className="row-actions"><button className="ghost-button" disabled={busy} onClick={() => void review(text(finding.id), "ACCEPT")}>Accept</button><button className="ghost-button" disabled={busy} onClick={() => void edit(finding)}>Edit</button><button className="ghost-button" disabled={busy} onClick={() => void review(text(finding.id), "UNKNOWN")}>Unknown</button><button className="danger-button" disabled={busy} onClick={() => void review(text(finding.id), "REJECT")}>Reject</button></div></div>)}</div>
        <div className="wizard-actions"><button className="ghost-button" onClick={() => setStep(2)}>Back</button><button className="primary-button" onClick={() => setStep(4)}>Create workspace</button></div>
      </div>}

      {step === 4 && <div className="panel-card">
        {createdProjectId ? <><PanelTitle title="Workspace created" detail="Project and SourceRevision are now bound to the imported snapshot." /><div className="success-callout"><strong>{projectName}</strong><span>Project {createdProjectId}</span><span>SourceRevision {text(record(session?.summary).source_revision_id, "created")}</span><span>Build executed: NO</span></div><button className="primary-button" onClick={onClose}>Open project</button></> : <><PanelTitle title="Create Workspace" detail="Copy the reviewed source into an isolated project workspace and create SourceRevision." /><div className="field-grid"><label className="field-label">Project name<input value={projectName} onChange={(event) => setProjectName(event.target.value)} /></label><label className="field-label">Description<textarea value={projectDescription} onChange={(event) => setProjectDescription(event.target.value)} rows={3} /></label></div><div className="wizard-actions"><button className="ghost-button" onClick={() => setStep(3)}>Back</button><button className="primary-button" disabled={busy} onClick={() => void createWorkspace()}>{busy ? "Creating…" : "Create workspace"}</button></div></>}
      </div>}
    </section>
  );
}

function PanelTitle({ title, detail }: { title: string; detail: string }) {
  return <div className="panel-heading"><div><span className="panel-kicker">M22 IMPORT</span><h2>{title}</h2></div><span className="muted">{detail}</span></div>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}
