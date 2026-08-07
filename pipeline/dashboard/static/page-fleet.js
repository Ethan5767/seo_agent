// Fleet — one card per discovered client.
const grid = document.getElementById('grid');
const empty = document.getElementById('empty');
let clients = [];

// Sharp edge #1. No docs/gate-baseline.json means the gates run BARE on this
// client's first PR: every piece of inherited debt reads as blocking. The CI
// workflow only warns, so the fleet card is where an operator can still see it.
function baselineChip(b) {
  if (!b || b.present === false) {
    return `<span class="bg-tertiary-container text-on-tertiary-container font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm"
      title="No docs/gate-baseline.json — the gates run bare. Record one before this client's first PR.">NO BASELINE</span>`;
  }
  if (b.entries == null) {
    return `<span class="bg-error-container text-on-error-container font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm"
      title="docs/gate-baseline.json exists but will not parse. Present and unreadable is not the same as fine.">BASELINE BAD</span>`;
  }
  return `<span class="border border-outline text-on-surface-variant font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm"
    title="Recorded ${esc(b.recorded || 'unknown')} — may only shrink from here">BL ${b.entries}</span>`;
}

function card(c) {
  const link = `/client?client=${encodeURIComponent(c.slug)}`;
  const tier = c.tier ? `T${c.tier}` : '—';
  // A client that failed to load stays visible carrying its error. Dropping it
  // would read as "no problems here", which is the opposite of the truth.
  if (c.error) {
    return `<div class="bg-surface p-md border border-outline-variant rounded-sm">
      <div class="flex justify-between items-start mb-sm">
        <div><h3 class="font-mono-base text-mono-base text-error">${esc(c.slug)}</h3>
        <p class="font-body-sm text-body-sm text-on-surface-variant">${esc(c.path)}</p></div>
        ${gitChip('error')}
      </div>
      <div class="border-t border-outline-variant pt-sm mt-sm font-mono-sm text-mono-sm text-error">${esc(c.error)}</div>
    </div>`;
  }
  const lanes = c.findings_by_lane;
  // findings_by_lane is null until wf-site-plan stamps lanes back onto the
  // findings. Rather than render four zeros that look measured, say so.
  const laneCells = lanes
    ? Object.entries(lanes).map(([k, v]) => `<div>
        <div class="font-label-caps text-label-caps text-on-surface-variant mb-[2px]">${esc(k)}</div>
        <div class="font-mono-base text-mono-base text-on-surface">${v}</div></div>`).join('')
    : `<div><div class="font-label-caps text-label-caps text-on-surface-variant mb-[2px]">LANES</div>
       <div class="font-mono-sm text-mono-sm text-on-surface-variant/60" title="RESOLVED / PERSISTING / NEW / REGRESSION are assigned by wf-site-plan">not planned</div></div>`;
  const total = c.findings_total == null
    ? '<span class="text-on-surface-variant/60" title="No findings.json yet — run site-health">not run</span>'
    : c.findings_total;
  return `<a href="${link}" class="bg-surface p-md border border-outline-variant rounded-sm hover:bg-surface-container transition-colors group block">
    <div class="flex justify-between items-start mb-sm">
      <div>
        <h3 class="font-mono-base text-mono-base text-primary mb-xs group-hover:underline">${esc(c.slug)}</h3>
        <p class="font-body-sm text-body-sm text-on-surface-variant">${esc(c.domain || c.path)}</p>
      </div>
      <div class="flex gap-xs items-start">
        <span class="bg-surface-container-high border border-outline text-on-surface font-label-caps text-label-caps px-xs py-[2px] rounded-sm">${esc(tier)}</span>
        ${baselineChip(c.baseline)}
        ${gitChip(c.git.state)}
      </div>
    </div>
    <div class="flex gap-lg border-t border-outline-variant pt-sm mt-sm">
      <div>
        <div class="font-label-caps text-label-caps text-on-surface-variant mb-[2px]">FINDINGS</div>
        <div class="font-mono-base text-mono-base text-on-surface">${total}</div>
      </div>
      <div class="flex gap-md">${laneCells}</div>
      <div class="ml-auto text-right">
        <div class="font-label-caps text-label-caps text-on-surface-variant mb-[2px]">CYCLE</div>
        <div class="font-mono-base text-mono-base text-on-surface-variant">${esc(c.latest_cycle || '—')}</div>
      </div>
    </div>
    <div class="font-mono-sm text-mono-sm text-on-surface-variant/60 mt-sm">${esc(c.git.branch || 'no branch')}${
      c.git.ahead ? ` · ${c.git.ahead} unpushed` : ''}${c.git.behind ? ` · ${c.git.behind} behind` : ''}</div>
  </a>`;
}

