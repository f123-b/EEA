import type { JobStatus } from "../api/generated";

export const jobStatusLabels: Record<JobStatus, string> = {
  QUEUED: "Queued",
  RUNNING: "Running",
  BLOCKED_PERMISSION: "Waiting for permission",
  BLOCKED_RESOURCE: "Waiting for resource",
  RECOVERING: "Recovering",
  SUCCESS: "Succeeded",
  FAILED: "Failed",
  FAILED_NEEDS_RECONCILE: "Needs reconciliation",
  CANCELLED: "Cancelled",
};

export const terminalJobStatuses = new Set<JobStatus>(["SUCCESS", "FAILED", "CANCELLED"]);

export function isTerminalJobStatus(status: JobStatus): boolean {
  return terminalJobStatuses.has(status);
}
