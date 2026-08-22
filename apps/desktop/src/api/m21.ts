import type {
  ApiEnvelope,
  DomainActivationData,
  DomainAvailableData,
  DomainUIContribution,
  ProjectData,
} from "./generated";
import type { BackendClient } from "./client";

export type JsonRecord = Record<string, unknown>;

export type ProjectListData = {
  items: ProjectData[];
  next_cursor?: string | null;
};

export type M21DomainComposition = JsonRecord & {
  active_domain_ids?: string[];
  ui_contributions?: DomainUIContribution[];
  plan_hash?: string;
};

export type M21Status = "PASS" | "FAIL" | "BLOCKED" | "UNKNOWN" | "STALE" | "CURRENT" | "RUNNING";

export class BackendRequestError extends Error {
  readonly status: number;
  readonly code: string | null;
  readonly details: JsonRecord;

  constructor(message: string, status: number, code: string | null = null, details: JsonRecord = {}) {
    super(message);
    this.name = "BackendRequestError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMessage(body: unknown, fallback: string): { message: string; code: string | null; details: JsonRecord } {
  if (!isRecord(body) || !isRecord(body.error)) {
    return { message: fallback, code: null, details: {} };
  }
  const error = body.error;
  return {
    message: typeof error.message === "string" ? error.message : fallback,
    code: typeof error.code === "string" ? error.code : null,
    details: isRecord(error.details) ? error.details : {},
  };
}

export async function requestJson<T>(
  client: BackendClient,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await client.request(path, { ...init, headers });
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const parsed = errorMessage(body, `Backend request failed (${response.status})`);
    throw new BackendRequestError(parsed.message, response.status, parsed.code, parsed.details);
  }
  if (!isRecord(body) || body.success !== true || !("data" in body)) {
    throw new BackendRequestError("Backend returned an invalid API envelope", response.status);
  }
  return (body as unknown as ApiEnvelope<T>).data;
}

function pathForProject(projectId: string, suffix = ""): string {
  return `/api/v1/projects/${encodeURIComponent(projectId)}${suffix}`;
}

function jsonBody(value: unknown): BodyInit {
  return JSON.stringify(value);
}

