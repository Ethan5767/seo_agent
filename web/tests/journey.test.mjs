import { test } from "node:test";
import assert from "node:assert/strict";

const { deriveJourney, JOURNEY_STEPS } = await import("../lib/journey.ts");

/**
 * The journey bar used to be decorative: `currentStep={4}` was hardcoded at both
 * call sites and Overview additionally passed `hasClient={true} hasScan={true}`,
 * so a brand-new account with no client and no scan was told it had reached
 * "Stage 4 of 6: Review Top Priorities" with the first three steps ticked green.
 *
 * A stage is now claimed only where there is evidence for it. These tests are
 * mostly about what must NOT be claimed.
 */

test("an empty account claims nothing", () => {
  const j = deriveJourney({});
  assert.equal(j.currentStep, 1);
  assert.deepEqual(j.steps.map((s) => s.status), Array(6).fill("upcoming").map((v, i) => (i === 0 ? "current" : v)));
});

test("null and malformed input do not throw", () => {
  for (const bad of [null, undefined, { client: null, report: null, plan: null }, { client: 7 }, { remediations: "no" }]) {
    const j = deriveJourney(bad);
    assert.equal(j.steps.length, 6);
    assert.ok(j.currentStep >= 1 && j.currentStep <= 6);
  }
});

test("a client alone completes step 1 and no more", () => {
  const j = deriveJourney({ client: { id: "c1" } });
  assert.equal(j.steps[0].status, "completed");
  assert.equal(j.steps[1].status, "current");
  assert.equal(j.currentStep, 2);
});

test("a scan with no Google connection still leaves step 2 outstanding", () => {
  // The steps are not a strict sequence: an audit runs without Search Console.
  // The bar must keep asking for the thing that is missing rather than marching
  // past it, so `current` is the lowest INCOMPLETE step, not the furthest reached.
  const j = deriveJourney({ client: { id: "c1" }, report: { seo: [{ code: "x", severity: "warn" }] } });
  assert.notEqual(j.steps[1].status, "completed", "Google is not connected, so step 2 is not done");
  assert.equal(j.steps[1].status, "current", "and it is the step the bar asks for");
  assert.equal(j.steps[2].status, "completed", "the audit did run, out of order");
  assert.equal(j.currentStep, 2);
});

test("a scan recorded on the client counts, even with no report in memory", () => {
  // Switching clients clears the in-memory report; the client row still knows.
  const j = deriveJourney({ client: { id: "c1", scans: 1 } });
  assert.equal(j.steps[2].status, "completed");
});

test("priorities need findings, not merely a scan", () => {
  const empty = deriveJourney({ client: { id: "c1" }, hasGsc: true, report: { seo: [] } });
  assert.equal(empty.steps[3].status, "upcoming", "a scan with no findings has nothing to review");

  const withWork = deriveJourney({
    client: { id: "c1" }, hasGsc: true,
    report: { seo: [{ code: "x", severity: "error" }] },
  });
  assert.equal(withWork.steps[3].status, "completed");
});

test("a plan worklist counts as something to review", () => {
  const j = deriveJourney({ client: { id: "c1" }, hasGsc: true, plan: { worklist: [{ code: "x" }] } });
  assert.equal(j.steps[3].status, "completed");
});

test("fixes complete only when a remediation really ran", () => {
  const base = { client: { id: "c1" }, hasGsc: true, report: { seo: [{ code: "x", severity: "error" }] } };
  assert.equal(deriveJourney(base).steps[4].status, "current");
  assert.equal(deriveJourney({ ...base, remediations: [] }).steps[4].status, "current");
  assert.equal(deriveJourney({ ...base, remediations: [{ id: "r1" }] }).steps[4].status, "completed");
  assert.equal(deriveJourney({ ...base, apply: { changelog: {} } }).steps[4].status, "completed");
});

test("tracking over time needs a second scan, because a trend needs two points", () => {
  const base = {
    client: { id: "c1", scans: 1 }, hasGsc: true,
    report: { seo: [{ code: "x", severity: "error" }] }, remediations: [{ id: "r1" }],
  };
  assert.equal(deriveJourney(base).steps[5].status, "current");
  assert.equal(deriveJourney({ ...base, client: { id: "c1", scans: 2 } }).steps[5].status, "completed");
});

test("a finished journey stays on the last step rather than inventing a seventh", () => {
  const j = deriveJourney({
    client: { id: "c1", scans: 3 }, hasGsc: true,
    report: { seo: [{ code: "x", severity: "error" }] }, remediations: [{ id: "r1" }],
  });
  assert.ok(j.steps.every((s) => s.status === "completed"));
  assert.equal(j.currentStep, 6);
  assert.equal(j.complete, true);
});

test("every step has a label and a description, and the ids are 1..6", () => {
  assert.equal(JOURNEY_STEPS.length, 6);
  JOURNEY_STEPS.forEach((s, i) => {
    assert.equal(s.id, i + 1);
    assert.ok(s.label && s.description, `step ${i + 1} needs a label and description`);
  });
});
