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
  assert.doesNotMatch(app, /histClient\?\.id \|\| clientId \|\| owner\?\.id/);
  assert.doesNotMatch(app, /site_url: \(finalAudit as any\)\.site_url \|\| baseReport\.site_url/);
});

/* ── one account, many projects: you choose, one domain per project ────────── */

const { pickScanProject, duplicateDomain } = await import("../lib/scanTarget.ts");

const TWO_ON_ONE_DOMAIN = [
  { id: "orienda-sep8", domain: "oriendainternationalhospital.com.kh" },
  { id: "test-test", domain: "www.oriendainternationalhospital.com.kh" },
];

test("the open project gets its scan even when another project shares the domain", () => {
  const url = "https://www.oriendainternationalhospital.com.kh/en";
  assert.equal(pickScanProject(TWO_ON_ONE_DOMAIN, TWO_ON_ONE_DOMAIN[1], url), "test-test");
  assert.equal(pickScanProject(TWO_ON_ONE_DOMAIN, TWO_ON_ONE_DOMAIN[0], url), "orienda-sep8");
});

test("a scan of another site never lands in the open project", () => {
  assert.equal(pickScanProject(TWO_ON_ONE_DOMAIN, TWO_ON_ONE_DOMAIN[1], "https://github.com"), null);
});

test("a second project for an existing domain is detected, www or not", () => {
  assert.equal(duplicateDomain(TWO_ON_ONE_DOMAIN, "https://oriendainternationalhospital.com.kh")?.id, "orienda-sep8");
  assert.equal(duplicateDomain(TWO_ON_ONE_DOMAIN, "vertly.ink"), null);
  // Editing a project may keep its own domain.
  assert.equal(duplicateDomain([TWO_ON_ONE_DOMAIN[0]], "oriendainternationalhospital.com.kh", "orienda-sep8"), null);
});

test("create and edit refuse a duplicate domain, and the client never bypasses it", () => {
  const read = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
  const create = read("../app/api/clients/route.ts");
  const edit = read("../app/api/clients/[id]/route.ts");
  const db = read("../lib/db.ts");
  const app = read("../app/ScannerApp.tsx");
  assert.match(create, /duplicateDomain\(\(mine as any\[\]\) \|\| \[\], cleanDomain\)[\s\S]{0,400}status: 409/);
  assert.match(edit, /duplicateDomain\(\(mine as any\[\]\) \|\| \[\], String\(patch\.domain\), id\)[\s\S]{0,300}status: 409/);
  assert.match(db, /res\.status === 409[\s\S]{0,200}existingId/);
  assert.match(app, /pickScanProject\(clients as any, histClient as any, activeUrl\)/);
});

test("a project is shown by its domain, with the business name only when it adds something", async () => {
  const { projectLabel, projectSubLabel } = await import("../lib/scanTarget.ts");
  const p = { id: "1", business: "Test Test", domain: "www.oriendainternationalhospital.com.kh" };
  assert.equal(projectLabel(p), "oriendainternationalhospital.com.kh");
  assert.equal(projectSubLabel(p), "Test Test");
  assert.equal(projectSubLabel({ id: "2", business: "vertly.ink", domain: "www.vertly.ink" }), "");
  assert.equal(projectLabel({ id: "3", business: "No site yet", domain: "" }), "No site yet");
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(dash, /\{c\.business \|\| c\.domain\}/, "project lists must label by domain");
  const modal = readFileSync(new URL("../components/dashboard/ProjectModal.tsx", import.meta.url), "utf8");
  assert.ok(modal.indexOf("Website URL *") < modal.indexOf("Business Name"), "URL comes first");
  assert.match(modal, /optional, defaults to the domain/);
});
