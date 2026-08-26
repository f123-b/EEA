import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { expect, test } from "@playwright/test";

test("M22R imports, reviews, creates a workspace, and exposes parser state", async ({ page }) => {
  const source = mkdtempSync(join(tmpdir(), "eea-m22r-e2e-"));
  mkdirSync(join(source, "src"));
  writeFileSync(join(source, "board.ioc"), "Mcu.Name=STM32G431CBUx\nPA0.Signal=GPIO_Output\n", "utf8");
  writeFileSync(join(source, "src", "main.c"), "int main(void) { return 0; }\n", "utf8");
  try {
    await page.goto("/");
    await page.getByTestId("nav-projects").click();
    await page.getByRole("button").filter({ hasText: /Import|导入/u }).first().click();
    await page.locator('input[placeholder*="projects"]').fill(source);
    await page.getByRole("button", { name: "Continue to Scan" }).click();
    await page.getByRole("button", { name: "Start scan" }).click();
    await expect(page.getByRole("heading", { name: "Project Understanding" })).toBeVisible();
    await expect(page.getByText("stm32-cubemx-ioc")).toBeVisible();
    await page.getByRole("button", { name: "Review candidates" }).click();
    await expect(page.getByText(/MCU_CONFIG/).first()).toBeVisible();
    await page.getByRole("button", { name: "Create workspace" }).click();
    await page.getByRole("button", { name: "Create workspace" }).click();
    await expect(page.getByRole("heading", { name: "Workspace created" })).toBeVisible();
    await expect(page.getByText("SourceRevision", { exact: true })).toBeVisible();
  } finally {
    rmSync(source, { recursive: true, force: true });
  }
});
