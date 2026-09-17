import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";

/**
 * Operator, 2026-09-15: "i click on Keyword Overview route keep using
 * /site-audit". Tool pages had no address; only tabs pushed one.
 */
const { navPath, parseNavPath } = await import("../lib/navPath.ts");

test("every non-tab sidebar item has an address, and the address opens it again", () => {
  for (const item of [{ view: "keyword-overview" }, { gsc: "gsc-queries" }, { gsc: "ga4-overview" }, { content: "brief" }, { stage: "plan" }]) {
    const path = navPath(item);
    assert.ok(path && path.startsWith("/"), JSON.stringify(item));
    assert.deepEqual(parseNavPath(path), item);
  }
  assert.equal(navPath({ tab: "Overview" }), null, "tabs keep their own routes");
  assert.deepEqual(parseNavPath("/site-audit"), {});
});

test("the routes exist, the sidebar pushes them, and back/forward restores them", () => {
  for (const kind of ["view", "gsc", "content", "stage"]) {
    const page = new URL(`../app/${kind}/[id]/page.tsx`, import.meta.url);
    assert.ok(existsSync(page), `/${kind}/[id] route missing`);
    assert.match(readFileSync(page, "utf8"), new RegExp(`initialNav=\\{\\{ ${kind}: decodeURIComponent\\(id\\) \\}\\}`));
  }
  const dash = readFileSync(new URL("../app/ReaiDashboard.tsx", import.meta.url), "utf8");
  const open = dash.slice(dash.indexOf("const openNavItem = useCallback"), dash.indexOf("}, [selectAeoFocus]);", dash.indexOf("const openNavItem = useCallback")));
  assert.match(open, /const path = navPath\(item\);/);
  assert.match(open, /window\.history\.pushState\(\{ nav: path \}, "", path\)/);
  assert.ok(open.indexOf("pushState") < open.indexOf("setActiveView(item.view)"));
  const pop = dash.slice(dash.indexOf("function handlePopState()"));
  assert.match(pop.slice(0, 600), /const nav = parseNavPath\(p\);/);
  for (const v of ["activeView", "activeGscView", "activeContentTool", "activeStage"]) {
    assert.match(dash, new RegExp(`const \\[${v}, set\\w+\\] = useState<[^>]+>\\(\\(?\\)? ?=?>? ?initialNav\\?\\.`), `${v} must start from the address`);
  }
});
