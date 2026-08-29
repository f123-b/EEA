import type { DomainUIContribution } from "../api/generated";
import type { JsonRecord, M21Status } from "../api/m21";

export type StatusTone = "pass" | "fail" | "blocked" | "unknown" | "stale" | "running" | "neutral";

export type NavigationItem = {
  id: string;
  label: string;
  route: string;
  icon: string;
  extension?: DomainUIContribution;
};

export const coreNavigation: NavigationItem[] = [
  { id: "dashboard", label: "Dashboard", route: "dashboard", icon: "⌂" },
  { id: "projects", label: "Projects", route: "projects", icon: "▦" },
  { id: "requirements", label: "Requirements", route: "requirements", icon: "≡" },
  { id: "planning", label: "Planning Copilot", route: "planning", icon: "✦" },
  { id: "documents", label: "Documents", route: "documents", icon: "▤" },
  { id: "pin-planner", label: "Pin Planner", route: "pin-planner", icon: "⌗" },
  { id: "hardware", label: "Hardware", route: "hardware", icon: "◈" },
  { id: "schematic", label: "Schematic / ERC", route: "schematic", icon: "⌁" },
  { id: "mcu-config", label: "MCU Config", route: "mcu-config", icon: "▣" },
  { id: "firmware", label: "Firmware", route: "firmware", icon: "{}" },
  { id: "protocol", label: "Protocol", route: "protocol", icon: "⇄" },
  { id: "tests", label: "Tests", route: "tests", icon: "✓" },
  { id: "review", label: "Review", route: "review", icon: "◉" },
  { id: "domains", label: "Domains", route: "domains", icon: "◇" },
  { id: "settings", label: "Settings", route: "settings", icon: "⚙" },
  { id: "ai", label: "AI Panel", route: "ai", icon: "✦" },
];

export const workflowStages = [
  "Requirement",
  "Pin Map",
  "Hardware / Circuit",
  "Schematic / ERC",
  "MCU Config",
  "Firmware / Source",
  "Build",
  "Static Analysis",
  "Protocol",
  "Tests",
  "Traceability",
  "Review",
] as const;

export function statusTone(status: string | null | undefined): StatusTone {
  switch (status?.toUpperCase()) {
    case "PASS":
    case "SUCCESS":
    case "CURRENT":
    case "COMPLETE":
    case "ACCEPTED":
      return "pass";
    case "FAIL":
    case "FAILED":
    case "INVALID":
    case "REJECTED":
      return "fail";
    case "BLOCKED":
    case "BLOCKED_PERMISSION":
    case "BLOCKED_RESOURCE":
      return "blocked";
    case "STALE":
    case "DEPRECATED":
      return "stale";
    case "RUNNING":
    case "QUEUED":
    case "RECOVERING":
      return "running";
    default:
      return "unknown";
  }
}

export function statusLabel(status: string | null | undefined): string {
  if (!status) return "UNKNOWN";
  return status.replaceAll("_", " ");
}

export function shortId(value: unknown, length = 12): string {
  if (typeof value !== "string" || value.length <= length) return typeof value === "string" ? value : "—";
  return `${value.slice(0, Math.max(4, length - 5))}…${value.slice(-4)}`;
}

export function asRecord(value: unknown): JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as JsonRecord : {};
}

export function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

export function stringValue(value: unknown, fallback = "—"): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

export function numberValue(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function statusFrom(value: unknown): M21Status | null {
  const status = typeof value === "string" ? value.toUpperCase() : null;
  if (status && ["PASS", "FAIL", "BLOCKED", "UNKNOWN", "STALE", "CURRENT", "RUNNING"].includes(status)) {
    return status as M21Status;
  }
  return null;
}

export function buildNavigation(extensions: DomainUIContribution[]): NavigationItem[] {
  const extensionItems = extensions.map((extension) => ({
    id: `extension:${extension.extension_id}`,
    label: extension.label,
    route: extension.route,
    icon: "✧",
    extension,
  }));
  return [...coreNavigation, ...extensionItems];
}

export function routeFromLocation(pathname: string): string {
  const route = pathname.replace(/^\//u, "").split("/")[0];
  return route || "dashboard";
}

export function isM20BenchmarkName(value: string): boolean {
  return value.toLowerCase().includes("m20") || value.toLowerCase().includes("stm32g431");
}
