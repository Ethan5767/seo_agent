// Worklist — phase 3. Renders worklist.json the moment plan.py starts writing it;
// until then it says which phase ships it rather than showing a blank table.
const slug = requireClient();
const bodyEl = document.getElementById('body');
document.getElementById('phase').textContent = 'produced by wf-site-plan · phase 3';

async function load() {
  try {
    const cycles = await api(`/api/clients/${encodeURIComponent(slug)}/cycles`);
    const sel = document.getElementById('cycle');
    if (!cycles.length) {
      sel.disabled = true;
      return void (bodyEl.innerHTML = emptyState('No cycles yet',
        'Run site-health first — the worklist is derived from a cycle\'s findings.'));
    }
    sel.innerHTML = cycles.map((c) => `<option>${esc(c)}</option>`).join('');
    sel.value = currentCycle() || cycles[0];
    sel.addEventListener('change', () => show(sel.value));
    show(sel.value);
  } catch (err) { fail(bodyEl, err); }
}

async function show(ym) {
  const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${ym}`);
  const doc = bundle.artifacts['worklist.json'];
  if (!doc) {
    bodyEl.innerHTML = emptyState('Worklist not built yet',
      'wf-site-plan (phase 3) turns findings into typed work items with machine-checkable acceptance criteria. Until it ships, the Findings screen is the full picture.');
    return;
  }
  const items = doc.items || [];
  // The tier split is the point: a finding the tier cannot act on stays visible
  // and counted, never silently dropped.
  const [actionable, blocked] = [items.filter((i) => !i.tier_blocked), items.filter((i) => i.tier_blocked)];
  bodyEl.innerHTML = section('ACTIONABLE AT THIS TIER', actionable) +
    (blocked.length ? section('NOT ACTIONABLE AT THIS TIER', blocked,
      'Visible and counted. These are the findings that say the client should move up a tier.') : '');
}

function section(title, items, note) {
  return `<div class="mb-lg">
    <div class="flex items-center gap-md mb-sm">
      <span class="font-label-caps text-label-caps text-on-surface-variant">${esc(title)}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface">${items.length}</span>
    </div>
    ${note ? `<div class="font-body-sm text-body-sm text-on-surface-variant/70 mb-sm">${esc(note)}</div>` : ''}
    ${items.map(item).join('') || '<div class="font-body-sm text-body-sm text-on-surface-variant/50">None.</div>'}</div>`;
}

function item(i) {
  return `<div class="border border-outline-variant rounded p-md mb-sm bg-surface-container-low">
    <div class="flex items-center gap-md mb-xs flex-wrap">
      <span class="font-mono-base text-mono-base text-primary">${esc(i.id)}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">${esc(i.kind)}</span>
      ${i.lane ? `<span class="font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm bg-surface-container-high">${esc(i.lane)}</span>` : ''}
      <span class="ml-auto font-mono-sm text-mono-sm text-on-surface-variant">${esc(i.url)}</span>
    </div>
    <div class="font-mono-sm text-mono-sm text-on-surface-variant/70">
      acceptance: ${esc(JSON.stringify(i.acceptance))}</div>
  </div>`;
}

load();
