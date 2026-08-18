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
load();
