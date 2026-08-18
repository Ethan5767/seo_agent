// Shared shell + API client for wf-dashboard.
//
// The header and sidebar are injected here rather than duplicated into eight
// pages: one nav definition, one place to add a screen, nothing to drift.

// ── API ──────────────────────────────────────────────────────────────────────
// The token is injected into the served HTML. A cross-origin page can issue
// requests to localhost but CORS stops it reading the response, so it cannot
// learn the token and cannot forge this header.
async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      'X-Dashboard-Token': window.DASH_TOKEN || '',
      ...(opts.headers || {}),
    },
  });
  const body = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok) throw new Error(body.error || `HTTP ${res.status}`);
  return body;
}

const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body) });

// ── URL state ────────────────────────────────────────────────────────────────
// Which client and cycle a page is looking at lives in the query string. No
// router, no store: the URL is the state, and a screen is shareable by copying it.
const params = new URLSearchParams(location.search);
const currentSlug = () => params.get('client');
const currentCycle = () => params.get('cycle');
function withParams(path, extra = {}) {
  const p = new URLSearchParams(location.search);
  for (const [k, v] of Object.entries(extra)) v == null ? p.delete(k) : p.set(k, v);
  const q = p.toString();
  return q ? `${path}?${q}` : path;
}

// ── shell ────────────────────────────────────────────────────────────────────
// Deploy is deliberately absent: the dashboard stops at the PR. Deploy happens
// in Actions on the client repo after a human merges.
const NAV = [
  { href: '/fleet', icon: 'dns', label: 'Fleet', keepClient: false },
  { href: '/client', icon: 'group', label: 'Client', needsClient: true },
  { href: '/findings', icon: 'troubleshoot', label: 'Findings', needsClient: true },
  { href: '/worklist', icon: 'assignment', label: 'Worklist', needsClient: true },
  { href: '/review', icon: 'difference', label: 'Review Diff', needsClient: true },
  { href: '/report', icon: 'analytics', label: 'Report', needsClient: true },
  { href: '/changelog', icon: 'history', label: 'Changelog', needsClient: true },
  { href: '/runs', icon: 'terminal', label: 'Runs', needsClient: true },
  { href: '/git', icon: 'commit', label: 'Git / PR', needsClient: true },
  { href: '/config', icon: 'tune', label: 'Config', needsClient: true },
];

function renderShell() {
  const here = location.pathname === '/' ? '/fleet' : location.pathname;
  const slug = currentSlug();
  const items = NAV.map((n) => {
    const disabled = n.needsClient && !slug;
    const active = n.href === here;
    const href = n.keepClient === false ? n.href : withParams(n.href);
    const cls = active
      ? 'bg-secondary-container text-on-secondary-container border-l-2 border-primary'
      : disabled
        ? 'text-on-surface-variant/40 pointer-events-none border-l-2 border-transparent'
        : 'text-on-surface-variant hover:text-on-surface hover:bg-surface-container-highest border-l-2 border-transparent';
    const keep = n.keepClient === false ? '' : ` data-nav="${n.href}"`;
    return `<li><a href="${disabled ? '#' : href}"${keep} class="${cls} cursor-pointer flex items-center gap-sm px-md py-sm">
      <span class="material-symbols-outlined" style="font-size:16px">${n.icon}</span>
      <span class="font-label-caps text-label-caps">${n.label}</span></a></li>`;
  }).join('');

  document.body.insertAdjacentHTML('afterbegin', `
    <header class="fixed top-0 inset-x-0 bg-surface text-primary border-b border-outline-variant flex justify-between items-center h-12 px-md z-50">
      <a href="/fleet" class="font-headline-sm text-headline-sm font-bold tracking-tighter">wf-dashboard</a>
      <div class="flex items-center gap-md">
        <span id="shell-client" class="font-mono-sm text-mono-sm text-on-surface-variant"></span>
      </div>
    </header>
    <nav class="hidden md:flex fixed top-12 bottom-0 left-0 w-60 flex-col py-md bg-surface-container-low border-r border-outline-variant z-40">
      <div class="px-md mb-lg">
        <div class="font-headline-sm text-headline-sm font-bold text-primary mb-xs">OPERATOR</div>
        <div class="font-mono-sm text-mono-sm text-on-surface-variant">local · 127.0.0.1</div>
      </div>
      <ul class="flex flex-col">${items}</ul>
    </nav>`);
  if (slug) document.getElementById('shell-client').textContent = slug;
}

