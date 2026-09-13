import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const { PIPELINE_STAGES, stage, laneCounts, actionableCount } =
  await import("../lib/pipelineStages.ts");

test("stage lookup is exhaustive and throws on an unknown id", () => {
  for (const s of PIPELINE_STAGES) assert.equal(stage(s.id).id, s.id);
  assert.throws(() => stage("measure"), /unknown pipeline stage/);
});

test("every stage declares whether its result is actually available", () => {
  // The distinction this module exists for. "We have no gate results" and "the
  // gates passed" must never render the same way — the shape of B-018, where a
  // gate that scanned nothing reported green. All three are wired now; the flag
  // stays because the next stage added may not be.
  for (const s of PIPELINE_STAGES) {
    assert.equal(typeof s.connected, "boolean", `${s.id}: connected must be explicit`);
  }
  assert.equal(stage("gate").connected, true,
    "gate reads the PR's check runs directly, so it is live once a repo is connected");
});

test("every disconnected stage explains why, and names what would fix it", () => {
  for (const s of PIPELINE_STAGES.filter((x) => !x.connected)) {
    assert.ok(s.absent.length > 40, `${s.id}: absent copy is too thin to be useful`);
    assert.ok(/not connected/i.test(s.absent),
      `${s.id}: must say plainly that it is not connected`);
    assert.ok(s.source.length > 0, `${s.id}: name the producer so an operator can go look`);
  }
});

test("no stage claims a verdict it cannot have", () => {
  const forbidden = /\b(passed|green|all clear|healthy|0 issues|no issues)\b/i;
  for (const s of PIPELINE_STAGES.filter((x) => !x.connected)) {
    assert.ok(!forbidden.test(s.absent),
      `${s.id}: absent copy implies a verdict for data nobody fetched`);
  }
});

test("lane counts are null when there is no worklist, never zeroes", () => {
  // A cycle that was never planned and a cycle that found nothing are different
  // facts. Zeroes would render as "0 regressions", which reads as good news.
  assert.equal(laneCounts(null), null);
  assert.equal(laneCounts([]), null);
  assert.deepEqual(
    laneCounts([{ status: "NEW" }, { status: "new" }, { status: "REGRESSION" }]),
    { NEW: 2, PERSISTING: 0, REGRESSION: 1, RESOLVED: 0 },
  );
});

test("actionable count is what the agent may attempt, not the worklist size", () => {
  const worklist = [
    { action: "fix", tier_blocked: false, human_edit: false },  // yes
    { action: "fix", tier_blocked: true, human_edit: false },   // above this tier
    { action: "fix", tier_blocked: false, human_edit: true },   // briefed to a human
    { tier_blocked: false, human_edit: false },                 // no action mapped
  ];
  assert.equal(actionableCount(worklist), 1,
    "a 4-item worklist where the agent can touch one is a one-item cycle");
  assert.equal(actionableCount([]), null);
});

test("the stages are reachable from the sidebar", () => {
  // B-007 again: a screen nobody can navigate to is not shipped. This module
  // is only worth anything if NAV_SECTIONS actually points at it.
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const nav = src.slice(src.indexOf("export const NAV_SECTIONS"), src.indexOf("export const RAIL_ICONS"));
  // Merge is deliberately NOT a section: merging is a button on the Gate
  // screen, because splitting the verdict from the action only adds a click.
  for (const id of ["Plan", "Fix", "Gate"]) {
    assert.ok(nav.includes(`id: "${id}"`), `${id} is not a section in NAV_SECTIONS`);
  }
  assert.ok(!nav.includes('id: "Merge"'), "Merge should be folded into Gate & Merge");
});

test("every new section has a rail icon", () => {
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const icons = src.slice(src.indexOf("export const RAIL_ICONS"), src.indexOf("export const RAIL_ICONS") + 900);
  for (const id of ["Plan", "Fix", "Gate"]) {
    assert.ok(new RegExp(`\\b${id}:`).test(icons), `${id} has no rail glyph`);
  }
});


// ── gate roster, merge policy, Fix stage (B-070) ─────────────────────────────

