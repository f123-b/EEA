import { createHash } from "node:crypto";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

test("@release drives the M20 benchmark through the real DEVICE release gate", async ({ page }) => {
  test.setTimeout(900_000);
  await page.goto("/");
  await expect(page.getByTestId("start-create-project")).toBeVisible();
  await page.getByTestId("nav-projects").click();
  await page.getByTestId("new-project").click();
  await page.locator("#project-name").fill(`M20 UI E2E ${Date.now()}`);
  await page.locator("#project-description").fill("M21 renderer benchmark");
  await page.getByTestId("confirm-create-project").click();
  await expect(page.locator("h1").filter({ hasText: /M20 UI E2E/ })).toBeVisible();

  await page.getByTestId("nav-review").click();
  await expect(page.getByTestId("release-gate-status")).toHaveText("BLOCKED");

  await page.getByTestId("nav-requirements").click();
  await expect(page.getByTestId("page-title")).toBeVisible();
  await page.getByTestId("analyze-m20-profile").click();
  await expect(page.getByText("embedded-controller-benchmark")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("embedded-controller-benchmark")).toBeVisible();

  await page.getByTestId("run-m20-workflow").click();
  await expect(page.getByTestId("run-m20-workflow")).toBeEnabled({ timeout: 900_000 });
  const workflowError = page.locator(".feedback-error");
  if (await workflowError.count()) {
    throw new Error(`M21 DEVICE UI workflow failed: ${(await workflowError.innerText()).trim()}`);
  }
  await expect(page.getByTestId("page-title")).toBeVisible({ timeout: 900_000 });
  await expect(page.getByTestId("release-gate-status")).toHaveText("PASS");
  await expect(page.getByTestId("build-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("static-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("erc-status")).toHaveAttribute("data-value", "PASS");
  await expect(page.getByTestId("erc-status")).toContainText(/Executed|已执行/u);
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

  await page.getByTestId("nav-firmware").click();
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
  await page.getByTestId("nav-projects").click();
  await page.getByTestId("new-project").click();
  await page.locator("#project-name").fill(`M21 Domain UI E2E ${Date.now()}`);
  await page.getByTestId("confirm-create-project").click();
  await page.getByTestId("nav-domains").click();
  await expect(page.getByTestId("page-title")).toBeVisible();

  const motorCard = page.locator(".domain-card").filter({ hasText: /MotorControl|Motor Control/i }).first();
  await expect(motorCard).toBeVisible();
  const motorNav = page.locator(".sidebar .nav-item").filter({ hasText: /MotorControl|Motor Control/i });
  await expect(motorNav).toHaveCount(0);
  await motorCard.locator("button").click();
  await expect(motorNav.first()).toBeVisible({ timeout: 60_000 });
  await motorCard.locator("button").click();
  await expect(motorNav).toHaveCount(0, { timeout: 60_000 });
});

test("@ui recalls memory and exposes canonical provenance with explicit history filtering", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-projects").click();
  await page.getByTestId("new-project").click();
  await page.locator("#project-name").fill(`M23R Memory UI E2E ${Date.now()}`);
  await page.getByTestId("confirm-create-project").click();
  await expect(page.locator("h1")).toHaveText(/M23R Memory UI E2E/u);
  const projectId = await page.getByTestId("current-project").inputValue();
  expect(projectId).not.toBe("");

  const created = await page.request.post("http://127.0.0.1:8765/api/v1/memory/entries", {
    headers: { Authorization: "Bearer m21-ui-e2e-token" },
    data: {
      project_id: projectId,
      scope: "PROJECT_PRIVATE",
      knowledge_type: "NOTE",
      title: "M23R canonical provenance memory",
      summary: "The canonical source remains authoritative.",
    },
  });
  expect(created.ok()).toBeTruthy();

  const panel = page.getByTestId("memory-panel");
  await panel.getByRole("textbox", { name: "记忆查询" }).fill("canonical provenance memory");
  await panel.getByTestId("memory-recall").click();
  await expect(panel.getByText("M23R canonical provenance memory")).toBeVisible();
  await expect(panel.getByTestId("memory-provenance")).toContainText(/Canonical claims|规范声明/u);
  await expect(panel.getByTestId("memory-include-history")).toBeVisible();
});

test("@ui defaults to Chinese and persists the Settings language switch", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "zh-CN");
  await page.getByTestId("nav-projects").click();
  await page.getByTestId("new-project").click();
  await page.locator("#project-name").fill(`M21 I18n E2E ${Date.now()}`);
  await page.getByTestId("confirm-create-project").click();
  await page.getByTestId("nav-settings").click();
  await expect(page.getByTestId("page-title")).toHaveText("设置");
  await page.getByTestId("locale-select").selectOption("en-US");
  await expect(page.locator("html")).toHaveAttribute("lang", "en-US");
  await expect(page.getByTestId("page-title")).toHaveText("Settings");
  const storedLocale = await page.evaluate(() => window.localStorage.getItem("eea.locale"));
  expect(storedLocale).toBe("en-US");
  await page.getByTestId("locale-select").selectOption("zh-CN");
  await expect(page.getByTestId("page-title")).toHaveText("设置");
});

test("@ui exposes the M24A plan-only requirement and review flow", async ({ page }) => {
  await page.goto("/");
  await page.getByTestId("nav-projects").click();
  await page.getByTestId("new-project").click();
  await page.locator("#project-name").fill(`M24A Planning UI E2E ${Date.now()}`);
  await page.getByTestId("confirm-create-project").click();
  await page.getByTestId("nav-planning").click();

  const panel = page.getByTestId("m24a-planning-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByText("PLAN ONLY · NO EXECUTION AUTHORITY")).toBeVisible();
  await expect(panel.getByTestId("m24a-create-requirement")).toBeVisible();
  await expect(panel.getByTestId("m24a-analyze-plan")).toBeDisabled();
  await panel.getByTestId("m24a-create-requirement").click();
  await expect(panel.getByTestId("m24a-analyze-plan")).toBeEnabled();
  await panel.getByTestId("m24a-analyze-plan").click();
  await expect(panel.getByText("STRUCTURED ENGINEERING PLAN")).toBeVisible();
  await expect(panel.getByTestId("m24a-approve")).toHaveText("Approve plan");
  await expect(panel.getByTestId("m24a-revision")).toHaveText("Request revision");
  await expect(panel.getByTestId("m24a-reject")).toHaveText("Reject plan");
  await expect(panel.locator("button").filter({ hasText: /execute|apply|run|deploy|flash/i })).toHaveCount(0);
});
