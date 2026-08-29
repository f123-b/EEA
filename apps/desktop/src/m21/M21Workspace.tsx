import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { DomainActivationData, DomainAvailableData, DomainUIContribution, ProjectData } from "../api/generated";
import { BackendRequestError, type EngineeringDataState, type JsonRecord, type M21Api } from "../api/m21";
import { useI18n } from "../i18n";
import {
  M20_PROFILE_NAME,
  M20_PROFILE_VERSION,
  m20CircuitPayload,
  m20DependencyResolvePayload,
  m20DeviceFirmwarePayload,
  m20EvidencePayloads,
  m20McuConfigPayload,
  m20PinPlanPayload,
  m20ProtocolPayload,
  m20RequirementPayload,
} from "./benchmark";
import {
  asArray,
  asRecord,
  buildNavigation,
  numberValue,
  routeFromLocation,
  shortId,
  statusFrom,
  statusLabel,
  statusTone,
  stringValue,
  workflowStages,
  type NavigationItem,
} from "./uiModel";
import { ImportWizard } from "./ImportWizard";
import { MemoryPanel } from "./MemoryPanel";
import { M24APlanningPanel } from "./M24APlanningPanel";

type WorkflowState = {
  analysis: JsonRecord | null;
  pinPlan: JsonRecord | null;
  architecture: JsonRecord | null;
  circuit: JsonRecord | null;
  schematic: JsonRecord | null;
  erc: JsonRecord | null;
  mcuConfig: JsonRecord | null;
  dependencyLock: JsonRecord | null;
  dependencyMaterialization: JsonRecord[];
  firmware: JsonRecord | null;
  build: JsonRecord | null;
  staticAnalysis: JsonRecord | null;
  protocol: JsonRecord | null;
  protocolOutputs: JsonRecord | null;
  tests: JsonRecord | null;
  testRun: JsonRecord | null;
  traceability: JsonRecord | null;
  review: JsonRecord | null;
};

type ProjectContext = {
  domains: JsonRecord[];
  availableDomains: JsonRecord[];
  extensions: DomainUIContribution[];
  consistency: JsonRecord | null;
  issues: JsonRecord[];
  latestBuild: JsonRecord | null;
  latestTestRun: JsonRecord | null;
  latestReview: JsonRecord | null;
  source: JsonRecord | null;
};

const emptyWorkflow: WorkflowState = {
  analysis: null,
  pinPlan: null,
  architecture: null,
  circuit: null,
  schematic: null,
  erc: null,
  mcuConfig: null,
  dependencyLock: null,
  dependencyMaterialization: [],
  firmware: null,
  build: null,
  staticAnalysis: null,
  protocol: null,
  protocolOutputs: null,
  tests: null,
  testRun: null,
  traceability: null,
  review: null,
};

const emptyContext: ProjectContext = {
  domains: [],
  availableDomains: [],
  extensions: [],
  consistency: null,
  issues: [],
  latestBuild: null,
  latestTestRun: null,
  latestReview: null,
  source: null,
};

function firstRecord(value: unknown): JsonRecord | null {
  const item = asArray(value)[0];
  return item ? asRecord(item) : null;
}

function nestedRecord(value: unknown, key: string): JsonRecord {
  return asRecord(asRecord(value)[key]);
}

function displayCount(value: unknown): string {
  return typeof value === "number" ? value.toLocaleString() : "0";
}