const { GATE_ROSTER, MERGE_POLICY, AUTOMERGE_DEFAULT_ENABLED, blockedReason } =
  await import("../lib/pipelineStages.ts");

test("the pipeline covers each stage once, in run order", () => {
  assert.deepEqual(PIPELINE_STAGES.map((s) => s.id), ["plan", "fix", "gate"]);
  assert.deepEqual(PIPELINE_STAGES.map((s) => s.step), [1, 2, 3]);
});

test("merging is reachable from the gate screen, not hidden behind another click", () => {
  // Folding Merge into Gate is only correct if the button actually lives there.
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const gate = src.slice(src.indexOf("GATE & MERGE"), src.indexOf("Stages with no result yet"));
  assert.ok(/mergePull\(pr\)/.test(gate), "the merge button must call mergePull");
  assert.ok(/disabled=\{!green/.test(gate),
    "merge must be disabled unless every gate is green — a red gate blocks the merge");
});

test("the Pipeline cover section is gone, its links rehomed", () => {
  // It was a lid over two unrelated destinations. Removing it is only safe if
  // both still have a home, or they silently disappear from the product.
  const src = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const nav = src.slice(src.indexOf("export const NAV_SECTIONS"), src.indexOf("export const RAIL_ICONS"));
  assert.ok(!/id: "Pipeline"/.test(nav), "the Pipeline cover section should be removed");
  assert.ok(/Review Fixes/.test(nav), "Review Fixes lost its home when Pipeline was removed");
  assert.ok(/Change History/.test(nav), "Change History lost its home when Pipeline was removed");
});

test("the gate roster matches what the workflow actually runs", () => {
  // Engine truth, mirrored. If the workflow gains or loses a gate this drifts,
  // so it is asserted against the real count rather than left to rot.
  // 21 checks: the 20 gate modules in pipeline/gates/, plus `tsc --noEmit`.
  assert.equal(GATE_ROSTER.length, 21, "21 checks run on a client PR");
  assert.equal(GATE_ROSTER.filter((g) => g.phase === "PRE").length, 6);
  assert.equal(GATE_ROSTER.filter((g) => g.phase === "OUT").length, 14);
  assert.equal(GATE_ROSTER.filter((g) => g.phase === "CHAIN").length, 1);
  for (const g of GATE_ROSTER) {
    assert.ok(g.blocks.length > 10, `${g.name}: say what it blocks on, in words a client reads`);
  }
});

test("the gate roster never implies a verdict", () => {
  // Showing WHICH gates run is honest. Showing that they passed is not, and the
  // roster is the easiest place to blur that line.
  const src = readFileSync(new URL("../lib/pipelineStages.ts", import.meta.url), "utf8");
  const roster = src.slice(src.indexOf("export const GATE_ROSTER"), src.indexOf("/* ── Merge policy"));
  assert.ok(!/\b(passed|green|clean|ok:)\b/i.test(roster),
    "the roster describes what each gate blocks on, never its result");
});

test("auto-merge is off by default for the whole fleet", () => {
  assert.equal(AUTOMERGE_DEFAULT_ENABLED, false);
});

test("the merge policy is escalate-when-unsure and ordered", () => {
  // The order IS the policy: the first failing condition routes to a human.
  assert.equal(MERGE_POLICY[0].condition, "Auto-merge is switched on for this client");
  assert.match(MERGE_POLICY[1].otherwise, /nothing was verified/);
  const text = MERGE_POLICY.map((r) => `${r.condition} ${r.otherwise}`).join(" ");
  for (const must of ["T1", "gate", "YMYL"]) {
    assert.ok(new RegExp(must, "i").test(text), `the policy must mention ${must}`);
  }
});

test("blockedReason names why an item is not actionable", () => {
  assert.equal(blockedReason({ action: "fix" }), null);
  assert.match(blockedReason({ action: "fix", tier_blocked: true }), /tier/);
  assert.match(blockedReason({ action: "fix", human_edit: true }), /human/);
  assert.match(blockedReason({}), /no automated fix/);
});
