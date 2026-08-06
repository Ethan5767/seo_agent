// Changelog — what the agent actually did. The only view of wf-site-remediate's
// output, and the one screen where "attempted" and "fixed" must never blur:
// a run that attempted ten items and fixed none is not a quiet success.
const slug = requireClient();
const bodyEl = document.getElementById('body');
document.getElementById('phase').textContent = 'produced by wf-site-remediate';

// A refusal is not a completion. Same rule as the exit chips: the status a run
// reports has to survive being rendered.
const STATUS = {
  fixed: 'border border-green-500/50 text-green-400',
  no_change: 'border border-outline text-on-surface-variant',
  error: 'bg-error-container text-on-error-container',
  refused: 'bg-error-container text-on-error-container',
};

async function load() {
  try {
    const cycles = await api(`/api/clients/${encodeURIComponent(slug)}/cycles`);
    const sel = document.getElementById('cycle');
    if (!cycles.length) {
      sel.disabled = true;
      return void (bodyEl.innerHTML = emptyState('No cycles yet',
        'Run site-health, then site-plan, then site-remediate — the changelog is the last of the three.'));
    }
    sel.innerHTML = cycles.map((c) => `<option>${esc(c)}</option>`).join('');
    sel.value = currentCycle() || cycles[0];
    sel.addEventListener('change', () => show(sel.value));
    show(sel.value);
  } catch (err) { fail(bodyEl, err); }
}

async function show(ym) {
  const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${ym}`);
  const doc = bundle.artifacts['changelog.json'];
  if (!doc) {
    bodyEl.innerHTML = emptyState('No agent run for this cycle',
      `Cycle ${ym} has no changelog.json. Nothing was written by the agent — which is not the same as nothing needing to change. Run site-remediate (start with --dry-run).`);
    return;
  }
  if (doc.error) return void fail(bodyEl, new Error(doc.error));
  const items = doc.items || [];
  const tally = {};
  for (const i of items) tally[i.status] = (tally[i.status] || 0) + 1;
  bodyEl.innerHTML = summary(doc, tally) + stopped(doc) +
    (items.length
      ? items.map(item).join('')
      : '<div class="font-body-sm text-body-sm text-on-surface-variant/70">No items were attempted.</div>') +
    files(doc);
}

function summary(doc, tally) {
  const cell = (label, value, tone = 'text-on-surface') => `<div>
    <div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">${esc(label)}</div>
    <div class="font-mono-base text-mono-base ${tone}">${esc(value ?? '—')}</div></div>`;
  const chips = Object.entries(tally).map(([k, n]) =>
    `<span class="${STATUS[k] || STATUS.error} font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm">${esc(k)} ${n}</span>`).join(' ');
  return `<div class="border border-outline-variant rounded bg-surface-container-low p-md mb-md flex items-center gap-lg flex-wrap">
    ${cell('CYCLE', doc.cycle)}
    ${cell('QUEUED', doc.queued)}
    ${cell('ATTEMPTED', doc.attempted)}
    ${cell('FILES CHANGED', Object.keys(doc.files || {}).length)}
    ${cell('MODEL', doc.model)}
    ${cell('COST', doc.cost_usd == null ? null : `$${doc.cost_usd}`, 'text-tertiary')}
    ${cell('TIER', doc.tier ? `T${doc.tier}` : 'NOT DECLARED')}
    <div class="ml-auto flex gap-xs flex-wrap">${chips}</div>
  </div>
  ${doc.queued > doc.attempted ? `<div class="font-body-sm text-body-sm text-on-surface-variant/70 mb-md">
    ${doc.queued - doc.attempted} queued item(s) were not attempted. They stay in the worklist — re-running is safe.</div>` : ''}`;
}

function stopped(doc) {
  if (!doc.stopped) return '';
  return `<div class="border border-error/50 bg-error-container/20 rounded p-md mb-md">
    <div class="font-label-caps text-label-caps text-error mb-xs">RUN STOPPED</div>
    <div class="font-body-md text-body-md text-on-surface">${esc(doc.stopped)}</div>
    <div class="font-body-sm text-body-sm text-on-surface-variant/70 mt-xs">
      What landed before the stop is still on disk. Read the diff on the Git screen before pushing.</div></div>`;
}

function item(i) {
  return `<div class="border border-outline-variant rounded p-md mb-sm bg-surface-container-low">
    <div class="flex items-center gap-md mb-xs flex-wrap">
      <span class="font-mono-base text-mono-base text-primary">${esc(i.id)}</span>
      <span class="${STATUS[i.status] || STATUS.error} font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm uppercase">${esc(i.status)}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">${esc(i.code)} · ${esc(i.kind)}</span>
      ${i.lane ? `<span class="font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm bg-surface-container-high">${esc(i.lane)}</span>` : ''}
      <span class="ml-auto font-mono-sm text-mono-sm text-on-surface-variant">${esc(i.url)}</span>
    </div>
    ${(i.files || []).length ? `<div class="font-mono-sm text-mono-sm text-on-surface mb-xs">${
      i.files.map((f) => esc(f)).join('<br/>')}</div>` : ''}
    ${i.note ? `<div class="font-body-sm text-body-sm text-tertiary mb-xs">${esc(i.note)}</div>` : ''}
    <div class="font-mono-sm text-mono-sm text-on-surface-variant/70">
      acceptance: ${esc(JSON.stringify(i.acceptance))}</div>
  </div>`;
}

// file -> item ids. The mapping the agent claimed; acceptance_check on the PR is
// what proves it, not this screen.
function files(doc) {
  const entries = Object.entries(doc.files || {});
  if (!entries.length) return '';
  return `<section class="border border-outline-variant rounded bg-surface-container-low mt-lg">
    <div class="px-md py-sm border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant">
      FILES TOUCHED — ${entries.length}</div>
    <div class="p-md font-mono-base text-mono-base">${entries.map(([f, ids]) =>
      `<div class="flex gap-md border-b border-outline-variant/40 py-xs">
        <span class="text-on-surface">${esc(f)}</span>
        <span class="ml-auto text-on-surface-variant">${esc(ids.join(', '))}</span></div>`).join('')}</div>
  </section>`;
}

load();