function render() {
  const q = document.getElementById('filter').value.toLowerCase();
  const shown = clients.filter((c) =>
    !q || c.slug.toLowerCase().includes(q) || (c.domain || '').toLowerCase().includes(q));
  grid.innerHTML = shown.map(card).join('');
  document.getElementById('count').textContent =
    `${shown.length}/${clients.length} client${clients.length === 1 ? '' : 's'}`;
  empty.innerHTML = clients.length === 0
    ? emptyState('No clients found',
        'wf-dashboard looks one level under --clients-dir for git repos containing docs/client-config.yml. Clone a client repo there and refresh.')
    : shown.length === 0 ? emptyState('No match', 'No client matches that filter.') : '';
}

async function load() {
  try {
    clients = await api('/api/clients');
    render();
  } catch (err) { fail(grid, err); }
}

// ── onboard ──────────────────────────────────────────────────────────────────
// wf-onboard STOPS on the interview step and exits 1, which is the normal first
// result, not a failure. So the panel and its log stay open on exit: the output
// names the file to edit, and the same button re-runs and resumes.
const panel = document.getElementById('add-panel');
const obLog = document.getElementById('ob-log');
const obExit = document.getElementById('ob-exit');

// ── the tier picker ──────────────────────────────────────────────────────────
// T1 is preselected and the note under each option says what that tier may do,
// because "tier" is the single most consequential field on this form and the
// number alone says nothing. T2 reveals the two fields it cannot work without —
// the server refuses T2 with either missing, and so does bootstrap_config, so the
// form is the third place that says it rather than the only one.
const TIERS = [
  { n: 1, label: 'T1 · COPY', note: 'Reword existing files only. No creates, no deletes. The safe default.' },
  { n: 2, label: 'T2 · CONTENT', note: 'T1, plus create pages under a content location and wire them into a registry. Both are required.' },
  { n: 3, label: 'T3 · FULL', note: 'Anything not on the deny floor. The floor still holds: never .github/**, never this config, never package.json.' },
];
let tier = 1;

function renderTiers() {
  document.getElementById('ob-tiers').innerHTML = TIERS.map((t) => {
    const on = t.n === tier;
    const cls = on
      ? 'bg-primary-container text-on-primary-container border-primary'
      : 'bg-surface-container-highest text-on-surface-variant border-outline-variant hover:text-on-surface';
    return `<button data-tier="${t.n}" class="tier-opt ${cls} border font-label-caps text-label-caps px-md py-sm rounded">${t.label}</button>`;
  }).join('');
  document.getElementById('ob-tier-note').textContent = TIERS.find((t) => t.n === tier).note;
  // T3 needs no content location (it may create anywhere not denied), so the
  // fields appear for T2 only — showing them for T3 would imply they constrain it.
  document.getElementById('ob-content').classList.toggle('hidden', tier !== 2);
  document.querySelectorAll('.tier-opt').forEach((b) => b.addEventListener('click', () => {
    tier = Number(b.dataset.tier);
    renderTiers();
  }));
}

function obLine(text) {
  const cls = /^\[(ERROR|STOPPED|BLOCKER|REFUSE)/.test(text) ? 'text-error'
    : /^\[warn/i.test(text) ? 'text-tertiary'
      : /^\[(ok|READY)/.test(text) ? 'text-green-400'
        : /^\$ /.test(text) ? 'text-primary' : 'text-on-surface';
  const div = document.createElement('div');
  div.className = cls;
  div.textContent = text;
  obLog.appendChild(div);
  obLog.scrollTop = obLog.scrollHeight;
}

async function onboard() {
  const btn = document.getElementById('ob-run');
  const tokenEl = document.getElementById('ob-token');
  btn.disabled = true;
  obLog.innerHTML = '';
  obLog.classList.remove('hidden');
  obExit.innerHTML = exitChip(null);
  // Read and clear BEFORE the await. Clearing on the success path only left the
  // token sitting in a live DOM node on every 400 — which is the likely path,
  // not the exotic one: mistype the repo and the server refuses.
  const token = tokenEl.value;
  tokenEl.value = '';
  try {
    const { run_id } = await post('/api/onboard', {
      repo: document.getElementById('ob-repo').value,
      domain: document.getElementById('ob-domain').value,
      tier,
      content_location: document.getElementById('ob-location').value.trim(),
      content_registry: document.getElementById('ob-registry').value
        .split(/[\s,]+/).filter(Boolean),
      token,
    });
    const stream = new EventSource(`/api/runs/${run_id}/stream`);
    stream.addEventListener('line', (e) => obLine(JSON.parse(e.data).line));
    stream.addEventListener('exit', (e) => {
      obExit.innerHTML = exitChip(JSON.parse(e.data));
      stream.close();
      btn.disabled = false;
      load();                          // exit 1 still leaves a checkout to show
    });
  } catch (err) {
    obExit.innerHTML = '';
    obLine(`[ERROR] ${err.message || err}`);
    btn.disabled = false;
  }
}

document.getElementById('add').addEventListener('click', () => {
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) document.getElementById('ob-repo').focus();
});
document.getElementById('ob-run').addEventListener('click', onboard);
document.getElementById('filter').addEventListener('input', render);
document.getElementById('refresh').addEventListener('click', load);
renderTiers();
load();