// The sidebar hrefs are built once from location.search. Anything that changes
// the query has to say so, or the links keep pointing at the state the page
// loaded with — which is how picking a cycle here still landed you on the
// newest one over there.
function syncNav() {
  document.querySelectorAll('nav a[data-nav]').forEach((a) => {
    if (a.getAttribute('href') !== '#') a.href = withParams(a.dataset.nav);
  });
}

// Every screen that lets you change cycle goes through here. Five selects used
// to change what was rendered without touching the URL, so the choice was lost
// the moment you moved screens.
function setCycle(ym) {
  history.replaceState(null, '', withParams(location.pathname, { cycle: ym }));
  syncNav();
}

// ── render helpers ───────────────────────────────────────────────────────────
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

// clean · dirty · ahead · behind · error are not interchangeable. `ahead` is the
// one that silently loses work: committed locally, invisible to everyone else.
const GIT_CHIP = {
  clean: 'border border-green-500/50 text-green-400',
  dirty: 'bg-tertiary-container text-on-tertiary-container',
  ahead: 'bg-primary-container text-on-primary-container',
  behind: 'border border-outline text-on-surface-variant',
  error: 'bg-error-container text-on-error-container',
};
const gitChip = (state) =>
  `<span class="${GIT_CHIP[state] || GIT_CHIP.error} font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm uppercase tracking-wider">${esc(state)}</span>`;

// A refusal must read as a refusal. A green "completed" chip on exit 19 destroys
// the distinction the exit code exists to protect.
const EXIT_CHIP = {
  clean: 'border border-green-500/50 text-green-400',
  findings: 'bg-primary-container text-on-primary-container',
  warn: 'bg-tertiary-container text-on-tertiary-container',
  refused: 'bg-error-container text-on-error-container',
  error: 'bg-error-container text-on-error-container',
};
const exitChip = (ex) => ex == null
  ? '<span class="font-mono-sm text-mono-sm text-on-surface-variant animate-pulse">RUNNING…</span>'
  : `<span class="${EXIT_CHIP[ex.kind]} font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm">${esc(ex.text)}</span>`;

