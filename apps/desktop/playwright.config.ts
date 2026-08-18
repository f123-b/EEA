import process from "node:process";

import { defineConfig, devices } from "@playwright/test";

const root = process.cwd().replace(/[\\/]apps[\\/]desktop$/, "");
const token = "m21-ui-e2e-token";
const python = process.env.EEA_E2E_PYTHON ?? (process.platform === "win32" ? "py -3.12" : "python");

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  timeout: 180_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI ? [["line"], ["html", { outputFolder: "test-results/m21-report", open: "never" }]] : "line",
  use: {
    ...devices["Desktop Chrome"],
    baseURL: "http://127.0.0.1:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command: `${python} -m eea_cli db upgrade && ${python} -m eea_backend`,
      cwd: root,
      url: "http://127.0.0.1:8765/health",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        EEA_RUNTIME_HOST: "127.0.0.1",
        EEA_RUNTIME_PORT: "8765",
        EEA_SESSION_TOKEN: token,
        EEA_DATA_DIR: ".eea-m21-e2e",
        EEA_ENV: "development",
        EEA_INSECURE_LOCAL_DEV: "false",
      },
    },
    {
      command: "pnpm --filter @eea/desktop exec vite --host 127.0.0.1 --port 4173",
      cwd: root,
      url: "http://127.0.0.1:4173",
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        VITE_EEA_API_URL: "http://127.0.0.1:4173",
        VITE_EEA_SESSION_TOKEN: token,
      },
    },
  ],
});
