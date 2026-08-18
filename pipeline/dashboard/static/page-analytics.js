// Analytics — trigger the four external measurement providers and curate the
// Bright Data SERP search-term list. Section 1 (providers) below; Section 2
// (search terms) is appended by a later change to this same file, extending
// load() in place rather than adding a second entry point.
const slug = requireClient();

let cfg = null, latestFindings = null;

// One combined fetch: GET /api/clients/:slug already returns config + cycles
// together, so this is one round-trip instead of three. Renders everything it
// loads — Section 2 extends this function's body directly instead of calling
// a second load, so the page never fetches or renders twice.
async function load() {
  try {
    const client = await api(`/api/clients/${encodeURIComponent(slug)}`);
    cfg = client.config;
    latestFindings = null;
    if (client.cycles.length) {
      const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${client.cycles[0]}`);
      latestFindings = bundle.artifacts['findings.json'] || null;
    }
    renderProviders((latestFindings && latestFindings.providers) || {});
    renderTerms();
  } catch (err) {
    fail(document.getElementById('recheck-log'), err);
  }
}

// The one launch/stream/reload path every button on this page uses. Returns
// the run's exit object ({code, kind, text}) on success, or null if the POST
// itself failed (e.g. another run is already busy against this client) — the
// error is already rendered into logEl either way, so callers only need to
// branch on whether to treat the run as having succeeded.
async function run(command, args, logEl) {
  logEl.innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`, { command, args });
    const ex = await streamRun(run_id, logEl);
    await load();
    return ex;
  } catch (err) {
    fail(logEl, err);
    return null;
  }
}

async function recheck() {
  const btn = document.getElementById('recheck');
  btn.disabled = true;
  try {
    await run('site-health',
      { 'with-crux': true, 'with-gsc': true, 'with-dataforseo': true,
        'with-serp': true, 'max-crawl-pages': 20 },
      document.getElementById('recheck-log'));
  } finally { btn.disabled = false; }
}

document.getElementById('recheck').addEventListener('click', recheck);

// ── Section 2: Search Terms ──────────────────────────────────────────────────

// State comes from the SERP provider's status string, not from finding
// presence — parse_serp emits NO finding at all for a query that already
// ranks on page one (rank <= SERP_TOP_PAGE), so "no finding" must render as
// "ranks on page one" once SERP has actually run, and only as "not checked
// yet" when it hasn't. Collapsing those two into one "not checked yet" state
// would hide the client's actual wins.
//
// No GSC column: a SERP finding's `location` is hardcoded to "/" for every
// query (providers.py — "which page ranks is Google's choice"), so there is
// no query-to-page mapping in this pipeline to join GSC data through. Showing
// one anyway would mean showing whatever GSC findings happen to sit on the
// homepage, mislabeled as being about this query.
function termStatus(query) {
  const serpStatus = (latestFindings && latestFindings.providers && latestFindings.providers.serp) || '';
  if (!serpStatus || serpStatus.startsWith('skipped:')) {
    return { text: 'not checked yet', cls: 'text-on-surface-variant/50' };
  }
  const findings = (latestFindings && latestFindings.findings) || [];
  const hit = findings.find((f) => f.code.startsWith('serp.') && f.context === query);
  if (!hit) return { text: 'ranks on page one', cls: 'text-green-400' };
  return { text: `${hit.code} — ${hit.detail || ''}`, cls: 'text-error' };
}

function termRow(query) {
  const s = termStatus(query);
  return `<div class="border-b border-outline-variant/40 py-sm">
    <div class="font-mono-base text-mono-base text-on-surface">${esc(query)}</div>
    <div class="mt-xs font-mono-sm text-mono-sm ${s.cls}">${esc(s.text)}</div>
  </div>`;
}

function renderTerms() {
  const el = document.getElementById('terms');
  const terms = (cfg && cfg.seed_queries) || [];
  el.innerHTML = terms.length
    ? terms.map(termRow).join('')
    : '<div class="font-body-sm text-body-sm text-on-surface-variant/70">No search terms tracked yet. Add one above, or ask the agent to suggest some.</div>';
}

function showCommitBanner() {
  const el = document.getElementById('commit-banner');
  el.textContent = 'seed_queries changed — commit docs/client-config.yml before '
    + 'the next cycle, or this list resets to what is on disk.';
  el.classList.remove('hidden');
}

function searchLog() {
  const el = document.getElementById('search-log');
  el.classList.remove('hidden');
  return el;
}

async function addTerm() {
  const input = document.getElementById('new-term');
  const term = input.value.trim();
  if (!term) return;
  const btn = document.getElementById('add-term');
  btn.disabled = true;
  try {
    const ex = await run('search-add', { write: [term] }, searchLog());
    if (ex && ex.code === 0) {
      input.value = '';
      showCommitBanner();
    }
  } finally { btn.disabled = false; }
}

async function suggest() {
  const btn = document.getElementById('suggest');
  const box = document.getElementById('suggestions');
  btn.disabled = true;
  box.classList.remove('hidden');
  box.innerHTML = '<div class="font-mono-sm text-mono-sm text-on-surface-variant">Asking the agent…</div>';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`,
      { command: 'search-suggest', args: {} });
    const ex = await streamRun(run_id, searchLog());
    if (!ex || ex.code !== 0) {
      box.innerHTML = '<div class="font-mono-sm text-mono-sm text-on-surface-variant/70">No suggestions — see the log above.</div>';
      return;
    }
    const run_data = await api(`/api/runs/${run_id}`);
    const queriesLine = run_data.output.find((l) => l.startsWith('[QUERIES] '));
    const queries = queriesLine ? JSON.parse(queriesLine.slice('[QUERIES] '.length)) : [];
    box.innerHTML = queries.length
      ? queries.map((q) => `<label class="flex items-center gap-sm py-xs">
          <input type="checkbox" class="suggestion accent-primary" value="${esc(q)}" checked/>
          <span class="font-mono-base text-mono-base text-on-surface">${esc(q)}</span></label>`).join('')
        + `<button id="keep-suggestions" class="mt-sm font-mono-sm text-mono-sm px-sm py-xs rounded bg-primary text-on-primary hover:opacity-90">ADD TICKED</button>`
      : '<div class="font-mono-sm text-mono-sm text-on-surface-variant/70">No suggestions came back — see the log above.</div>';
    document.getElementById('keep-suggestions')?.addEventListener('click', async () => {
      const picked = [...document.querySelectorAll('.suggestion:checked')].map((c) => c.value);
      if (!picked.length) return;
      const addEx = await run('search-add', { write: picked }, searchLog());
      if (addEx && addEx.code === 0) {
        showCommitBanner();
        box.classList.add('hidden');
      }
    });
  } catch (err) {
    fail(box, err);
  } finally { btn.disabled = false; }
}

document.getElementById('add-term').addEventListener('click', addTerm);
document.getElementById('suggest').addEventListener('click', suggest);

load();
