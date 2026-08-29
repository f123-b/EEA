import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const panelSource = readFileSync(new URL("../src/m21/M24APlanningPanel.tsx", import.meta.url), "utf8");

test("M24A planning panel exposes review-only controls", () => {
  assert.match(panelSource, /data-testid="m24a-create-requirement"/u);
  assert.match(panelSource, /data-testid="m24a-analyze-plan"/u);
  assert.match(panelSource, /data-testid="m24a-approve"/u);
  assert.match(panelSource, /data-testid="m24a-revision"/u);
  assert.match(panelSource, /data-testid="m24a-reject"/u);
  assert.match(panelSource, /PLAN ONLY · NO EXECUTION AUTHORITY/u);
  assert.doesNotMatch(panelSource, /<button[^>]*(?:execute|apply|run|deploy|flash)/iu);
});