export function createM21Api(client: BackendClient) {
  const get = <T>(path: string) => requestJson<T>(client, path);
  const post = <T>(path: string, payload: unknown) =>
    requestJson<T>(client, path, { method: "POST", body: jsonBody(payload) });
  const patch = <T>(path: string, payload: unknown) =>
    requestJson<T>(client, path, { method: "PATCH", body: jsonBody(payload) });

  return {
    listProjects: () => get<ProjectListData>("/api/v1/projects"),
    createProject: (payload: { name: string; description: string; metadata?: JsonRecord }) =>
      post<ProjectData>("/api/v1/projects", payload),
    createImport: (payload: JsonRecord) => post<JsonRecord>("/api/v1/imports", payload),
    getImport: (importId: string) => get<JsonRecord>(`/api/v1/imports/${encodeURIComponent(importId)}`),
    scanImport: (importId: string) => post<JsonRecord>(`/api/v1/imports/${encodeURIComponent(importId)}/scan`, {}),
    reviewImportFinding: (importId: string, findingId: string, payload: JsonRecord) =>
      patch<JsonRecord>(`/api/v1/imports/${encodeURIComponent(importId)}/findings/${encodeURIComponent(findingId)}`, payload),
    reviewImport: (importId: string, payload: JsonRecord) =>
      post<JsonRecord>(`/api/v1/imports/${encodeURIComponent(importId)}/review`, payload),
    createImportWorkspace: (importId: string, payload: JsonRecord = {}) =>
      post<JsonRecord>(`/api/v1/imports/${encodeURIComponent(importId)}/create-workspace`, payload),
    rescanImport: (importId: string) => post<JsonRecord>(`/api/v1/imports/${encodeURIComponent(importId)}/rescan`, {}),
    registerEvidence: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(`${pathForProject(projectId)}/evidence`, payload),
    getProject: (projectId: string) => get<ProjectData>(pathForProject(projectId)),
    getConsistency: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/consistency")),
    getDomains: (projectId: string) =>
      get<{ items: DomainActivationData[] }>(pathForProject(projectId, "/domains")),
    getAvailableDomains: (projectId: string) =>
      get<{ items: DomainAvailableData[] }>(pathForProject(projectId, "/domains/available")),
    getDomainComposition: (projectId: string) =>
      get<M21DomainComposition>(pathForProject(projectId, "/domains/composition")),
    getDomainExtensions: (projectId: string) =>
      get<{ items: DomainUIContribution[] }>(pathForProject(projectId, "/ui/extensions")),
    activateDomain: (projectId: string, domainId: string, configuration: JsonRecord = {}) =>
      post<DomainActivationData>(
        pathForProject(projectId, `/domains/${encodeURIComponent(domainId)}/activate`),
        { activated_by: "m21-desktop", configuration },
      ),
    deactivateDomain: (projectId: string, domainId: string) =>
      post<DomainActivationData>(
        pathForProject(projectId, `/domains/${encodeURIComponent(domainId)}/deactivate`),
        { activated_by: "m21-desktop", configuration: {} },
      ),
    getRequirementProfile: (name: string, version: string) =>
      get<JsonRecord>(`/api/v1/requirement-profiles/${encodeURIComponent(name)}/${encodeURIComponent(version)}`),
    analyzeRequirements: (payload: JsonRecord) =>
      post<JsonRecord>("/api/v1/requirements/analyze/structured", payload),
    analyzeNaturalLanguage: (payload: JsonRecord) =>
      post<JsonRecord>("/api/v1/requirements/analyze/natural-language", payload),
    getPinMap: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/pin-planner/map")),
    generatePinPlan: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/pin-planner/generate"), payload),
    validatePinPlan: (projectId: string, planId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/pin-planner/validate"), { plan_id: planId }),
    lockPinAssignment: (projectId: string, assignmentId: string, payload: JsonRecord) =>
      post<JsonRecord>(
        pathForProject(projectId, `/pin-planner/assignments/${encodeURIComponent(assignmentId)}/lock`),
        payload,
      ),
    generateArchitecture: (projectId: string, pinPlanId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/architecture/generate"), { pin_plan_id: pinPlanId }),
    getArchitecture: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/architecture")),
    generateCircuit: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/circuit/generate"), payload),
    getCircuit: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/circuit")),
    validateCircuit: (projectId: string, circuitId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/circuit/validate"), { circuit_id: circuitId }),
    generateSchematic: (projectId: string, circuitId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/schematic/generate"), { circuit_id: circuitId }),
    getSchematic: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/schematic")),
    validateSchematic: (projectId: string, schematicId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/schematic/validate"), { schematic_id: schematicId }),
    runErc: (projectId: string, schematicId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/schematic/erc/run"), { schematic_id: schematicId }),
    generateMcuConfig: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/mcu-config/generate"), payload),
    getMcuConfig: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/mcu-config")),
    validateMcuConfig: (projectId: string, configId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/mcu-config/validate"), { config_id: configId }),
    resolveDependencies: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/dependencies/resolve"), payload),
    getDependencies: (projectId: string) =>
      get<JsonRecord>(pathForProject(projectId, "/dependencies")),
    materializeDependencies: (projectId: string, lockId: string) =>
      post<JsonRecord[]>(pathForProject(projectId, "/dependencies/materialize"), { lock_id: lockId }),
    generateFirmware: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/firmware/generate"), payload),
    getFirmware: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/firmware")),
    build: (projectId: string, firmwareId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/build"), { firmware_id: firmwareId }),
    listBuilds: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/builds")),
    runStaticAnalysis: (projectId: string, firmwareId: string) =>
      post<JsonRecord>(pathForProject(projectId, "/analysis/static"), { firmware_id: firmwareId, run_cppcheck: true }),
    listStaticAnalyses: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/analysis/static")),
    createProtocol: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/protocol"), payload),
    getProtocol: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/protocol")),
    updateProtocol: (projectId: string, payload: JsonRecord) =>
      patch<JsonRecord>(pathForProject(projectId, "/protocol"), payload),
    validateProtocol: (projectId: string, payload: JsonRecord = {}) =>
      post<JsonRecord>(pathForProject(projectId, "/protocol/validate"), payload),
    generateProtocol: (projectId: string, payload: JsonRecord = {}) =>
      post<JsonRecord>(pathForProject(projectId, "/protocol/generate"), payload),
    sourceStatus: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/source/status")),
    sourceRevision: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/source/revision")),
    generateTests: (projectId: string, verificationProfile?: string) =>
      post<JsonRecord>(pathForProject(projectId, "/tests/generate"), verificationProfile ? { verification_profile: verificationProfile } : {}),
    listTests: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/tests")),
    listTestResults: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/tests/results")),
    runTests: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/tests/run"), payload),
    getCoverage: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/tests/coverage")),
    getTraceability: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/traceability")),
    runReview: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/review"), payload),
    listReviews: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/reviews")),
    listIssues: (projectId: string) => get<JsonRecord>(pathForProject(projectId, "/issues")),
    uploadDocument: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/documents"), payload),
    createEvidence: (projectId: string, payload: JsonRecord) =>
      post<JsonRecord>(pathForProject(projectId, "/evidence"), payload),
    getDevice: (deviceRef: string, packageName?: string) =>
      get<JsonRecord>(`/api/v1/devices/${encodeURIComponent(deviceRef)}${packageName ? `?package=${encodeURIComponent(packageName)}` : ""}`),
  };
}

export type M21Api = ReturnType<typeof createM21Api>;
