import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { marketFor, DEFAULT_MARKET } = await import("../lib/market.ts");

test("a country-code domain is measured in that country", () => {
  assert.deepEqual(marketFor("https://www.oriendainternationalhospital.com.kh/en"),
    { location_code: 2116, language_code: "en", country: "Cambodia" });
  assert.equal(marketFor("shop.co.uk").location_code, 2826);
  assert.equal(marketFor("example.com.au:443").country, "Australia");
});

test("any other domain is United States, stated not guessed", () => {
  assert.deepEqual(marketFor("www.vertly.ink"), DEFAULT_MARKET);
  assert.deepEqual(marketFor("acme.com"), DEFAULT_MARKET);
  assert.deepEqual(marketFor(""), DEFAULT_MARKET);
});

test("every scan sends the project's market", () => {
  const app = readFileSync(new URL("../app/ScannerApp.tsx", import.meta.url), "utf8");
  const at = app.indexOf('authedFetch("/api/scan", {');
  const body = app.slice(at, at + 600);
  assert.match(body, /location_code: marketFor\(activeUrl\)\.location_code/);
  assert.match(body, /language_code: marketFor\(activeUrl\)\.language_code/);
});
