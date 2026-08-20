import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

test("@release drives the M20 benchmark through the real DEVICE release gate", async ({ page }) => {
  test.setTimeout(900_000);
  await page.goto("/");
  await expect(page.getByText("M21 · DESKTOP ENGINEERING WORKBENCH")).toBeVisible();
  await page.getByRole("button", { name: "Projects" }).click();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Name").fill(`M20 UI E2E ${Date.now()}`);
  await page.getByLabel("Description").fill("M21 renderer benchmark");
  await page.getByRole("dialog").getByRole("button", { name: "Create project" }).click();
  await expect(page.locator("h1").filter({ hasText: /M20 UI E2E/ })).toBeVisible();

  await page.getByRole("button", { name: "Review", exact: true }).click();
  await expect(page.getByTestId("release-gate-status")).toHaveText("BLOCKED");

  await page.getByRole("button", { name: "Requirements", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Requirements" })).toBeVisible();
  await page.getByRole("button", { name: "Analyze M20 profile" }).click();
  await expect(page.getByText("Analysis result")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("embedded-controller-benchmark")).toBeVisible();

  await page.getByRole("button", { name: "Run M20 UI workflow" }).click();
  await expect(page.getByText("Run M20 generic UI workflow · deterministic backend operation running")).toBeVisible();
  await expect(page.getByText("Run M20 generic UI workflow · deterministic backend operation running")).toBeHidden({ timeout: 900_000 });
  const workflowError = page.locator(".feedback-error");
  if (await workflowError.count()) {
    throw new Error(`M21 DEVICE UI workflow failed: ${(await workflowError.innerText()).trim()}`);
  }
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible({ timeout: 900_000 });
  await expect(page.getByTestId("release-gate-status")).toHaveText("PASS");
  await expect(page.getByTestId("build-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("static-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("erc-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("erc-status")).toContainText("Executed");
  await expect(page.getByTestId("test-run-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("review-status")).toHaveText("PASS");
  await expect(page.getByTestId("traceability-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("test-case-summary")).toHaveAttribute("data-value", /^\d+\/\d+ PASS$/u);
  const releaseResults = {
    build: await page.getByTestId("build-status").getAttribute("data-value"),
    static_analysis: await page.getByTestId("static-status").getAttribute("data-value"),
    erc: await page.getByTestId("erc-status").getAttribute("data-value"),
    erc_executed: true,
    test_run: await page.getByTestId("test-run-status").getAttribute("data-value"),
    test_cases: await page.getByTestId("test-case-summary").getAttribute("data-value"),
    traceability: await page.getByTestId("traceability-status").getAttribute("data-value"),
    review: (await page.getByTestId("review-status").textContent())?.trim(),
    release_gate: (await page.getByTestId("release-gate-status").textContent())?.trim(),
  };

  await page.getByRole("button", { name: "Firmware", exact: true }).click();
  await expect(page.getByTestId("build-profile")).toHaveAttribute("data-value", "DEVICE");
  await expect(page.getByTestId("build-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("build-target")).toHaveAttribute("data-value", "arm-none-eabi");
  await expect(page.getByTestId("build-toolchain")).toHaveAttribute("data-value", /^arm-none-eabi-gcc\s+.+/u);
  await expect(page.getByTestId("build-artifact")).toHaveAttribute("data-value", "eea_device.elf");
  await expect(page.getByTestId("build-artifact-sha256")).toHaveAttribute("data-value", /^[0-9a-f]{64}$/u);
  await expect(page.getByTestId("dependency-lock-id")).not.toHaveAttribute("data-value", "UNKNOWN");
  await expect(page.getByTestId("dependency-lock-hash")).toHaveAttribute("data-value", /^[0-9a-f]{64}$/u);
  await expect(page.getByTestId("source-revision-id")).not.toHaveAttribute("data-value", "UNKNOWN");
  await expect(page.getByTestId("build-input-snapshot-id")).not.toHaveAttribute("data-value", "UNKNOWN");
  await expect(page.getByTestId("cppcheck-status")).toHaveAttribute("data-value", "PASS");
  const firmwareRules: Record<string, string | null> = {};
  for (const rule of ["APP_DIRECT_HAL_CALL", "ISR_BLOCKING_API", "DRIVER_DEPENDENCY_CYCLE", "MCUCONFIG_FIRMWARE_MISMATCH"]) {
    await expect(page.getByTestId(`firmware-rule-${rule}`)).toHaveAttribute("data-status", /^(PASS|NOT_APPLICABLE)$/u);
    firmwareRules[rule] = await page.getByTestId(`firmware-rule-${rule}`).getAttribute("data-status");
  }

  const evidenceDir = process.env.EEA_BUILD_EVIDENCE_DIR;
  if (!evidenceDir) throw new Error("EEA_BUILD_EVIDENCE_DIR is required for the M21 release gate");
  const elfName = readdirSync(evidenceDir).find((name) => name.endsWith(".elf"));
  if (!elfName) throw new Error("real DEVICE build did not publish an ELF artifact");
  const elf = readFileSync(join(evidenceDir, elfName));
  expect(elf.subarray(0, 4)).toEqual(Buffer.from([0x7f, 0x45, 0x4c, 0x46]));
  expect(elf.readUInt16LE(18)).toBe(0x28);
  const elfSha256 = createHash("sha256").update(elf).digest("hex");
  expect(await page.getByTestId("build-artifact-sha256").getAttribute("data-value")).toBe(elfSha256);
  const value = async (testId: string) => page.getByTestId(testId).getAttribute("data-value");
  mkdirSync(evidenceDir, { recursive: true });
  writeFileSync(join(evidenceDir, "m21-ui-release-summary.json"), JSON.stringify({
    dependency_lock_id: await value("dependency-lock-id"),
    dependency_lock_hash: await value("dependency-lock-hash"),
    source_revision_id: await value("source-revision-id"),
    build_input_snapshot_id: await value("build-input-snapshot-id"),
    profile: await value("build-profile"),
    toolchain: await value("build-toolchain"),
    target_triple: await value("build-target"),
    artifact: elfName,
    elf_size: elf.length,
    elf_sha256: elfSha256,
    arm_e_machine: "EM_ARM (0x28)",
    cppcheck: await value("cppcheck-status"),
    firmware_rules: firmwareRules,
    ...releaseResults,
  }, null, 2));
});

test("@ui activates and deactivates domain UI from backend metadata", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Projects" }).click();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Name").fill(`M21 Domain UI E2E ${Date.now()}`);
  await page.getByRole("dialog").getByRole("button", { name: "Create project" }).click();
  await page.getByRole("button", { name: "Domains", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Domain Extensions" })).toBeVisible();

  const motorCard = page.locator(".domain-card").filter({ hasText: /MotorControl|Motor Control/i }).first();
  await expect(motorCard).toBeVisible();
  const motorNav = page.locator(".sidebar .nav-item").filter({ hasText: /MotorControl|Motor Control/i });
  await expect(motorNav).toHaveCount(0);
  await motorCard.getByRole("button", { name: "Activate" }).click();
  await expect(motorNav.first()).toBeVisible({ timeout: 60_000 });
  await motorCard.getByRole("button", { name: "Deactivate" }).click();
  await expect(motorNav).toHaveCount(0, { timeout: 60_000 });
});
