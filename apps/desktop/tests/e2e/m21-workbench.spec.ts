import { expect, test } from "@playwright/test";

test("renders the M20 generic benchmark workflow and release surfaces", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("M21 · DESKTOP ENGINEERING WORKBENCH")).toBeVisible();
  await page.getByRole("button", { name: "Projects" }).click();
  await page.getByRole("button", { name: "Create project" }).click();
  await page.getByLabel("Name").fill(`M20 UI E2E ${Date.now()}`);
  await page.getByLabel("Description").fill("M21 renderer benchmark");
  await page.getByRole("dialog").getByRole("button", { name: "Create project" }).click();
  await expect(page.locator("h1").filter({ hasText: /M20 UI E2E/ })).toBeVisible();

  await page.getByRole("button", { name: "Requirements", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Requirements" })).toBeVisible();
  await page.getByRole("button", { name: "Analyze M20 profile" }).click();
  await expect(page.getByText("Analysis result")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("embedded-controller-benchmark")).toBeVisible();

  await page.getByRole("button", { name: "Run M20 UI workflow" }).click();
  await expect(page.getByText("Run M20 generic UI workflow · deterministic backend operation running")).toBeVisible();
  await expect(page.getByText("Run M20 generic UI workflow · deterministic backend operation running")).toBeHidden({ timeout: 150_000 });
  await expect(page.locator(".feedback-error")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Review" })).toBeVisible({ timeout: 150_000 });
  await expect(page.getByText("DETERMINISTIC REVIEW")).toBeVisible();
});

test("activates and deactivates domain UI from backend metadata", async ({ page }) => {
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
