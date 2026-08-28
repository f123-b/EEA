import assert from "node:assert/strict";
import test from "node:test";

import { BackendRequestError } from "../src/api/m21.ts";
import { m20PinSpecs, m20RequirementPayload } from "../src/m21/benchmark.ts";
import {
  buildNavigation,
  coreNavigation,
  routeFromLocation,
  statusTone,
  statusFrom,
} from "../src/m21/uiModel.ts";

test("core navigation is domain-neutral and maps stable routes", () => {
  assert.equal(coreNavigation.some((item) => item.label.includes("Motor")), false);
  assert.equal(routeFromLocation("/requirements/details"), "requirements");
  assert.equal(routeFromLocation("/"), "dashboard");
  assert.equal(statusTone("PASS"), "pass");
  assert.equal(statusTone("UNKNOWN"), "unknown");
  assert.equal(statusTone("STALE"), "stale");
  assert.equal(statusFrom("RUNNING"), "RUNNING");
  assert.equal(statusFrom("not-a-status"), null);
});

test("dynamic domain metadata contributes navigation only when active", () => {
  const extension = {
    extension_id: "motor-control-ui",
    kind: "panel",
    label: "Motor Control",
    route: "domain/motor-control",
    schema: { fields: [{ name: "mode", type: "enum" }] },
  } as const;

  const navigation = buildNavigation([extension]);
  assert.equal(navigation.some((item) => item.route === extension.route), true);
  assert.equal(navigation.find((item) => item.route === extension.route)?.extension?.extension_id, extension.extension_id);
});

test("M20 benchmark payload preserves the generic controller contract", () => {
  const payload = m20RequirementPayload("project-1");
  assert.equal(payload.profile_name, "embedded-controller-benchmark");
  assert.equal(payload.profile_version, "1.0");
  assert.deepEqual(m20PinSpecs.map(([signal]) => signal), [
    "UART_TX",
    "UART_RX",
    "CAN_RX",
    "CAN_TX",
    "SPI_SCK",
    "SPI_MISO",
    "SPI_MOSI",
    "SPI_CS",
  ]);
  assert.equal(Array.isArray(payload.requirements), true);
});

test("backend failures remain structured for the renderer", () => {
  const error = new BackendRequestError("Validation failed", 422, "VALIDATION_ERROR", { field: "name" });
  assert.equal(error.name, "BackendRequestError");
  assert.equal(error.status, 422);
  assert.equal(error.code, "VALIDATION_ERROR");
  assert.deepEqual(error.details, { field: "name" });
});
