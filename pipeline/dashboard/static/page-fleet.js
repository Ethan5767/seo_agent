// Fleet — one card per discovered client.
const grid = document.getElementById('grid');
const empty = document.getElementById('empty');
let clients = [];

function card(c) {
  const link = `/client?client=${encodeURIComponent(c.slug)}`;
  const tier = c.tier ? `T${c.tier}` : '—';
  // A client that failed to load stays visible carrying its error. Dropping it
  // would read as "no problems here", which is the opposite of the truth.
  if (c.error) {
    return `<div class="bg-surface p-md">
      <div class="flex justify-between items-start mb-sm">
        <div><h3 class="font-mono-base text-mono-base text-error">${esc(c.slug)}</h3>
        <p class="font-body-sm text-body-sm text-on-surface-variant">${esc(c.path)}</p></div>
        ${gitChip('error')}
      </div>
      <div class="border-t border-outline-variant pt-sm mt-sm font-mono-sm text-mono-sm text-error">${esc(c.error)}</div>
    </div>`;
  }
  const lanes = c.findings_by_lane;
  // findings_by_lane is null until phase 3 ships the ratchet. Rather than render
  // four zeros that look measured, show the total and say where lanes come from.
  const laneCells = lanes
    ? Object.entries(lanes).map(([k, v]) => `<div>
        <div class="font-label-caps text-label-caps text-on-surface-variant mb-[2px]">${esc(k)}</div>
        <div class="font-mono-base text-mono-base text-on-surface">${v}</div></div>`).join('')
    : `<div><div class="font-label-caps text-label-caps text-on-surface-variant mb-[2px]">LANES</div>
       <div class="font-mono-sm text-mono-sm text-on-surface-variant/60" title="RESOLVED / PERSISTING / NEW / REGRESSION arrive with the ratchet">phase 3</div></div>`;
  const total = c.findings_total == null
    ? '<span class="text-on-surface-variant/60" title="No findings.json yet — run site-health">not run</span>'
    : c.findings_total;
  return `<a href="${link}" class="bg-surface p-md hover:bg-surface-container transition-colors group block">
    <div class="flex justify-between items-start mb-sm">
      <div>
        <h3 class="font-mono-base text-mono-base text-primary mb-xs group-hover:underline">${esc(c.slug)}</h3>
        <p class="font-body-sm text-body-sm text-on-surface-variant">${esc(c.domain || c.path)}</p>
      </div>
      <div class="flex gap-xs items-start">
        <span class="bg-surface-container-high border border-outline text-on-surface font-label-caps text-label-caps px-xs py-[2px] rounded-sm">${esc(tier)}</span>
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

document.getElementById('filter').addEventListener('input', render);
document.getElementById('refresh').addEventListener('click', load);
load();
