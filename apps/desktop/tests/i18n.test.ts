import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { resolve } from "node:path";

const root = resolve(import.meta.dirname, "../src/i18n");

test("desktop defaults to zh-CN and ships both locale catalogs", () => {
  const source = readFileSync(resolve(root, "index.ts"), "utf-8");
  const zhCN = JSON.parse(readFileSync(resolve(root, "zh-CN.json"), "utf-8")) as Record<string, string>;
  const enUS = JSON.parse(readFileSync(resolve(root, "en-US.json"), "utf-8")) as Record<string, string>;
  assert.match(source, /DEFAULT_LOCALE:\s*Locale\s*=\s*"zh-CN"/u);
  assert.equal(zhCN["Settings"], "设置");
  assert.equal(enUS["Settings"], "Settings");
  assert.equal(zhCN["Language"], "语言");
});

test("language selector persists only the local locale preference and broadcasts changes", () => {
  const source = readFileSync(resolve(root, "index.ts"), "utf-8");
  assert.match(source, /localStorage\.setItem\(LOCALE_STORAGE_KEY, nextLocale\)/u);
  assert.match(source, /window\.dispatchEvent\(new Event\(LOCALE_EVENT\)\)/u);
  assert.doesNotMatch(source, /sessionStorage\.setItem|document\.cookie|Authorization/u);
});