// One log line, coloured by what it says. Lives here because four screens stream
// runs and only page-runs.js used to colour them — so a `[REFUSED]` on the diff
// review screen, the screen where a refusal matters most, rendered in the same grey
// as everything else.
function runLine(el, text) {
  const cls = /^\[(ERROR|BLOCKER|REFUSE|STOPPED)/.test(text) ? 'text-error'
    : /^\[warn/i.test(text) ? 'text-tertiary'
      : /^\[(ok|OK|READY|resume|chain)/.test(text) ? 'text-green-400'
        : /^\$ /.test(text) ? 'text-primary' : 'text-on-surface';
  const div = document.createElement('div');
  div.className = cls;
  div.textContent = text;
  el.appendChild(div);
  el.scrollTop = el.scrollHeight;
  return div;
}

// Shared provider-status strip — used by Findings and Analytics.
//
// measure.py writes a status string per external source it was asked for, for
// one reason: a provider that returned nothing because it was never asked must
// not read as a provider that returned nothing because the site is clean.
//
// Three tones, because only one of them means "this number is complete":
// green `ok:`, red `failed:`, amber for everything else (skipped, partial,
// timed out, no field data). Amber is not a warning about the site, it is a
// warning about the measurement.
function providerTone(status) {
  if (status.startsWith('ok:')) return 'text-green-400';
  if (status.startsWith('failed:')) return 'text-error';
  return 'text-tertiary';
}

function renderProviders(providers) {
  const el = document.getElementById('providers');
  const names = Object.keys(providers || {}).sort();
  if (!names.length) {
    el.innerHTML = `<span class="font-mono-sm text-mono-sm text-tertiary">`
      + `HTTP-only cycle — no external provider ran. CrUX, Search Console, `
      + `DataForSEO and Bright Data findings are absent because they were never `
      + `asked for, not because the site is clean.</span>`;
    return;
  }
  el.innerHTML = `<span class="font-label-caps text-label-caps text-on-surface-variant shrink-0">PROVIDERS</span>`
    + names.map((n) => `<span class="font-mono-sm text-mono-sm whitespace-nowrap shrink-0">`
        + `<span class="text-on-surface">${esc(n)}</span> `
        + `<span class="${providerTone(String(providers[n]))}">${esc(String(providers[n]))}</span>`
      + `</span>`).join('');
}

// The one EventSource call site. There were four (runs, git, fleet, review), all
// the same nine lines. Resolves with the exit object so a caller can sequence runs
// — the review screen stops at the first red gate.
function streamRun(runId, logEl, { exitEl = null, onExit = null } = {}) {
  return new Promise((resolve) => {
    const es = new EventSource(`/api/runs/${runId}/stream`);
    if (exitEl) exitEl.innerHTML = exitChip(null);
    es.addEventListener('line', (e) => runLine(logEl, JSON.parse(e.data).line));
    es.addEventListener('exit', (e) => {
      const ex = JSON.parse(e.data);
      if (exitEl) exitEl.innerHTML = exitChip(ex);
      else logEl.insertAdjacentHTML('beforeend', `<div class="mt-sm">${exitChip(ex)}</div>`);
      es.close();
      if (onExit) onExit(ex);
      resolve(ex);
    });
  });
}

// The cycle branch name. Takes the cycle being worked on, because naming the branch
// after the artifacts it carries is the point; falls back to the current month for
// the Git screen, which has no cycle selected.
function cycleBranchName(slug, cycle) {
  if (cycle) return `cycle/${slug}-${cycle}`;
  const d = new Date();
  return `cycle/${slug}-${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
}

function emptyState(title, detail) {
  return `<div class="flex flex-col items-center justify-center py-xl gap-sm text-center">
    <div class="font-headline-sm text-headline-sm text-on-surface-variant">${esc(title)}</div>
    <div class="font-body-sm text-body-sm text-on-surface-variant/70 max-w-md">${esc(detail)}</div>
  </div>`;
}

function fail(el, err) {
  el.innerHTML = `<div class="m-md p-md border border-error/50 bg-error-container/20 rounded">
    <div class="font-label-caps text-label-caps text-error mb-xs">ERROR</div>
    <div class="font-mono-base text-mono-base text-on-surface">${esc(err.message || err)}</div></div>`;
}

// Worklist, Report and Changelog are the same screen over a different artifact:
// pick a cycle, render it. The selection is written back into the URL because
// the sidebar builds every link from location.search — without this, choosing
// 2026-07 here and clicking Changelog silently lands you on the newest cycle.
async function cycleScreen(slug, sel, bodyEl, show, emptyCopy) {
  try {
    const cycles = await api(`/api/clients/${encodeURIComponent(slug)}/cycles`);
    if (!cycles.length) {
      sel.disabled = true;
      bodyEl.innerHTML = emptyState('No cycles yet', emptyCopy);
      return;
    }
    sel.innerHTML = cycles.map((c) => `<option>${esc(c)}</option>`).join('');
    sel.value = currentCycle() || cycles[0];
    sel.addEventListener('change', () => { setCycle(sel.value); show(sel.value); });
    show(sel.value);
  } catch (err) { fail(bodyEl, err); }
}

// Requires a client in the URL; sends you back to the fleet if there is none.
function requireClient() {
  const slug = currentSlug();
  if (!slug) { location.href = '/fleet'; throw new Error('no client'); }
  return slug;
}

renderShell();
