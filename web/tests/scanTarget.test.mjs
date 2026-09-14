import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

/**
 * B-126, reproduced from the operator's saved data on 2026-09-14: a github.com
 * scan was filed under the open hospital project and later Site Health tests
 * merged into it, so the hospital's On-Page, Content, Schema, Internal links,
 * E-E-A-T and Video pages showed github.com findings.
 */
const { normDomain, ownerOf, sameSite } = await import("../lib/scanTarget.ts");

const PROJECTS = [
  { id: "hospital", domain: "www.oriendainternationalhospital.com.kh", website: "https://www.oriendainternationalhospital.com.kh" },
  { id: "acme", domain: "", website: "https://acme-roofing.com/" },
];

test("domains compare without scheme, www, path, port or case", () => {
  assert.equal(normDomain("https://WWW.Example.com:443/en?x=1"), "example.com");
  assert.equal(normDomain(""), "");
});

test("a scan is filed under the project that owns its domain", () => {
  assert.equal(ownerOf(PROJECTS, "https://www.oriendainternationalhospital.com.kh/en"), "hospital");
  assert.equal(ownerOf(PROJECTS, "acme-roofing.com"), "acme");
});

test("a domain no project owns belongs to no existing project (the github.com case)", () => {
  assert.equal(ownerOf(PROJECTS, "https://github.com"), null);
});

test("a scan merges only into a report of the same site", () => {
  assert.equal(sameSite("https://www.oriendainternationalhospital.com.kh/en", "https://oriendainternationalhospital.com.kh"), true);
  assert.equal(sameSite("https://www.oriendainternationalhospital.com.kh/en", "https://github.com"), false);
  assert.equal(sameSite("", "https://github.com"), false);
});

test("ScannerApp files by domain and merges only same-site reports", () => {
  const app = readFileSync(new URL("../app/ScannerApp.tsx", import.meta.url), "utf8");
  assert.match(app, /sameSite\(openReportUrl, activeUrl\)/);
  assert.match(app, /ownerOf\(clients as any, activeUrl\)/);
  assert.doesNotMatch(app, /histClient\?\.id \|\| clientId \|\| owner\?\.id/);
  assert.doesNotMatch(app, /site_url: \(finalAudit as any\)\.site_url \|\| baseReport\.site_url/);
});
