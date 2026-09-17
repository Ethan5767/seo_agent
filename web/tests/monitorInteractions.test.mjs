import { test } from "node:test";
import assert from "node:assert/strict";

const { moveWidget, saveWidget, deleteWidget } = await import("../lib/monitor/layout.ts");
const { loadMonitorLayout, saveMonitorLayout } = await import("../lib/monitor/types.ts");

const widget = (id, title = id) => ({ id, title, source: "gsc", chartType: "stat", metric: "clicks", width: "third" });

test("Monitor add action appends a widget", () => {
  assert.deepEqual(saveWidget([widget("one")], widget("two")).map((w) => w.id), ["one", "two"]);
});

test("Monitor edit action replaces one widget without changing order", () => {
  const rows = saveWidget([widget("one"), widget("two")], widget("one", "Edited title"));
  assert.deepEqual(rows.map((w) => w.id), ["one", "two"]);
  assert.equal(rows[0].title, "Edited title");
});

test("Monitor delete action removes only the selected widget", () => {
  assert.deepEqual(deleteWidget([widget("one"), widget("two")], "one").map((w) => w.id), ["two"]);
});

test("Monitor rearrange action swaps adjacent widgets and keeps boundary clicks inert", () => {
  const start = [widget("one"), widget("two"), widget("three")];
  assert.deepEqual(moveWidget(start, 1, "left").map((w) => w.id), ["two", "one", "three"]);
  assert.equal(moveWidget(start, 0, "left"), start);
  assert.equal(moveWidget(start, 2, "right"), start);
});

test("Monitor UI actions persist their final layout for the current browser and project", () => {
  const store = new Map();
  globalThis.window = {};
  globalThis.localStorage = {
    getItem: (key) => store.has(key) ? store.get(key) : null,
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  };
  const project = "interaction-test.example";
  const finalLayout = moveWidget(saveWidget(deleteWidget([widget("one"), widget("two")], "one"), widget("three")), 1, "left");
  saveMonitorLayout(project, finalLayout);
  assert.deepEqual(loadMonitorLayout(project).map((w) => w.id), ["three", "two"]);
});