function asStatus(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

async function registerM20Evidence(api: M21Api, projectId: string): Promise<JsonRecord> {
  const entries = await Promise.all(Object.entries(m20EvidencePayloads).map(async ([key, payload]) => {
    const evidence = await api.registerEvidence(projectId, payload);
    return [key, evidence.id] as const;
  }));
  return Object.fromEntries(entries);
}

function getWorkflowStageStatus(workflow: WorkflowState, index: number): string {
  const stages: Array<JsonRecord | null> = [
    workflow.analysis,
    workflow.pinPlan,
    workflow.architecture ?? workflow.circuit,
    workflow.erc ?? workflow.schematic,
    workflow.mcuConfig,
    workflow.firmware,
    workflow.build,
    workflow.staticAnalysis,
    workflow.protocol,
    workflow.testRun ?? workflow.tests,
    workflow.traceability,
    workflow.review,
  ];
  const current = stages[index];
  if (!current) return index === 0 ? "READY" : "NOT RUN";
  const status = statusFrom(current.status ?? asRecord(current.completeness).status ?? asRecord(current.erc_report).status);
  return status ? statusLabel(status) : "CURRENT";
}

function apiFailureMessage(error: unknown): string {
  if (error instanceof BackendRequestError) {
    const details = error.details && Object.keys(error.details).length > 0 ? ` · ${JSON.stringify(error.details)}` : "";
    return `${error.message}${error.code ? ` · ${error.code}` : ""}${details}`;
  }
  return error instanceof Error ? error.message : "Unexpected backend error";
}

function backendError(error: unknown): BackendRequestError {
  return error instanceof BackendRequestError
    ? error
    : new BackendRequestError(apiFailureMessage(error), 0, "UNKNOWN_BACKEND_ERROR");
}

function requirementId(analysis: JsonRecord | null): string | undefined {
  const id = asArray(analysis?.requirement_ids)[0];
  return typeof id === "string" ? id : undefined;
}

function firmwareId(firmware: JsonRecord | null): string | undefined {
  return typeof firmware?.id === "string" ? firmware.id : undefined;
}

function sourceRevisionId(firmware: JsonRecord | null): string | undefined {
  const id = firmware?.source_revision_id;
  return typeof id === "string" ? id : undefined;
}

function testIrId(tests: JsonRecord | null): string | undefined {
  const testIr = asRecord(tests?.test_ir);
  return typeof testIr.id === "string" ? testIr.id : undefined;
}

const REQUIRED_FIRMWARE_RULES = new Set([
  "APP_DIRECT_HAL_CALL",
  "ISR_BLOCKING_API",
  "DRIVER_DEPENDENCY_CYCLE",
  "MCUCONFIG_FIRMWARE_MISMATCH",
]);

function requireDeviceFirmware(firmware: JsonRecord): void {
  const target = asRecord(firmware.build_target);
  if (
    target.profile !== "DEVICE"
    || target.toolchain_id !== "arm-none-eabi-gcc"
    || target.target_triple !== "arm-none-eabi"
    || firmware.dependency_lock_id == null
  ) {
    throw new Error("Release workflow requires backend-confirmed DEVICE firmware, DependencyLock, and arm-none-eabi target");
  }
}

function requireReleaseBuild(build: JsonRecord): void {
  if (build.status !== "PASS" || build.profile !== "DEVICE" || build.toolchain_id !== "arm-none-eabi-gcc" || !build.artifact_hash) {
    const evidence = {
      status: build.status,
      profile: build.profile,
      toolchain_id: build.toolchain_id,
      artifact_hash: build.artifact_hash,
      diagnostics: build.diagnostics,
    };
    throw new Error(`Release workflow requires a PASS DEVICE BuildRun with a real ELF artifact hash · ${JSON.stringify(evidence)}`);
  }
}

function requireReleaseStatic(analysis: JsonRecord): void {
  const cppcheck = asArray(analysis.tool_results).map(asRecord).find((item) => item.tool_id === "cppcheck");
  const rules = asArray(analysis.rule_results).map(asRecord);
  const rulesById = new Map(rules.map((item) => [String(item.rule_id), item]));
  const requiredRulesPass = [...REQUIRED_FIRMWARE_RULES].every((id) => {
    const status = rulesById.get(id)?.status;
    return status === "PASS" || status === "NOT_APPLICABLE";
  });
  if (analysis.status !== "PASS" || cppcheck?.status !== "PASS" || !requiredRulesPass) {
    throw new Error("Release workflow requires PASS Cppcheck and all four firmware release rules");
  }
}

function ercReport(value: JsonRecord | null): JsonRecord {
  return asRecord(value?.erc_report);
}

function requireReleaseErc(value: JsonRecord): void {
  const report = ercReport(value);
  if (report.executed !== true || report.status !== "PASS") {
    throw new Error(`Release workflow requires an executed PASS KiCad ERC report · ${JSON.stringify(report)}`);
  }
}

function traceabilityReleaseStatus(traceability: JsonRecord | null): "PASS" | "BLOCKED" {
  const coverage = asRecord(traceability?.coverage);
  const blocking = [
    ...asArray(coverage.uncovered_requirement_ids),
    ...asArray(coverage.unexecuted_requirement_ids),
    ...asArray(coverage.failing_requirement_ids),
    ...asArray(coverage.blocked_requirement_ids),
    ...asArray(coverage.unknown_requirement_ids),
    ...asArray(coverage.stale_requirement_ids),
  ];
  return coverage.release_critical_requirements !== undefined && blocking.length === 0 ? "PASS" : "BLOCKED";
}

function releaseGateStatus(workflow: WorkflowState): "PASS" | "BLOCKED" {
  try {
    if (!workflow.firmware || !workflow.build || !workflow.staticAnalysis || !workflow.erc) return "BLOCKED";
    requireDeviceFirmware(workflow.firmware);
    requireReleaseBuild(workflow.build);
    requireReleaseStatic(workflow.staticAnalysis);
    requireReleaseErc(workflow.erc);
  } catch {
    return "BLOCKED";
  }
  const testResults = asArray(workflow.testRun?.case_results).map(asRecord);
  if (
    workflow.testRun?.status !== "PASS"
    || testResults.length === 0
    || testResults.some((item) => item.status !== "PASS")
    || traceabilityReleaseStatus(workflow.traceability) !== "PASS"
    || workflow.review?.status !== "PASS"
  ) return "BLOCKED";
  return "PASS";
}

function projectLabel(project: ProjectData): string {
  return project.name || shortId(project.id);
}

export function M21Workspace({ api, runtimeVersion, onReady }: { api: M21Api; runtimeVersion: unknown; onReady?: () => Promise<void> }) {
  const { text } = useI18n();
  const [projects, setProjects] = useState<ProjectData[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowState>(emptyWorkflow);
  const [context, setContext] = useState<ProjectContext>(emptyContext);
  const contextRef = useRef(context);
  const workflowRef = useRef(workflow);
  const [route, setRoute] = useState(() => routeFromLocation(window.location.pathname));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [rawContext, setRawContext] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [showImport, setShowImport] = useState(false);
  const [projectName, setProjectName] = useState("M20 Generic Embedded Controller");
  const [projectDescription, setProjectDescription] = useState(
    "STM32G431 + UART + CAN + SPI Sensor + FreeRTOS",
  );
  const [documentFile, setDocumentFile] = useState<File | null>(null);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiResult, setAiResult] = useState<JsonRecord | null>(null);
  const [refreshStates, setRefreshStates] = useState<Record<string, EngineeringDataState<unknown>>>({});
  const [workflowDescriptor, setWorkflowDescriptor] = useState<JsonRecord | null>(null);
  const readyReported = useRef(false);
  contextRef.current = context;
  workflowRef.current = workflow;

  const selectedProject = projects.find((project) => project.id === projectId) ?? null;
  const navItems = useMemo(() => buildNavigation(context.extensions).map((item) => ({
    ...item,
    label: item.extension ? item.label : text(item.label),
  })), [context.extensions, text]);

  const navigate = useCallback((nextRoute: string) => {
    const safeRoute = nextRoute.replace(/^\//u, "");
    window.history.pushState({}, "", `/${safeRoute}`);
    setRoute(safeRoute);
  }, []);

  useEffect(() => {
    const onPopState = () => setRoute(routeFromLocation(window.location.pathname));
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  useEffect(() => {
    void api.getWorkflowDescriptor()
      .then((descriptor) => setWorkflowDescriptor(descriptor))
      .catch((loadError: unknown) => {
        setRefreshStates((current) => ({
          ...current,
          workflow: { state: "ERROR", error: backendError(loadError) },
        }));
      });
  }, [api]);

  const refreshProjects = useCallback(async () => {
    const result = await api.listProjects();
    setProjects(result.items);
    setProjectId((current) => current ?? result.items[0]?.id ?? null);
  }, [api]);

  const refreshProject = useCallback(async (nextProjectId: string) => {
    const optional = async <T,>(
      key: string,
      operation: () => Promise<T>,
      previous: T | null,
    ): Promise<T | null> => {
      setRefreshStates((current) => ({ ...current, [key]: { state: "LOADING" } }));
      try {
        const data = await operation();
        setRefreshStates((current) => ({ ...current, [key]: { state: "CURRENT", data } }));
        return data;
      } catch (loadError: unknown) {
        const errorState: EngineeringDataState<T> = previous === null
          ? { state: "ERROR", error: backendError(loadError) }
          : { state: "STALE", data: previous, reason: apiFailureMessage(loadError) };
        setRefreshStates((current) => ({ ...current, [key]: errorState }));
        return previous;
      }
    };
    const [domains, availableDomains, extensions, consistency, issues, builds, results, reviews, source] = await Promise.all([
      optional("domains", () => api.getDomains(nextProjectId), contextRef.current.domains.length ? { items: contextRef.current.domains as unknown as DomainActivationData[] } : null),
      optional("available-domains", () => api.getAvailableDomains(nextProjectId), contextRef.current.availableDomains.length ? { items: contextRef.current.availableDomains as unknown as DomainAvailableData[] } : null),
      optional("extensions", () => api.getDomainExtensions(nextProjectId), contextRef.current.extensions.length ? { items: contextRef.current.extensions } : null),
      optional("consistency", () => api.getConsistency(nextProjectId), contextRef.current.consistency),
      optional("issues", () => api.listIssues(nextProjectId), contextRef.current.issues.length ? { items: contextRef.current.issues } : null),
      optional("builds", () => api.listBuilds(nextProjectId), contextRef.current.latestBuild ? { builds: [contextRef.current.latestBuild] } : null),
      optional("test-results", () => api.listTestResults(nextProjectId), contextRef.current.latestTestRun ? { items: [contextRef.current.latestTestRun] } : null),
      optional("reviews", () => api.listReviews(nextProjectId), contextRef.current.latestReview ? { items: [contextRef.current.latestReview] } : null),
      optional("source", () => api.sourceStatus(nextProjectId), contextRef.current.source),
    ]);
    const projectDomains = asArray(domains?.items).map(asRecord);
    const projectAvailableDomains = asArray(availableDomains?.items).map(asRecord);
    const projectExtensions = asArray(extensions?.items).filter((item): item is DomainUIContribution => {
      const record = asRecord(item);
      return typeof record.extension_id === "string" && typeof record.label === "string" && typeof record.route === "string";
    });
    const buildList = asArray(builds?.builds);
    const resultList = asArray(results?.items);
    const reviewList = asArray(reviews?.items);
    const latestBuild = firstRecord(buildList);
    const latestTestRun = firstRecord(resultList);
    const latestReview = firstRecord(reviewList);
    setContext({
      domains: projectDomains,
      availableDomains: projectAvailableDomains,
      extensions: projectExtensions,
      consistency: consistency ? asRecord(consistency) : null,
      issues: asArray(issues?.items).map(asRecord),
      latestBuild,
      latestTestRun,
      latestReview,
      source: source ? asRecord(source) : null,
    });
    const [pinPlan, architecture, circuit, schematic, mcuConfig, dependencies, firmware, protocol, tests, traceability] = await Promise.all([
      optional("pin-plan", () => api.getPinMap(nextProjectId), workflowRef.current.pinPlan),
      optional("architecture", () => api.getArchitecture(nextProjectId), workflowRef.current.architecture),
      optional("circuit", () => api.getCircuit(nextProjectId), workflowRef.current.circuit),
      optional("schematic", () => api.getSchematic(nextProjectId), workflowRef.current.schematic),
      optional("mcu-config", () => api.getMcuConfig(nextProjectId), workflowRef.current.mcuConfig),
      optional("dependencies", () => api.getDependencies(nextProjectId), workflowRef.current.dependencyLock),
      optional("firmware", () => api.getFirmware(nextProjectId), workflowRef.current.firmware ? { firmware: workflowRef.current.firmware } : null),
      optional("protocol", () => api.getProtocol(nextProjectId), workflowRef.current.protocol),
      optional("tests", () => api.listTests(nextProjectId), workflowRef.current.tests),
      optional("traceability", () => api.getTraceability(nextProjectId), workflowRef.current.traceability),
    ]);
    setWorkflow((current) => ({
      ...current,
      pinPlan: pinPlan ? asRecord(pinPlan) : current.pinPlan,
      architecture: architecture ? asRecord(architecture) : current.architecture,
      circuit: circuit ? asRecord(circuit) : current.circuit,
      schematic: schematic ? asRecord(schematic) : current.schematic,
      mcuConfig: mcuConfig ? asRecord(mcuConfig) : current.mcuConfig,
      dependencyLock: dependencies ? asRecord(dependencies) : current.dependencyLock,
      firmware: firmware ? nestedRecord(firmware, "firmware") : current.firmware,
      protocol: protocol ? asRecord(protocol) : current.protocol,
      tests: tests ? asRecord(tests) : current.tests,
      traceability: traceability ? asRecord(traceability) : current.traceability,
      build: latestBuild ?? current.build,
      testRun: latestTestRun ?? current.testRun,
      review: latestReview ?? current.review,
    }));
  }, [api]);

  useEffect(() => {
    void refreshProjects()
      .then(() => {
        window.requestAnimationFrame(() => {
          if (readyReported.current) return;
          readyReported.current = true;
          void onReady?.().catch(() => undefined);
        });
      })
      .catch((loadError: unknown) => setError(apiFailureMessage(loadError)));
  }, [onReady, refreshProjects]);

  useEffect(() => {
    if (!projectId) {
      setWorkflow(emptyWorkflow);
      setContext(emptyContext);
      return;
    }
    void refreshProject(projectId).catch((loadError: unknown) => setError(apiFailureMessage(loadError)));
  }, [projectId, refreshProject]);

  const runAction = useCallback(async (label: string, operation: () => Promise<void>) => {
    setBusy(label);
    setError(null);
    setNotice(null);
    try {
      await operation();
      setNotice(`${text(label)} ${text("completed")}`);
    } catch (actionError: unknown) {
      setError(apiFailureMessage(actionError));
    } finally {
      setBusy(null);
    }
  }, [text]);

  const createProject = async () => {
    await runAction("Create project", async () => {
      const created = await api.createProject({
        name: projectName.trim() || "Untitled engineering project",
        description: projectDescription,
        metadata: { benchmark: "STM32G431 + UART + CAN + SPI Sensor + FreeRTOS", m21: true },
      });
      setProjects((current) => [created, ...current.filter((item) => item.id !== created.id)]);
      setProjectId(created.id);
      setShowCreate(false);
      navigate("dashboard");
    });
  };

  const analyzeM20 = async () => {
    if (!projectId) return;
    await runAction("Analyze requirements", async () => {
      const evidenceRefs = await registerM20Evidence(api, projectId);
      const analysis = await api.analyzeRequirements(m20RequirementPayload(projectId, evidenceRefs));
      setWorkflow((current) => ({ ...current, analysis }));
      navigate("requirements");
    });
  };

  const generatePins = async () => {
    if (!projectId || !workflow.analysis) return;
    await runAction("Generate verified pin map", async () => {
      const plan = await api.generatePinPlan(projectId, m20PinPlanPayload(workflow.analysis as JsonRecord));
      setWorkflow((current) => ({ ...current, pinPlan: plan }));
      navigate("pin-planner");
    });
  };

  const lockPins = async () => {
    if (!projectId || !workflow.pinPlan) return;
    await runAction("Lock verified assignments", async () => {
      const assignments = asArray(workflow.pinPlan?.assignments).map(asRecord);
      for (const assignment of assignments) {
        if (assignment.locked === true || typeof assignment.id !== "string") continue;
        await api.lockPinAssignment(projectId, assignment.id, {
          expected_revision: typeof assignment.revision === "number" ? assignment.revision : undefined,
          actor: "m21-desktop",
          reason: "Verified engineering assignment",
        });
      }
      const map = await api.getPinMap(projectId);
      setWorkflow((current) => ({ ...current, pinPlan: map }));
    });
  };

  const generateHardware = async () => {
    if (!projectId || !workflow.pinPlan) return;
    await runAction("Generate hardware and circuit", async () => {
      const pinPlanId = workflow.pinPlan?.id;
      if (typeof pinPlanId !== "string") throw new Error("Generate Pin Map first");
      const architecture = await api.generateArchitecture(projectId, pinPlanId);
      const hardware = nestedRecord(architecture, "hardware");
      const circuit = await api.generateCircuit(projectId, m20CircuitPayload(hardware, requirementId(workflow.analysis)));
      setWorkflow((current) => ({ ...current, architecture, circuit: nestedRecord(circuit, "circuit") }));
      navigate("hardware");
    });
  };

  const generateSchematic = async () => {
    const circuit = workflow.circuit;
    if (!projectId || !circuit) return;
    await runAction("Generate schematic", async () => {
      const circuitId = typeof circuit.id === "string" ? circuit.id : undefined;
      if (!circuitId) throw new Error("Generate Circuit first");
      const schematic = await api.generateSchematic(projectId, circuitId);
      setWorkflow((current) => ({ ...current, schematic }));
      navigate("schematic");
    });
  };

  const runErc = async () => {
    const schematic = workflow.schematic;
    if (!projectId || !schematic) return;
    await runAction("Run schematic ERC", async () => {
      const schematicData = asRecord(schematic.schematic);
      const schematicId = typeof schematicData.id === "string"
        ? schematicData.id
        : typeof schematic.id === "string" ? schematic.id : undefined;
      if (!schematicId) throw new Error("Generate Schematic first");
      const erc = await api.runErc(projectId, schematicId);
      setWorkflow((current) => ({ ...current, erc }));
    });
  };

  const generateMcu = async () => {
    const architecture = workflow.architecture;
    const circuit = workflow.circuit;
    const schematic = workflow.schematic;
    if (!projectId || !architecture || !circuit || !schematic) return;
    await runAction("Generate MCUConfigIR", async () => {
      const hardware = nestedRecord(architecture, "hardware");
      const circuitData = nestedRecord(circuit, "circuit");
      const schematicData = nestedRecord(schematic, "schematic");
      const config = await api.generateMcuConfig(
        projectId,
        m20McuConfigPayload(hardware, circuitData, schematicData, requirementId(workflow.analysis)),
      );
      setWorkflow((current) => ({ ...current, mcuConfig: nestedRecord(config, "config") }));
      navigate("mcu-config");
    });
  };

  const generateFirmware = async () => {
    const mcuConfig = workflow.mcuConfig;
    if (!projectId || !mcuConfig) return;
    await runAction("Generate FirmwareIR", async () => {
      const configId = typeof mcuConfig.id === "string" ? mcuConfig.id : undefined;
      if (!configId) throw new Error("Generate MCU Config first");
      const dependencyLock = await api.resolveDependencies(
        projectId,
        m20DependencyResolvePayload(configId, requirementId(workflow.analysis)),
      );
      const materialization = await api.materializeDependencies(projectId, String(dependencyLock.id));
      const firmwareBundle = await api.generateFirmware(
        projectId,
        m20DeviceFirmwarePayload(configId, String(dependencyLock.id)),
      );
      const firmware = nestedRecord(firmwareBundle, "firmware");
      requireDeviceFirmware(firmware);
      setWorkflow((current) => ({
        ...current,
        dependencyLock,
        dependencyMaterialization: materialization,
        firmware,
      }));
      navigate("firmware");
    });
  };

  const runBuild = async () => {
    if (!projectId || !workflow.firmware) return;
    const firmware = workflow.firmware;
    await runAction("Build DEVICE firmware", async () => {
      const id = firmwareId(firmware);
      if (!id) throw new Error("Generate Firmware first");
      requireDeviceFirmware(firmware);
      const build = await api.build(projectId, id);
      setWorkflow((current) => ({ ...current, build }));
      requireReleaseBuild(build);
      await refreshProject(projectId);
    });
  };

  const runStatic = async () => {
    if (!projectId || !workflow.firmware) return;
    await runAction("Run static analysis", async () => {
      const id = firmwareId(workflow.firmware);
      if (!id) throw new Error("Generate Firmware first");
      const analysis = await api.runStaticAnalysis(projectId, id);
      setWorkflow((current) => ({ ...current, staticAnalysis: analysis }));
      requireReleaseStatic(analysis);
      navigate("firmware");
    });
  };

  const generateProtocol = async () => {
    if (!projectId) return;
    await runAction("Generate ProtocolIR", async () => {
      const protocol = await api.createProtocol(projectId, m20ProtocolPayload(requirementId(workflow.analysis)));
      const generated = await api.generateProtocol(projectId, { protocol_id: protocol.id });
      setWorkflow((current) => ({ ...current, protocol, protocolOutputs: generated }));
      navigate("protocol");
    });
  };

  const generateAndRunTests = async () => {
    if (!projectId || !workflow.firmware) return;
    await runAction("Run software tests", async () => {
      const tests = await api.generateTests(projectId, "SOFTWARE_RELEASE");
      const testIr = nestedRecord(tests, "test_ir");
      const sourceId = sourceRevisionId(workflow.firmware);
      if (!sourceId) throw new Error("Firmware has no SourceRevision binding");
      const testRun = await api.runTests(projectId, { test_ir_id: testIr.id, source_revision_id: sourceId });
      setWorkflow((current) => ({ ...current, tests, testRun }));
      navigate("tests");
    });
  };

  const runTraceability = async () => {
    if (!projectId) return;
    await runAction("Refresh traceability", async () => {
      const traceability = await api.getTraceability(projectId);
      setWorkflow((current) => ({ ...current, traceability }));
      navigate("review");
    });
  };

  const runReview = async () => {
    if (!projectId || !workflow.firmware) return;
    await runAction("Run deterministic review", async () => {
      requireDeviceFirmware(workflow.firmware as JsonRecord);
      if (!workflow.build) throw new Error("Run the DEVICE build before Review");
      requireReleaseBuild(workflow.build);
      if (!workflow.staticAnalysis) throw new Error("Run static analysis before Review");
      requireReleaseStatic(workflow.staticAnalysis);
      if (!workflow.erc) throw new Error("Run ERC before Review");
      requireReleaseErc(workflow.erc);
      if (workflow.testRun?.status !== "PASS") throw new Error("Run the PASS software TestRun before Review");
      if (traceabilityReleaseStatus(workflow.traceability) !== "PASS") throw new Error("Refresh complete release traceability before Review");
      const sourceId = sourceRevisionId(workflow.firmware);
      if (!sourceId) throw new Error("Firmware has no SourceRevision binding");
      const review = await api.runReview(projectId, {
        source_revision_id: sourceId,
        test_ir_id: testIrId(workflow.tests),
        test_run_id: workflow.testRun?.id,
        build_run_id: workflow.build?.id,
        static_analysis_id: workflow.staticAnalysis?.id,
        schematic_id: nestedRecord(workflow.schematic, "schematic").id ?? workflow.schematic?.id,
        require_build: true,
        require_static_analysis: true,
        require_erc: true,
        require_test: true,
      });
      setWorkflow((current) => ({ ...current, review }));
      if (review.status !== "PASS") throw new Error("Backend Review did not return PASS");
      await refreshProject(projectId);
      navigate("review");
    });
  };

  const runFullBenchmark = async () => {
    if (!projectId) return;
    await runAction("Run M20 generic UI workflow", async () => {
      const evidenceRefs = await registerM20Evidence(api, projectId);
      const analysis = await api.analyzeRequirements(m20RequirementPayload(projectId, evidenceRefs));
      setWorkflow((current) => ({ ...current, analysis }));
      const plan = await api.generatePinPlan(projectId, m20PinPlanPayload(analysis));
      setWorkflow((current) => ({ ...current, pinPlan: plan }));
      const assignments = asArray(plan.assignments).map(asRecord);
      for (const assignment of assignments) {
        if (assignment.locked === true || typeof assignment.id !== "string") continue;
        await api.lockPinAssignment(projectId, assignment.id, {
          expected_revision: typeof assignment.revision === "number" ? assignment.revision : undefined,
          actor: "m21-desktop",
          reason: "M20 UI benchmark",
        });
      }
      const lockedPlan = await api.getPinMap(projectId);
      const architecture = await api.generateArchitecture(projectId, lockedPlan.id as string);
      const hardware = nestedRecord(architecture, "hardware");
      const circuitBundle = await api.generateCircuit(projectId, m20CircuitPayload(hardware, requirementId(analysis)));
      const circuit = nestedRecord(circuitBundle, "circuit");
      const schematicBundle = await api.generateSchematic(projectId, circuit.id as string);
      const schematic = nestedRecord(schematicBundle, "schematic");
      const erc = await api.runErc(projectId, schematic.id as string);
      requireReleaseErc(erc);
      const mcuBundle = await api.generateMcuConfig(projectId, m20McuConfigPayload(hardware, circuit, schematic, requirementId(analysis)));
      const mcu = nestedRecord(mcuBundle, "config");
      const dependencyLock = await api.resolveDependencies(
        projectId,
        m20DependencyResolvePayload(String(mcu.id), requirementId(analysis)),
      );
      const dependencyMaterialization = await api.materializeDependencies(projectId, String(dependencyLock.id));
      const firmwareBundle = await api.generateFirmware(
        projectId,
        m20DeviceFirmwarePayload(String(mcu.id), String(dependencyLock.id)),
      );
      const firmware = nestedRecord(firmwareBundle, "firmware");
      requireDeviceFirmware(firmware);
      const build = await api.build(projectId, firmware.id as string);
      requireReleaseBuild(build);
      const staticAnalysis = await api.runStaticAnalysis(projectId, firmware.id as string);
      requireReleaseStatic(staticAnalysis);
      const protocol = await api.createProtocol(projectId, m20ProtocolPayload(requirementId(analysis)));
      const protocolOutputs = await api.generateProtocol(projectId, { protocol_id: protocol.id });
      const tests = await api.generateTests(projectId, "SOFTWARE_RELEASE");
      const testIr = nestedRecord(tests, "test_ir");
      const testRun = await api.runTests(projectId, { test_ir_id: testIr.id, source_revision_id: firmware.source_revision_id });
      if (testRun.status !== "PASS" || asArray(testRun.case_results).some((item) => !["PASS", "NOT_APPLICABLE"].includes(String(asRecord(item).status)))) {
        throw new Error("Release workflow requires a PASS deterministic software TestRun");
      }
      const traceability = await api.getTraceability(projectId);
      if (traceabilityReleaseStatus(traceability) !== "PASS") {
        throw new Error("Release workflow has uncovered, unexecuted, failing, blocked, unknown, or stale MUST requirements");
      }
      const review = await api.runReview(projectId, {
        source_revision_id: firmware.source_revision_id,
        test_ir_id: testIr.id,
        test_run_id: testRun.id,
        build_run_id: build.id,
        static_analysis_id: staticAnalysis.id,
        schematic_id: schematic.id,
        require_build: true,
        require_static_analysis: true,
        require_erc: true,
        require_test: true,
      });
      if (review.status !== "PASS") {
        throw new Error("Release workflow requires an explicit backend Review PASS");
      }
      setWorkflow({ analysis, pinPlan: lockedPlan, architecture, circuit, schematic: schematicBundle, erc, mcuConfig: mcu, dependencyLock, dependencyMaterialization, firmware, build, staticAnalysis, protocol, protocolOutputs, tests, testRun, traceability, review });
      await refreshProject(projectId);
      navigate("review");
    });
  };

  const activateDomain = async (domainId: string) => {
    if (!projectId) return;
    await runAction(`Activate ${domainId}`, async () => {
      await api.activateDomain(projectId, domainId);
      await refreshProject(projectId);
      navigate("domains");
    });
  };

  const deactivateDomain = async (domainId: string) => {
    if (!projectId) return;
    await runAction(`Deactivate ${domainId}`, async () => {
      await api.deactivateDomain(projectId, domainId);
      await refreshProject(projectId);
      navigate("domains");
    });
  };

  const uploadDocument = async () => {
    if (!projectId || !documentFile) return;
    await runAction("Upload document", async () => {
      const content = await documentFile.arrayBuffer();
      let binary = "";
      for (const byte of new Uint8Array(content)) binary += String.fromCharCode(byte);
      const contentBase64 = btoa(binary);
      await api.uploadDocument(projectId, {
        filename: documentFile.name,
        content_base64: contentBase64,
        document_type: "UNKNOWN",
        vendor: null,
        product: null,
        version_label: null,
      });
      setDocumentFile(null);
    });
  };

  const askAi = async () => {
    if (!projectId || !aiPrompt.trim()) return;
    await runAction("Generate controlled AI suggestion", async () => {
      const result = await api.analyzeNaturalLanguage({
        project_id: projectId,
        profile_name: M20_PROFILE_NAME,
        profile_version: M20_PROFILE_VERSION,
        source_text: aiPrompt.trim(),
        evidence_refs: {},
      });
      setAiResult(result);
    });
  };

  const filteredNav = navItems.filter((item) => !search || item.label.toLowerCase().includes(search.toLowerCase()));
  const nonCurrentStates = Object.entries(refreshStates).filter(([, state]) => state.state !== "CURRENT");

  return (
    <div className="workspace-shell">
      <header className="topbar">
          <div className="brand-lockup">
          <div className="brand-mark" aria-hidden="true">EE</div>
          <div>
            <p className="brand-name">{text("Embedded Engineering Agent")}</p>
            <p className="brand-subtitle">{text("Architecture Freeze · Generic Workbench")} · {stringValue(workflowDescriptor?.workflow_id, "descriptor unavailable")}</p>
          </div>
        </div>
        <div className="topbar-context">
          <label className="project-picker">
            <span>{text("Project")}</span>
            <select data-testid="current-project" aria-label={text("Current project")} value={projectId ?? ""} onChange={(event) => setProjectId(event.target.value || null)}>
              <option value="">{text("No project selected")}</option>
              {projects.map((project) => <option key={project.id} value={project.id}>{projectLabel(project)}</option>)}
            </select>
          </label>
          <span className="status-pill tone-pass">{text("● Backend authenticated")}</span>
        </div>
      </header>

      <div className="workspace-body">
        <aside className="sidebar" aria-label="Primary navigation">
          <div className="sidebar-heading"><span>{text("WORKSPACE")}</span><span className="project-chip">{text(selectedProject ? "PROJECT" : "START")}</span></div>
          <nav className="nav-list">
            {filteredNav.map((item) => <NavButton key={item.id} item={item} active={route === item.route} onNavigate={navigate} />)}
          </nav>
          <div className="sidebar-footer">
            <button className="text-button" data-testid="new-project" onClick={() => setShowCreate(true)}>{text("＋ New project")}</button>
            <span className="version-label">Runtime {stringValue(asRecord(runtimeVersion).version, "connected")}</span>
          </div>
        </aside>

        <main className="main-workspace">
          <div className="workspace-toolbar">
            <label className="search-box"><span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={text("Search workspace")} aria-label={text("Search workspace")} /></label>
            <div className="toolbar-actions"><button className="ghost-button" data-testid="refresh-state" onClick={() => projectId && void refreshProject(projectId)}>{text("Refresh state")}</button><button className="primary-button" data-testid="run-m20-workflow" disabled={!projectId || Boolean(busy)} onClick={() => void runFullBenchmark()}>{text("Run M20 UI workflow")}</button></div>
          </div>
           {error && <div className="feedback-banner feedback-error" role="alert"><strong>{text("Backend action failed")}</strong><span>{error}</span><button className="icon-button" onClick={() => setError(null)} aria-label={text("Dismiss error")}>×</button></div>}
           {nonCurrentStates.length > 0 && <div className="feedback-banner feedback-warning" role="status"><strong>{text("Engineering data state")}</strong><span>{nonCurrentStates.map(([key, state]) => `${key}: ${state.state}`).join(" · ")}</span></div>}
          {notice && <div className="feedback-banner feedback-success" role="status"><strong>{text("Action complete")}</strong><span>{notice}</span><button className="icon-button" onClick={() => setNotice(null)} aria-label={text("Dismiss notice")}>×</button></div>}
          {busy && <div className="running-strip" role="status"><span className="spinner" aria-hidden="true" /> {text(busy)} · {text("deterministic backend operation running")}</div>}
          {showImport ? <ImportWizard api={api} onClose={() => setShowImport(false)} onComplete={async (createdProjectId) => { await refreshProjects(); setProjectId(createdProjectId); navigate("projects"); }} /> : !selectedProject && route !== "projects" ? <StartPanel onCreate={() => setShowCreate(true)} onOpen={() => navigate("projects")} /> : <PageRouter api={api} route={route} selectedProject={selectedProject} workflow={workflow} context={context} busy={busy} rawContext={rawContext} setRawContext={setRawContext} onNavigate={navigate} onAnalyze={analyzeM20} onGeneratePins={generatePins} onLockPins={lockPins} onGenerateHardware={generateHardware} onGenerateSchematic={generateSchematic} onRunErc={runErc} onGenerateMcu={generateMcu} onGenerateFirmware={generateFirmware} onRunBuild={runBuild} onRunStatic={runStatic} onGenerateProtocol={generateProtocol} onRunTests={generateAndRunTests} onTraceability={runTraceability} onReview={runReview} onActivateDomain={activateDomain} onDeactivateDomain={deactivateDomain} onUploadDocument={uploadDocument} documentFile={documentFile} setDocumentFile={setDocumentFile} aiPrompt={aiPrompt} setAiPrompt={setAiPrompt} aiResult={aiResult} onAskAi={askAi} projects={projects} onSelectProject={setProjectId} onCreate={() => setShowCreate(true)} onImport={() => setShowImport(true)} />}
        </main>

        <aside className="context-panel" aria-label={text("Context and AI panel")}>
          <div className="panel-heading"><span className="panel-kicker">{text("CONTEXT")}</span><span className="ai-spark">✦</span></div>
          <h2>{selectedProject?.name ?? text("No project context")}</h2>
          <p className="muted">{text("Backend state is authoritative. This panel explains state and suggests next actions; it never overrides deterministic gates.")}</p>
          {selectedProject && <div className="context-stack"><ContextRow label={text("Project ID")} value={shortId(selectedProject.id)} /><ContextRow label="SourceRevision" value={shortId(context.source?.source_revision_id ?? workflow.firmware?.source_revision_id)} /><ContextRow label={text("Active domains")} value={`${context.domains.filter((item) => item.status === "ACTIVE").length}`} /><ContextRow label={text("Open issues")} value={displayCount(context.issues.filter((item) => item.status === "OPEN").length)} /></div>}
          <div className="ai-card"><div className="ai-card-title">{text("AI Panel · controlled")}</div><p>{text("Ask for a requirement interpretation or an explanation of a rule. Deterministic Build/ERC/Review states cannot be changed here.")}</p><button className="ghost-button full-width" onClick={() => navigate("ai")}>{text("Open AI Panel")}</button></div>
          {selectedProject && <MemoryPanel api={api} projectId={selectedProject.id} />}
          {selectedProject && <div className="context-actions"><button className="ghost-button full-width" onClick={() => navigate("review")}>{text("Inspect release gate")}</button><button className="ghost-button full-width" onClick={() => setRawContext((value) => !value)}>{text(rawContext ? "Hide raw context" : "Show raw context")}</button></div>}
          {rawContext && <pre className="raw-json">{JSON.stringify({ project: selectedProject, context, workflow }, null, 2)}</pre>}
        </aside>
      </div>
      <footer className="statusbar"><span><i className="status-dot small pass" /> {text("Backend connection: authenticated loopback")}</span><span>{text("Source")}: {shortId(context.source?.source_revision_id ?? workflow.firmware?.source_revision_id)}</span><span>{text("Build")}: <StatusPill status={asStatus(workflow.build?.status ?? context.latestBuild?.status)} /></span><span>{text("Review")}: <StatusPill status={asStatus(workflow.review?.status ?? context.latestReview?.status)} /></span><span>{typeof context.consistency?.status === "string" ? `${text("Consistency")}: ${statusLabel(context.consistency.status)}` : text("State sync ready")}</span></footer>
      {showCreate && <CreateProjectDialog name={projectName} description={projectDescription} setName={setProjectName} setDescription={setProjectDescription} onClose={() => setShowCreate(false)} onCreate={() => void createProject()} busy={busy === "Create project"} />}
    </div>
  );
}

function NavButton({ item, active, onNavigate }: { item: NavigationItem; active: boolean; onNavigate: (route: string) => void }) {
  return <button className={`nav-item ${active ? "active" : ""}`} data-testid={`nav-${item.id}`} aria-current={active ? "page" : undefined} onClick={() => onNavigate(item.route)}><span className="nav-icon" aria-hidden="true">{item.icon}</span><span>{item.label}</span>{item.extension && <span className="extension-badge">EXT</span>}</button>;
}

function StartPanel({ onCreate, onOpen }: { onCreate: () => void; onOpen: () => void }) {
  const { text } = useI18n();
  return <section className="start-panel"><span className="eyebrow">{text("M21 · DESKTOP ENGINEERING WORKBENCH")}</span><h1>{text("Bring verified engineering state into view.")}</h1><p>{text("Create or open a project to work through requirements, verified pins, HardwareIR, MCUConfigIR, FirmwareIR, deterministic Build/Test/Review, and dynamic Domain UI.")}</p><div className="start-actions"><button className="primary-button" data-testid="start-create-project" onClick={onCreate}>{text("Create project")}</button><button className="ghost-button" data-testid="start-open-projects" onClick={onOpen}>{text("Open project list")}</button></div><div className="start-contract"><span>{text("✓ Backend/Core remains authority")}</span><span>{text("✓ No domain is active by default")}</span><span>{text("✓ UNKNOWN and STALE stay explicit")}</span></div></section>;
}

function PageRouter(props: PageProps) {
  const { route, ...pageProps } = props;
  if (route === "dashboard") return <DashboardPage {...pageProps} />;
  if (route === "projects") return <ProjectsPage {...pageProps} />;
  if (route === "requirements") return <RequirementsPage {...pageProps} />;
  if (route === "planning") return <M24APlanningPanel api={pageProps.api} projectId={pageProps.selectedProject?.id ?? null} busy={pageProps.busy} />;
  if (route === "documents") return <DocumentsPage {...pageProps} />;
  if (route === "pin-planner") return <PinPlannerPage {...pageProps} />;
  if (route === "hardware") return <HardwarePage {...pageProps} />;
  if (route === "schematic") return <SchematicPage {...pageProps} />;
  if (route === "mcu-config") return <McuConfigPage {...pageProps} />;
  if (route === "firmware") return <FirmwarePage {...pageProps} />;
  if (route === "protocol") return <ProtocolPage {...pageProps} />;
  if (route === "tests") return <TestsPage {...pageProps} />;
  if (route === "review") return <ReviewPage {...pageProps} />;
  if (route === "domains") return <DomainsPage {...pageProps} />;
  if (route === "settings") return <SettingsPage {...pageProps} />;
  if (route === "ai") return <AiPage {...pageProps} />;
  const extension = pageProps.context.extensions.find((item) => item.route === route);
  return <ExtensionPage {...pageProps} extension={extension} />;
}

type PageProps = {
  route?: string;
  api: M21Api;
  selectedProject: ProjectData | null;
  workflow: WorkflowState;
  context: ProjectContext;
  busy: string | null;
  rawContext: boolean;
  setRawContext: (value: boolean) => void;
  onNavigate: (route: string) => void;
  onAnalyze: () => Promise<void>;
  onGeneratePins: () => Promise<void>;
  onLockPins: () => Promise<void>;
  onGenerateHardware: () => Promise<void>;
  onGenerateSchematic: () => Promise<void>;
  onRunErc: () => Promise<void>;
  onGenerateMcu: () => Promise<void>;
  onGenerateFirmware: () => Promise<void>;
  onRunBuild: () => Promise<void>;
  onRunStatic: () => Promise<void>;
  onGenerateProtocol: () => Promise<void>;
  onRunTests: () => Promise<void>;
  onTraceability: () => Promise<void>;
  onReview: () => Promise<void>;
  onActivateDomain: (domainId: string) => Promise<void>;
  onDeactivateDomain: (domainId: string) => Promise<void>;
  onUploadDocument: () => Promise<void>;
  documentFile: File | null;
  setDocumentFile: (file: File | null) => void;
  aiPrompt: string;
  setAiPrompt: (value: string) => void;
  aiResult: JsonRecord | null;
  onAskAi: () => Promise<void>;
  projects: ProjectData[];
  onSelectProject: (projectId: string) => void;
  onCreate: () => void;
  onImport: () => void;
};

function PageFrame({ eyebrow, title, description, actions, children }: { eyebrow: string; title: string; description: string; actions?: React.ReactNode; children: React.ReactNode }) {
  const { text } = useI18n();
  return <section className="page-frame"><div className="page-header"><div><span className="eyebrow">{text(eyebrow)}</span><h1 data-testid="page-title">{text(title)}</h1><p>{text(description)}</p></div>{actions && <div className="page-actions">{actions}</div>}</div>{children}</section>;
}

function DashboardPage(props: PageProps) {
  const { selectedProject, workflow, context, busy, onAnalyze, onGeneratePins, onGenerateHardware, onGenerateFirmware, onRunTests, onReview, onNavigate } = props;
  const { text } = useI18n();
  return <PageFrame eyebrow="PROJECT / DASHBOARD" title={selectedProject?.name ?? "Dashboard"} description="A dense, answer-first view of the current engineering workflow and deterministic release health." actions={<button className="primary-button" disabled={Boolean(busy)} onClick={() => void onReview()}>{text("Run review")}</button>}>
    <div className="metric-grid"><Metric label="Build" value={workflow.build?.status ?? context.latestBuild?.status} detail={workflow.build?.artifact_hash ? shortId(workflow.build.artifact_hash) : "No latest artifact"} /><Metric label="Software tests" value={workflow.testRun?.status ?? context.latestTestRun?.status} detail={`${asArray(workflow.testRun?.case_results).length || "No"} case results`} /><Metric label="Review" value={workflow.review?.status ?? context.latestReview?.status} detail={`${asArray(workflow.review?.findings).length} findings`} /><Metric label="Stale objects" value={context.consistency?.engineering_freshness ? "CURRENT" : "UNKNOWN"} detail={context.consistency?.engineering_freshness ? `${displayCount(asRecord(context.consistency.engineering_freshness).stale)} stale · ${displayCount(asRecord(context.consistency.engineering_freshness).invalid)} invalid` : "Refresh project state"} /></div>
     <div className="dashboard-grid"><div className="panel-card workflow-card"><PanelTitle label="Workflow progress" title="M20 generic benchmark" action={<button className="ghost-button" data-testid="analyze-m20-profile" onClick={() => void onAnalyze()}>{text("Analyze requirements")}</button>} /><div className="workflow-list">{workflowStages.map((stage, index) => <button key={stage} className="workflow-row" onClick={() => onNavigate(stageRoute(stage))}><span className="workflow-index">{String(index + 1).padStart(2, "0")}</span><span className="workflow-stage">{stage}</span><StatusPill status={getWorkflowStageStatus(workflow, index)} /><span className="chevron">›</span></button>)}</div></div><div className="panel-card"><PanelTitle label="Next actions" title="Continue from authority" /><div className="action-stack"><ActionRow title="Verified Pin Planner" detail="Generate UART / CAN / SPI assignments" onClick={onGeneratePins} disabled={!workflow.analysis || Boolean(busy)} /><ActionRow title="HardwareIR + CircuitIR" detail="Generate from the locked pin map" onClick={onGenerateHardware} disabled={!workflow.pinPlan || Boolean(busy)} /><ActionRow title="Firmware + Build" detail="Generate source, build, and static evidence" onClick={onGenerateFirmware} disabled={!workflow.mcuConfig || Boolean(busy)} /><ActionRow title="Run software tests" detail="Deterministic verification only" onClick={onRunTests} disabled={!workflow.firmware || Boolean(busy)} /><ActionRow title="Review" detail="Close the traceability loop" onClick={onReview} disabled={!workflow.firmware || Boolean(busy)} /></div></div></div>
    <div className="panel-card"><PanelTitle label="Issues / activity" title="What needs attention?" /><div className="issue-list">{context.issues.length === 0 ? <EmptyState text="No open issues reported by the backend." /> : context.issues.slice(0, 5).map((issue) => <IssueRow key={String(issue.id)} issue={issue} />)}</div></div>
    <div className="benchmark-callout"><div><span className="eyebrow">RELEASE BENCHMARK</span><h2>STM32G431 + UART + CAN + SPI Sensor + FreeRTOS</h2><p>MotorControl is not part of this project. Domain UI is loaded from backend metadata, so an inactive domain does not add a tab.</p></div><div className="callout-actions"><button className="ghost-button" onClick={() => onNavigate("domains")}>Inspect domains</button><button className="primary-button" disabled={!workflow.build || Boolean(busy)} onClick={() => void onReview()}>Close review gate</button></div></div>
  </PageFrame>;
}

function ProjectsPage({ projects, selectedProject, onSelectProject, onCreate, onImport }: PageProps) {
  const { text } = useI18n();
  return <PageFrame eyebrow="WORKSPACE" title="Projects" description="Create, open, and resume engineering projects from backend state." actions={<><button className="ghost-button" onClick={onImport}>{text("Import existing project")}</button><button className="primary-button" onClick={onCreate}>{text("Create project")}</button></>}><div className="project-grid">{projects.map((project) => <button className={`project-card ${selectedProject?.id === project.id ? "selected" : ""}`} key={project.id} onClick={() => onSelectProject(project.id)}><div className="project-card-top"><span className="project-status">{project.status}</span><span className="chevron">›</span></div><h2>{project.name}</h2><p>{project.description || text("No description")}</p><div className="project-meta"><span>{shortId(project.id)}</span><span>rev {project.revision}</span></div></button>)}</div>{projects.length === 0 && <EmptyState text="No projects yet. Create or import an existing project to start." />}</PageFrame>;
}

function RequirementsPage({ workflow, onAnalyze, onNavigate, busy }: PageProps) {
  const analysis = workflow.analysis;
  const completeness = asRecord(analysis?.completeness);
  const { text } = useI18n();
  return <PageFrame eyebrow="WORKFLOW / REQUIREMENTS" title="Requirements" description="Structured canonical requirements remain backend-owned; the UI only submits profile values and renders evidence-backed results." actions={<button className="primary-button" data-testid="analyze-m20-profile" disabled={Boolean(busy)} onClick={() => void onAnalyze()}>{text("Analyze M20 profile")}</button>}><div className="two-column"><div className="panel-card form-card"><PanelTitle label="Profile" title="Generic embedded controller" /><div className="field-grid"><ReadOnlyField label="Profile" value={M20_PROFILE_NAME} /><ReadOnlyField label="Version" value={M20_PROFILE_VERSION} /><ReadOnlyField label="Target" value="STM32G431 · UFQFPN48" /><ReadOnlyField label="Interfaces" value="USART2 · FDCAN1 · SPI1" /><ReadOnlyField label="RTOS" value="FreeRTOS · 3 tasks" /><ReadOnlyField label="Evidence contract" value="Device · Interface · RTOS" /></div><div className="profile-note"><span>{text("Canonical input")}</span><p>{text("Analyze returns Requirement, Claim, Evidence and completeness refs. The frontend does not recreate missing-field or rule logic.")}</p></div></div><div className="panel-card"><PanelTitle label="Completeness" title="Analysis result" /><div className="result-header"><StatusPill status={typeof completeness.status === "string" ? completeness.status : "UNKNOWN"} /><span>{typeof completeness.score === "number" ? `${Math.round(completeness.score * 100)}% complete` : text("Not analyzed")}</span></div><KeyValueList values={{ "Missing fields": asArray(completeness.missing_field_keys).join(", ") || "None", "Ambiguities": asArray(completeness.ambiguous_field_keys).join(", ") || "None", "Missing evidence": asArray(completeness.missing_evidence_keys).join(", ") || "None" }} /></div></div>{analysis && <div className="panel-card"><PanelTitle label="Canonical output" title={`${asArray(analysis.requirements).length} requirements · ${asArray(analysis.claims).length} claims`} action={<button className="ghost-button" onClick={() => onNavigate("pin-planner")}>{text("Continue to Pin Planner")}</button>} /><div className="table-wrap"><table><thead><tr><th>Requirement</th><th>Type / priority</th><th>Statement</th><th>Status</th></tr></thead><tbody>{asArray(analysis.requirements).map((item, index) => { const record = asRecord(item); return <tr key={String(record.id ?? index)}><td><strong>{stringValue(record.code, `REQ-${index + 1}`)}</strong><br /><span className="muted">{stringValue(record.title)}</span></td><td>{stringValue(record.requirement_type)}<br />{stringValue(record.priority)}</td><td>{stringValue(record.statement)}</td><td><StatusPill status={typeof record.status === "string" ? record.status : undefined} /></td></tr>; })}</tbody></table></div></div>}</PageFrame>;
}

function DocumentsPage({ documentFile, setDocumentFile, onUploadDocument, busy }: PageProps) {
  const { text } = useI18n();
  return <PageFrame eyebrow="EVIDENCE / DOCUMENTS" title="Documents" description="Register a document as backend DocumentIR and render parse status, evidence, and claims without pretending upload is project import." actions={<button className="primary-button" disabled={!documentFile || Boolean(busy)} onClick={() => void onUploadDocument()}>{text("Upload document")}</button>}><div className="two-column"><div className="panel-card upload-card"><PanelTitle label="DocumentIR" title="Add source evidence" /><label className="drop-zone"><input type="file" onChange={(event) => setDocumentFile(event.target.files?.[0] ?? null)} /><span className="upload-icon">↥</span><strong>{documentFile ? documentFile.name : text("Choose a datasheet, reference manual, or user document")}</strong><small>{text("Stored through the authenticated backend path. No localStorage or browser secret.")}</small></label></div><div className="panel-card"><PanelTitle label="What this page shows" title="Evidence-aware document state" /><div className="mini-list"><MiniRow label="Upload" value="Backend DocumentIR" /><MiniRow label="Parsing" value="UPLOADED → PARSED / FAILED" /><MiniRow label="Claims" value="Extracted by backend pipeline" /><MiniRow label="Import" value="Out of M21 scope" /></div></div></div></PageFrame>;
}

function PinPlannerPage({ workflow, onGeneratePins, onLockPins, onNavigate, busy }: PageProps) {
  const assignments = asArray(workflow.pinPlan?.assignments).map(asRecord);
  const { text } = useI18n();
  return <PageFrame eyebrow="HARDWARE / PIN PLANNER" title="Verified Pin Planner" description="Signals, alternate functions, evidence-backed assignments, locks, and rule results are rendered from PinPlanData." actions={<><button className="ghost-button" disabled={!workflow.analysis || Boolean(busy)} onClick={() => void onGeneratePins()}>{text("Generate")}</button><button className="primary-button" disabled={!workflow.pinPlan || Boolean(busy)} onClick={() => void onLockPins()}>{text("Lock verified")}</button></>}><div className="planner-summary"><Metric label="Device" value="STM32G431" detail="UFQFPN48" /><Metric label="Assignments" value={String(assignments.length)} detail={`${assignments.filter((item) => item.locked === true).length} locked`} /><Metric label="Rule state" value={workflow.pinPlan ? "CURRENT" : "UNKNOWN"} detail="Backend Pin Planner" /></div>{assignments.length === 0 ? <EmptyState text="Analyze requirements, then generate the verified M20 pin map." /> : <div className="table-wrap"><table><thead><tr><th>Signal</th><th>Peripheral / function</th><th>Selected pin</th><th>AF</th><th>Evidence</th><th>Lock</th><th>Rule state</th></tr></thead><tbody>{assignments.map((assignment, index) => { const fn = asRecord(assignment.function); return <tr key={String(assignment.id ?? index)}><td><strong>{stringValue(assignment.signal_ref ?? assignment.signal_name)}</strong></td><td>{stringValue(fn.peripheral)} / {stringValue(fn.signal)}</td><td><strong>{stringValue(assignment.pin_name)}</strong><br /><span className="muted">{stringValue(assignment.package)}</span></td><td>{stringValue(fn.alternate_function, "GPIO")}</td><td>{asArray(assignment.evidence_ids).length || "—"}</td><td>{assignment.locked === true ? <StatusPill status="PASS" label="LOCKED" /> : <StatusPill status="UNKNOWN" label="OPEN" />}</td><td><StatusPill status={assignment.rule_status as string | undefined} /></td></tr>; })}</tbody></table></div>}{workflow.pinPlan && <div className="inline-actions"><button className="ghost-button" onClick={() => onNavigate("hardware")}>{text("Continue to Hardware")}</button><CopyValue value={String(workflow.pinPlan.id ?? "")} label="Copy PinPlan ID" /></div>}</PageFrame>;
}

function HardwarePage({ workflow, onGenerateHardware, onGenerateSchematic, onNavigate, busy }: PageProps) {
  const architecture = workflow.architecture;
  const hardware = nestedRecord(architecture, "hardware");
  const { text } = useI18n();
  return <PageFrame eyebrow="HARDWARE / CIRCUIT" title="HardwareIR & CircuitIR" description="Hardware and electrical choices are generated from the locked PinPlan. The UI explains accepted inputs; it does not create a second hardware truth." actions={<><button className="primary-button" disabled={!workflow.pinPlan || Boolean(busy)} onClick={() => void onGenerateHardware()}>{text("Generate hardware")}</button><button className="ghost-button" disabled={!workflow.circuit || Boolean(busy)} onClick={() => void onGenerateSchematic()}>{text("Generate schematic")}</button></>}><div className="two-column"><div className="panel-card"><PanelTitle label="SystemArchitecture" title="Blocks & interfaces" /><div className="object-grid"><ObjectSummary label="Blocks" items={hardware.blocks ?? architecture?.blocks} /><ObjectSummary label="Interfaces" items={hardware.interfaces ?? architecture?.interfaces} /><ObjectSummary label="Power domains" items={hardware.power_domains} /><ObjectSummary label="Device instances" items={hardware.device_instances} /></div></div><div className="panel-card"><PanelTitle label="CircuitIR" title="Electrical rules" /><div className="rule-list">{asArray(workflow.circuit?.rule_results).map((rule, index) => <RuleRow key={index} rule={asRecord(rule)} />)}{!workflow.circuit && <EmptyState text="Generate hardware first; CircuitIR and rule results will appear here." />}</div></div></div>{workflow.circuit && <div className="panel-card"><PanelTitle label="Netlist" title={`${asArray(workflow.circuit.nets).length} nets · ${asArray(workflow.circuit.components).length} components`} action={<button className="ghost-button" onClick={() => onNavigate("schematic")}>{text("Open Schematic / ERC")}</button>} /><div className="chip-list">{asArray(workflow.circuit.nets).slice(0, 12).map((net, index) => <span className="data-chip" key={index}>{stringValue(asRecord(net).name, `NET-${index + 1}`)}</span>)}</div></div>}</PageFrame>;
}

function SchematicPage({ workflow, onGenerateSchematic, onRunErc, busy }: PageProps) {
  const schematic = nestedRecord(workflow.schematic, "schematic");
  const erc = workflow.erc ? ercReport(workflow.erc) : nestedRecord(workflow.schematic, "erc_report");
  const { text } = useI18n();
  return <PageFrame eyebrow="SCHEMATIC / ERC" title="Schematic & ERC" description="Generated schematic metadata and executable ERC state are explicit. UNKNOWN is not rendered as PASS." actions={<><button className="ghost-button" disabled={!workflow.circuit || Boolean(busy)} onClick={() => void onGenerateSchematic()}>{text("Generate schematic")}</button><button className="primary-button" disabled={!schematic.id || Boolean(busy)} onClick={() => void onRunErc()}>{text("Run ERC")}</button></>}><div className="two-column"><div className="panel-card"><PanelTitle label="Artifact" title="Generated schematic" /><KeyValueList values={{ "Artifact ID": shortId(schematic.artifact_id), Format: stringValue(schematic.format), "Content hash": shortId(schematic.content_hash, 18), "Input hash": shortId(schematic.input_hash, 18), "ERC executed": erc.executed === true ? "YES" : "NO" }} /></div><div className="panel-card"><PanelTitle label="Electrical Rule Check" title="Tool result" /><div className="result-header"><StatusPill status={erc.status as string | undefined} /><span>{erc.executed === true ? text("Executed") : text("Not executed")}</span></div><p className="muted">{stringValue(erc.recommendation, text("Run ERC to receive tool-backed results."))}</p><div className="rule-list">{asArray(erc.issues).map((issue, index) => <RuleRow key={index} rule={asRecord(issue)} />)}</div></div></div></PageFrame>;
}

function McuConfigPage({ workflow, onGenerateMcu, onGenerateFirmware, busy }: PageProps) {
  const config = workflow.mcuConfig;
  const { text } = useI18n();
  return <PageFrame eyebrow="FIRMWARE INPUT / MCU CONFIG" title="MCUConfigIR" description="Clock, GPIO, peripherals, DMA, IRQ, and FreeRTOS capability snapshot are shown from the backend configuration source of truth." actions={<><button className="ghost-button" disabled={!workflow.schematic || Boolean(busy)} onClick={() => void onGenerateMcu()}>{text("Generate MCUConfigIR")}</button><button className="primary-button" disabled={!config || Boolean(busy)} onClick={() => void onGenerateFirmware()}>{text("Generate FirmwareIR")}</button></>}><div className="metric-grid"><Metric label="Clock" value={stringValue(asRecord(config?.clock).source)} detail={JSON.stringify(asRecord(config?.clock).target_frequency ?? {})} /><Metric label="GPIO" value={String(asArray(config?.gpio).length)} detail="PinMap refs" /><Metric label="Peripherals" value={String(asArray(config?.peripherals).length)} detail="UART · CAN · SPI" /><Metric label="Interrupts" value={String(asArray(config?.interrupts).length)} detail="FreeRTOS handoff" /></div><div className="two-column"><div className="panel-card"><PanelTitle label="Peripheral facts" title="Configured interfaces" /><div className="table-wrap"><table><thead><tr><th>Instance</th><th>Mode</th><th>Parameters</th><th>Pin refs</th></tr></thead><tbody>{asArray(config?.peripherals).map((peripheral, index) => { const item = asRecord(peripheral); return <tr key={index}><td><strong>{stringValue(item.instance)}</strong></td><td>{stringValue(item.mode)}</td><td>{JSON.stringify(item.parameters ?? {})}</td><td>{asArray(item.pin_assignment_ids).length}</td></tr>; })}</tbody></table></div></div><div className="panel-card"><PanelTitle label="RTOS snapshot" title="FreeRTOS tasks" /><div className="mini-list">{asArray(asRecord(config?.capability_snapshot).rtos_profile && asRecord(asRecord(config?.capability_snapshot).rtos_profile).tasks).map((task, index) => { const item = asRecord(task); return <MiniRow key={index} label={stringValue(item.name)} value={`priority ${stringValue(item.priority)} · ${stringValue(item.stack_bytes)} bytes`} />; })}</div></div></div></PageFrame>;
}

function FirmwarePage({ workflow, onGenerateFirmware, onRunBuild, onRunStatic, busy, onNavigate }: PageProps) {
  const firmware = workflow.firmware;
  const files = asArray(firmware?.files);
  const target = asRecord(firmware?.build_target);
  const profile = workflow.build?.profile ?? target.profile;
  const toolchainId = workflow.build?.toolchain_id ?? target.toolchain_id;
  const targetTriple = target.target_triple;
  const outputFormat = stringValue(target.output_format, "ELF").toUpperCase();
  const artifactName = workflow.build?.artifact_hash
    ? `${stringValue(target.output_name, "eea_device")}.${outputFormat.toLowerCase()}`
    : "UNKNOWN";
  const cppcheck = asArray(workflow.staticAnalysis?.tool_results).map(asRecord).find((item) => item.tool_id === "cppcheck");
  const { text } = useI18n();
  return <PageFrame eyebrow="FIRMWARE / SOURCE" title="Firmware & SourceRevision" description="Generated files, SourceRevision binding, DependencyLock, DEVICE build artifact, and static analysis stay connected to backend IDs and hashes." actions={<><button className="ghost-button" disabled={!workflow.mcuConfig || Boolean(busy)} onClick={() => void onGenerateFirmware()}>{text("Generate DEVICE FirmwareIR")}</button><button className="primary-button" disabled={!firmware || Boolean(busy)} onClick={() => void onRunBuild()}>{text("Run DEVICE build")}</button><button className="ghost-button" disabled={!firmware || Boolean(busy)} onClick={() => void onRunStatic()}>{text("Run static")}</button></>}>
    <div className="metric-grid">
      <Metric label="Build profile" value={profile} detail="Backend BuildRun" testId="build-profile" />
      <Metric label="Build status" value={workflow.build?.status} detail={shortId(workflow.build?.id)} testId="build-status" />
      <Metric label="Artifact" value={artifactName} detail={outputFormat} testId="build-artifact" />
      <Metric label="Static" value={workflow.staticAnalysis?.status} detail={`${asArray(workflow.staticAnalysis?.rule_results).length} rules`} testId="static-status" />
    </div>
    <div className="two-column">
      <div className="panel-card"><PanelTitle label="DEVICE source authority" title="Dependency & revision binding" /><div className="mini-list">
        <EvidenceValue label="DependencyLock" value={stringValue(workflow.dependencyLock?.id ?? firmware?.dependency_lock_id)} testId="dependency-lock-id" />
        <EvidenceValue label="DependencyLock hash" value={stringValue(workflow.dependencyLock?.lock_hash ?? firmware?.dependency_lock_hash)} testId="dependency-lock-hash" />
        <EvidenceValue label="SourceRevision" value={stringValue(firmware?.source_revision_id)} testId="source-revision-id" />
        <EvidenceValue label="BuildInputSnapshot" value={stringValue(workflow.build?.build_input_snapshot_id)} testId="build-input-snapshot-id" />
        <EvidenceValue label="Toolchain" value={`${stringValue(toolchainId)} ${stringValue(workflow.build?.toolchain_version)}`.trim()} testId="build-toolchain" />
        <EvidenceValue label="Target" value={stringValue(targetTriple)} testId="build-target" />
        <EvidenceValue label="Artifact SHA256" value={stringValue(workflow.build?.artifact_hash)} testId="build-artifact-sha256" />
      </div></div>
      <div className="panel-card"><PanelTitle label="Deterministic evidence" title="Cppcheck & firmware release rules" /><EvidenceValue label="Cppcheck" value={stringValue(cppcheck?.status)} testId="cppcheck-status" /><div className="rule-list">{asArray(workflow.staticAnalysis?.rule_results).map((rule, index) => <RuleRow key={index} rule={asRecord(rule)} testId={`firmware-rule-${stringValue(asRecord(rule).rule_id, String(index))}`} />)}</div></div>
    </div>
       <div className="panel-card"><PanelTitle label="Source workspace" title="Generated files" action={<button className="ghost-button" onClick={() => onNavigate("settings")}>{text("Workspace settings")}</button>} /><div className="file-tree">{files.length === 0 ? <EmptyState text="Source files are backend-owned; generate DEVICE FirmwareIR to bind the authoritative revision." /> : files.slice(0, 30).map((file, index) => { const item = asRecord(file); return <div className="file-row" key={index}><span className="file-icon">{String(item.path).endsWith("/") ? "▾" : "·"}</span><span>{stringValue(item.path)}</span><span className="file-hash">{shortId(item.content_hash, 14)}</span></div>; })}</div></div>
  </PageFrame>;
}

function ProtocolPage({ workflow, onGenerateProtocol, busy }: PageProps) {
  const { text } = useI18n();
  return <PageFrame eyebrow="INTERFACE / PROTOCOL" title="ProtocolIR" description="CAN and UART transports share one backend ProtocolIR; outputs refresh from the same protocol revision." actions={<button className="primary-button" disabled={Boolean(busy)} onClick={() => void onGenerateProtocol()}>{text("Generate outputs")}</button>}><div className="two-column"><div className="panel-card"><PanelTitle label="Protocol definition" title={stringValue(workflow.protocol?.version_label, "No ProtocolIR")} /><div className="chip-list">{asArray(workflow.protocol?.transports).map((transport, index) => <span className="data-chip" key={index}>{stringValue(asRecord(transport).name)} · {stringValue(asRecord(transport).transport_type)}</span>)}</div><div className="mini-list">{asArray(workflow.protocol?.messages).map((message, index) => <MiniRow key={index} label={stringValue(asRecord(message).name, `Message ${index + 1}`)} value={`${stringValue(asRecord(message).transport_ref)} · ${stringValue(asRecord(message).payload_length_bytes)} bytes`} />)}</div></div><div className="panel-card"><PanelTitle label="Generated outputs" title={`${asArray(workflow.protocolOutputs?.outputs).length} artifacts`} /><div className="output-list">{asArray(workflow.protocolOutputs?.outputs).map((output, index) => { const item = asRecord(output); return <details className="output-item" key={index}><summary><strong>{stringValue(item.target)}</strong><span>{stringValue(item.path)}</span><span className="muted">{shortId(item.content_hash, 14)}</span></summary><pre>{stringValue(item.content, text("No output content"))}</pre></details>; })}</div></div></div></PageFrame>;
}

function TestsPage({ workflow, onRunTests, busy, onNavigate }: PageProps) {
  const cases = asArray(workflow.tests?.test_ir && asRecord(workflow.tests.test_ir).cases);
  const { text } = useI18n();
  return <PageFrame eyebrow="VERIFICATION / TESTS" title="Tests & TestRun" description="The UI distinguishes deterministic software verification from future physical hardware commissioning." actions={<button className="primary-button" disabled={!workflow.firmware || Boolean(busy)} onClick={() => void onRunTests()}>{text("Generate & run software tests")}</button>}><div className="metric-grid"><Metric label="TestIR" value={shortId(asRecord(workflow.tests?.test_ir).id)} detail={`${cases.length} cases`} /><Metric label="TestRun" value={statusLabel(workflow.testRun?.status as string | undefined)} detail={shortId(workflow.testRun?.id)} /><Metric label="Authority" value="DETERMINISTIC_VERIFICATION" detail="Backend executor" /><Metric label="Hardware" value="NOT RUN" detail="REAL_HARDWARE is separate" /></div><div className="panel-card"><PanelTitle label="Case results" title="Software verification" action={<button className="ghost-button" onClick={() => onNavigate("review")}>{text("Open Review")}</button>} /><div className="table-wrap"><table><thead><tr><th>Code</th><th>Type</th><th>Expected</th><th>Status</th><th>Duration</th></tr></thead><tbody>{asArray(workflow.testRun?.case_results).map((result, index) => { const item = asRecord(result); return <tr key={index}><td><strong>{stringValue(item.test_case_code)}</strong></td><td>{stringValue(item.executor_id, "Software")}</td><td>{stringValue(item.message, "Deterministic case")}</td><td><StatusPill status={item.status as string | undefined} /></td><td>{numberValue(item.duration_ms)} ms</td></tr>; })}</tbody></table></div>{!workflow.testRun && <EmptyState text="Generate and run software tests to populate deterministic case results." />}</div></PageFrame>;
}

function ReviewPage({ workflow, context, onTraceability, onReview, busy, onNavigate }: PageProps) {
  const coverage = asRecord(workflow.traceability?.coverage);
  const erc = workflow.erc ? ercReport(workflow.erc) : nestedRecord(workflow.schematic, "erc_report");
  const caseResults = asArray(workflow.testRun?.case_results).map(asRecord);
  const passedCases = caseResults.filter((item) => item.status === "PASS").length;
  const traceabilityStatus = traceabilityReleaseStatus(workflow.traceability);
  const gateStatus = releaseGateStatus(workflow);
  const { text } = useI18n();
  return <PageFrame eyebrow="RELEASE GATE" title="Review" description="One closeout surface for DEVICE Build, Static Analysis, ERC, Tests, Traceability, Impact, and deterministic findings." actions={<><button className="ghost-button" disabled={!workflow.firmware || Boolean(busy)} onClick={() => void onTraceability()}>{text("Refresh traceability")}</button><button className="primary-button" disabled={!workflow.firmware || Boolean(busy)} onClick={() => void onReview()}>{text("Run Review")}</button></>}>
    <div className="metric-grid">
      <Metric label="Build" value={workflow.build?.status} detail={String(workflow.build?.profile ?? "UNKNOWN")} testId="build-status" />
      <Metric label="Static" value={workflow.staticAnalysis?.status} detail={shortId(workflow.staticAnalysis?.id)} testId="static-status" />
      <Metric label="ERC" value={erc.status} detail={erc.executed === true ? "Executed" : "Not executed"} testId="erc-status" />
      <Metric label="TestRun" value={workflow.testRun?.status} detail={`${passedCases}/${caseResults.length} PASS`} testId="test-run-status" />
    </div>
    <div className="review-banner" data-testid="release-gate"><div><span className="eyebrow">M21 DEVICE RELEASE GATE</span><h2 data-testid="release-gate-status">{gateStatus}</h2><p>{gateStatus === "PASS" ? "All required backend gates returned explicit PASS." : "UNKNOWN, missing, BLOCKED, or FAIL evidence cannot close this release gate."}</p></div><StatusPill status={gateStatus} /></div>
    <div className="review-banner"><div><span className="eyebrow">DETERMINISTIC REVIEW</span><h2 data-testid="review-status">{statusLabel(workflow.review?.status as string | undefined)}</h2><p>{workflow.review ? `${asArray(workflow.review.findings).length} findings · ${asArray(workflow.review.issue_ids).length} linked issues` : "Review has not run for this SourceRevision."}</p></div><StatusPill status={typeof workflow.review?.status === "string" ? workflow.review.status : undefined} /></div>
    <div className="two-column"><div className="panel-card"><PanelTitle label="Traceability" title="Requirement → Claim → Pin → MCU → Firmware → Test" /><EvidenceValue label="Release traceability" value={traceabilityStatus} testId="traceability-status" /><KeyValueList values={{ "Release-critical requirements": displayCount(coverage.release_critical_requirements), "Total requirements": displayCount(coverage.total_requirements), "Design coverage": typeof coverage.design_coverage_ratio === "number" ? `${Math.round(coverage.design_coverage_ratio * 100)}%` : "UNKNOWN", "Verification coverage": typeof coverage.verification_coverage_ratio === "number" ? `${Math.round(coverage.verification_coverage_ratio * 100)}%` : "UNKNOWN", "Uncovered": displayCount(asArray(coverage.uncovered_requirement_ids).length), "Unknown": displayCount(asArray(coverage.unknown_requirement_ids).length), "Stale": displayCount(asArray(coverage.stale_requirement_ids).length) }} /><EvidenceValue label="Software cases" value={`${passedCases}/${caseResults.length} PASS`} testId="test-case-summary" /><button className="ghost-button full-width" onClick={() => onNavigate("dashboard")}>{text("View project health")}</button></div><div className="panel-card"><PanelTitle label="Findings / issues" title="Blockers stay visible" /><div className="rule-list">{asArray(workflow.review?.findings).map((finding, index) => <RuleRow key={index} rule={asRecord(finding)} />)}{context.issues.slice(0, 5).map((issue) => <IssueRow key={String(issue.id)} issue={issue} />)}{!workflow.review && context.issues.length === 0 && <EmptyState text="No review findings loaded." />}</div></div></div>
  </PageFrame>;
}

function DomainsPage({ context, onActivateDomain, onDeactivateDomain, busy }: PageProps) {
  const activeIds = new Set(context.domains.filter((item) => item.status === "ACTIVE").map((item) => String(item.domain_id)));
  const { text } = useI18n();
  return <PageFrame eyebrow="EXTENSIONS / DOMAINS" title="Domain Extensions" description="Navigation and panels are backend-supplied descriptors. There is no MotorControl-specific branch in the Core renderer." actions={<span className="status-pill tone-neutral">{activeIds.size} {text("active domains")}</span>}><div className="domain-grid">{context.availableDomains.map((available, index) => { const descriptor = asRecord(available.descriptor); const id = stringValue(descriptor.id, `domain-${index}`); const active = available.active === true || activeIds.has(id); return <div className={`domain-card ${active ? "active" : ""}`} key={id}><div className="domain-card-top"><span className="domain-status">{active ? text("ACTIVE") : text("AVAILABLE")}</span><span className="extension-badge">{stringValue(descriptor.trust_tier)}</span></div><h2>{stringValue(descriptor.name, id)}</h2><p>{stringValue(descriptor.plugin_id)} · v{stringValue(descriptor.version)}</p><div className="chip-list">{asArray(descriptor.capabilities).slice(0, 4).map((capability, capIndex) => <span className="data-chip" key={capIndex}>{String(capability)}</span>)}</div>{active ? <button className="ghost-button" data-testid={`domain-deactivate-${id}`} disabled={Boolean(busy)} onClick={() => void onDeactivateDomain(id)}>{text("Deactivate")}</button> : <button className="primary-button" data-testid={`domain-activate-${id}`} disabled={Boolean(busy)} onClick={() => void onActivateDomain(id)}>{text("Activate")}</button>}</div>; })}</div>{context.availableDomains.length === 0 && <EmptyState text="Backend reports no available domains. Core navigation remains domain-neutral." />}<div className="panel-card dynamic-contract"><PanelTitle label="Dynamic UI contract" title="Backend metadata → navigation / panel / form" /><p>{text("Each active domain contributes descriptors with extension_id, kind, label, route, schema, and optional action. The renderer registers them generically, so inactive MotorControl does not appear and an activated future domain can add its own surface.")}</p><div className="extension-list">{context.extensions.map((extension) => <MiniRow key={extension.extension_id} label={extension.label} value={`${extension.kind} · ${extension.route}`} />)}{context.extensions.length === 0 && <EmptyState text="No active domain UI extensions." />}</div></div></PageFrame>;
}

function SettingsPage({ context }: PageProps) {
  const { locale, setLocale, text } = useI18n();
  return <PageFrame eyebrow="SYSTEM" title="Settings" description="Runtime, tool availability, workspace, and appearance settings. Secrets remain in backend SecretService paths; the browser has no credential storage." actions={<span className="status-pill tone-pass">{text("SECURE SESSION")}</span>}><div className="settings-grid"><div className="panel-card"><PanelTitle label="Runtime" title="Desktop connection" /><KeyValueList values={{ Backend: "127.0.0.1 loopback", Authentication: "Tauri IPC → Bearer closure", CSP: "Strict self + loopback", "Navigation isolation": "Enabled", "Source state": stringValue(context.source?.dirty === true ? "DIRTY" : "CURRENT") }} /></div><div className="panel-card"><PanelTitle label="Workspace" title="Safe defaults" /><KeyValueList values={{ "Stale objects": displayCount(asRecord(context.consistency?.engineering_freshness).stale), "Open issues": displayCount(context.issues.length), "Local paths": "Backend-owned", Appearance: "Engineering dark" }} /></div></div><div className="panel-card language-card"><PanelTitle label="Language" title="Language" /><label className="field-label" htmlFor="locale-select">{text("Language")}</label><select id="locale-select" data-testid="locale-select" value={locale} onChange={(event) => setLocale(event.target.value as typeof locale)}><option value="zh-CN">{text("中文")}</option><option value="en-US">{text("English")}</option></select><p className="muted">{locale === "zh-CN" ? "默认语言为中文；设置仅保存在本地浏览器配置中。" : "The default language is Chinese; this preference is stored only in local settings."}</p></div><div className="panel-card security-note"><span className="eyebrow">{text("SECURITY INVARIANTS")}</span><p>{text("Runtime bearer token is not placed in URL, localStorage, sessionStorage, DOM, or logs. Renderer receives only an authenticated BackendClient from the Tauri-managed bootstrap.")}</p></div></PageFrame>;
}

function AiPage({ aiPrompt, setAiPrompt, aiResult, onAskAi, busy }: PageProps) {
  const { text } = useI18n();
  return <PageFrame eyebrow="ASSIST / CONTROLLED AI" title="AI Panel" description="A constrained assistant for requirement help and issue explanation. It cannot override compiler, ERC, Pin, Build, or Review truth." actions={<button className="primary-button" disabled={!aiPrompt.trim() || Boolean(busy)} onClick={() => void onAskAi()}>{text("Generate suggestion")}</button>}><div className="two-column"><div className="panel-card form-card"><PanelTitle label="Structured generation" title="Ask about this project" /><label className="field-label" htmlFor="ai-question">{text("Question or requirement context")}</label><textarea id="ai-question" value={aiPrompt} onChange={(event) => setAiPrompt(event.target.value)} placeholder={text("Explain why the current review is blocked…")} rows={8} /><p className="muted">{text("The request is sent through the existing authenticated backend AI foundation. No autonomous multi-agent action is exposed.")}</p></div><div className="panel-card"><PanelTitle label="Suggestion" title="Schema-constrained result" />{aiResult ? <KeyValueList values={{ Profile: `${stringValue(aiResult.profile_name)} v${stringValue(aiResult.profile_version)}`, Completeness: stringValue(asRecord(aiResult.completeness).status), "Follow-up questions": String(asArray(aiResult.follow_up_questions).length), "Canonical requirements": String(asArray(aiResult.requirements).length) }} /> : <EmptyState text="No AI suggestion yet. Deterministic engineering state remains authoritative." />}</div></div></PageFrame>;
}

function ExtensionPage({ extension }: PageProps & { extension?: DomainUIContribution }) {
  return <PageFrame eyebrow="DOMAIN EXTENSION" title={extension?.label ?? "Extension"} description="This surface was registered from backend UI metadata. It is not a Core hardcoded domain page."><div className="panel-card"><PanelTitle label={extension?.kind ?? "extension"} title={extension?.extension_id ?? "Unknown extension"} /><p className="muted">Route: {extension?.route ?? "—"}</p><div className="schema-preview"><span className="eyebrow">DESCRIPTOR SCHEMA</span><pre>{JSON.stringify(extension?.json_schema ?? {}, null, 2)}</pre></div></div></PageFrame>;
}

function Metric({ label, value, detail, testId }: { label: string; value: unknown; detail: string; testId?: string }) {
  const { text } = useI18n();
  const rendered = typeof value === "string" ? value : String(value ?? "UNKNOWN");
  return <div className="metric-card" data-testid={testId} data-value={rendered}><span className="metric-label">{text(label)}</span><strong className={`metric-value ${statusTone(rendered).startsWith("pass") ? "metric-pass" : ""}`}>{statusLabel(rendered)}</strong><span className="metric-detail">{text(detail)}</span></div>;
}

function StatusPill({ status, label }: { status?: string | null; label?: string }) {
  return <span className={`status-pill tone-${statusTone(status)}`}>{label ?? statusLabel(status)}</span>;
}

function PanelTitle({ label, title, action }: { label: string; title: string; action?: React.ReactNode }) {
  const { text } = useI18n();
  return <div className="panel-title"><div><span className="panel-kicker">{text(label)}</span><h2>{text(title)}</h2></div>{action}</div>;
}

function ActionRow({ title, detail, onClick, disabled }: { title: string; detail: string; onClick: () => Promise<void>; disabled?: boolean }) {
  const { text } = useI18n();
  return <button className="action-row" disabled={disabled} onClick={() => void onClick()}><span><strong>{text(title)}</strong><small>{text(detail)}</small></span><span className="chevron">›</span></button>;
}

function ContextRow({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();
  return <div className="context-row"><span>{text(label)}</span><strong>{text(value)}</strong></div>;
}

function KeyValueList({ values }: { values: Record<string, string> }) {
  const { text } = useI18n();
  return <dl className="key-value-list">{Object.entries(values).map(([key, value]) => <div key={key}><dt>{text(key)}</dt><dd title={value}>{text(value)}</dd></div>)}</dl>;
}

function ReadOnlyField({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();
  return <div className="readonly-field"><span>{text(label)}</span><strong>{text(value)}</strong></div>;
}

function MiniRow({ label, value }: { label: string; value: string }) {
  const { text } = useI18n();
  return <div className="mini-row"><span>{text(label)}</span><strong>{text(value)}</strong></div>;
}

function EvidenceValue({ label, value, testId }: { label: string; value: string; testId: string }) {
  const { text } = useI18n();
  const rendered = value || "UNKNOWN";
  return <div className="mini-row" data-testid={testId} data-value={rendered}><span>{text(label)}</span><strong title={rendered}>{text(rendered)}</strong></div>;
}

function ObjectSummary({ label, items }: { label: string; items: unknown }) {
  const { text } = useI18n();
  return <div className="object-summary"><span className="metric-label">{text(label)}</span><strong>{asArray(items).length}</strong><span className="muted">{text("backend objects")}</span></div>;
}

function RuleRow({ rule, testId }: { rule: JsonRecord; testId?: string }) {
  const { text } = useI18n();
  const status = rule.status ?? rule.severity;
  return <div className="rule-row" data-testid={testId} data-status={stringValue(status)}><StatusPill status={status as string | undefined} /><span><strong>{text(stringValue(rule.rule_id ?? rule.code ?? rule.title, "Rule result"))}</strong><small>{text(stringValue(rule.message ?? rule.recommendation, "No diagnostic message"))}</small></span></div>;
}

function IssueRow({ issue }: { issue: JsonRecord }) {
  return <div className="issue-row"><StatusPill status={issue.severity as string | undefined} /><span><strong>{stringValue(issue.title, stringValue(issue.code, "Issue"))}</strong><small>{stringValue(issue.description)}</small></span><span className="muted">{stringValue(issue.status)}</span></div>;
}

function EmptyState({ text: message }: { text: string }) {
  const { text } = useI18n();
  return <div className="empty-state"><span className="empty-icon">○</span><span>{text(message)}</span></div>;
}

function CopyValue({ value, label }: { value: string; label: string }) {
  const { text } = useI18n();
  const copy = async () => { await navigator.clipboard?.writeText(value); };
  return <button className="ghost-button" onClick={() => void copy()}>{text(label)}</button>;
}

function CreateProjectDialog({ name, description, setName, setDescription, onClose, onCreate, busy }: { name: string; description: string; setName: (value: string) => void; setDescription: (value: string) => void; onClose: () => void; onCreate: () => void; busy: boolean }) {
  const { text } = useI18n();
  return <div className="dialog-backdrop" role="presentation"><section className="dialog" role="dialog" aria-modal="true" aria-labelledby="create-project-title"><div className="panel-title"><div><span className="panel-kicker">{text("PROJECT")}</span><h2 id="create-project-title">{text("Create project")}</h2></div><button className="icon-button" onClick={onClose} aria-label={text("Close dialog")}>×</button></div><label className="field-label" htmlFor="project-name">{text("Name")}</label><input id="project-name" value={name} onChange={(event) => setName(event.target.value)} /><label className="field-label" htmlFor="project-description">{text("Description")}</label><textarea id="project-description" value={description} onChange={(event) => setDescription(event.target.value)} rows={4} /><div className="dialog-actions"><button className="ghost-button" data-testid="cancel-create-project" onClick={onClose}>{text("Cancel")}</button><button className="primary-button" data-testid="confirm-create-project" disabled={busy || !name.trim()} onClick={onCreate}>{busy ? text("Creating…") : text("Create project")}</button></div></section></div>;
}

function stageRoute(stage: string): string {
  const routes: Record<string, string> = { Requirement: "requirements", "Pin Map": "pin-planner", "Hardware / Circuit": "hardware", "Schematic / ERC": "schematic", "MCU Config": "mcu-config", "Firmware / Source": "firmware", Build: "firmware", "Static Analysis": "firmware", Protocol: "protocol", Tests: "tests", Traceability: "review", Review: "review" };
  return routes[stage] ?? "dashboard";
}
