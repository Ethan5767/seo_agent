// Client detail — the hub. Which artifacts exist for a cycle, and what to do next.
const slug = requireClient();
let client = null;

// Each artifact names the command that produces it, so an absent file reads as
// "that step has not been run", never as "nothing wrong here".
const ARTIFACTS = [
  { file: 'findings.json', label: 'Findings', by: 'wf-site-health', href: '/findings',
    count: (d) => (d.findings || []).length + ' findings' },
  { file: 'worklist.json', label: 'Worklist', by: 'wf-site-plan', href: '/worklist',
    count: (d) => (d.items || []).length + ' items' },
  { file: 'report.md', label: 'Report', by: 'wf-site-plan', href: '/report',
    count: (d) => String(d).split('\n').length + ' lines' },
  { file: 'changelog.json', label: 'Changelog', by: 'wf-site-remediate', href: '/changelog',
    count: (d) => `${(d.items || []).filter((i) => i.status === 'fixed').length} fixed of ${d.attempted ?? 0} attempted` },
];

// ── the stage rail ───────────────────────────────────────────────────────────
// The whole flow in one line, with the current position lit and the three human
// gates marked as gates. The complaint this answers is that nine nav items showed
// nine artifacts and nothing showed the sequence.
const STAGES = [
  { id: 'INTERVIEW', label: 'Interview', human: true },
  { id: 'MEASURE', label: 'Measure' },
  { id: 'PLAN', label: 'Plan' },
  { id: 'REMEDIATE', label: 'Remediate' },
  { id: 'REVIEW', label: 'Review diff', human: true },
  { id: 'COMMIT', label: 'Commit' },
  { id: 'PR', label: 'Open PR' },
  { id: 'MERGE', label: 'Merge', human: true },
];

function renderStage() {
  const next = client.next || {};
  const at = STAGES.findIndex((s) => s.id === next.stage);
  const pills = STAGES.map((s, i) => {
    const done = at > i, here = at === i;
    const cls = here
      ? 'bg-primary-container text-on-primary-container border-primary'
      : done
        ? 'border-green-500/40 text-green-400/80'
        : 'border-outline-variant text-on-surface-variant/40';
    // A gate is marked as a gate whether or not you are standing on it: the
    // operator should be able to see where they will be stopped next.
    const icon = s.human
      ? '<span class="material-symbols-outlined" style="font-size:12px">person</span>'
      : done ? '<span class="material-symbols-outlined" style="font-size:12px">check</span>' : '';
    return `<span class="${cls} border rounded-sm px-sm py-[3px] font-label-caps text-label-caps flex items-center gap-[3px] shrink-0">
      ${icon}${esc(s.label)}</span>`;
  }).join('<span class="text-on-surface-variant/30 shrink-0">›</span>');

  // The one button. `command` is null for a stage a human clears or a screen owns,
  // and in that case the panel says where to go instead of offering a no-op.
  const action = next.command
    ? `<a href="/runs?client=${encodeURIComponent(slug)}&command=${encodeURIComponent(next.command)}"
          class="bg-primary text-on-primary font-label-caps text-label-caps px-md py-sm rounded hover:opacity-90 flex items-center gap-xs shrink-0">
        <span class="material-symbols-outlined" style="font-size:16px">play_arrow</span> ${esc(next.label || 'RUN')}</a>`
    : next.stage === 'REVIEW'
      ? `<a href="/review?client=${encodeURIComponent(slug)}"
            class="bg-primary text-on-primary font-label-caps text-label-caps px-md py-sm rounded hover:opacity-90 flex items-center gap-xs shrink-0">
          <span class="material-symbols-outlined" style="font-size:16px">difference</span> REVIEW THE DIFF</a>`
      : ['COMMIT', 'PR'].includes(next.stage)
        ? `<a href="/review?client=${encodeURIComponent(slug)}"
              class="bg-primary text-on-primary font-label-caps text-label-caps px-md py-sm rounded hover:opacity-90 flex items-center gap-xs shrink-0">
            <span class="material-symbols-outlined" style="font-size:16px">check</span> FINISH UP</a>`
        : '';

  document.getElementById('stage').innerHTML = `
    <div class="px-md py-sm border-b border-outline-variant flex items-center gap-xs overflow-x-auto">${pills}</div>
    <div class="p-md flex items-start gap-lg flex-wrap">
      <div class="flex-1 min-w-[16rem]">
        <div class="font-headline-sm text-headline-sm ${next.human ? 'text-tertiary' : 'text-primary'} mb-xs">
          ${next.human ? 'YOUR TURN — ' : ''}${esc(next.label || '—')}</div>
        <div class="font-body-md text-body-md text-on-surface-variant">${esc(next.detail || '')}</div>
        ${next.blocked_by ? `<div class="font-body-sm text-body-sm text-error mt-xs">${esc(next.blocked_by)}</div>` : ''}
      </div>
      ${action}
    </div>`;
}

// ── score + graph ────────────────────────────────────────────────────────────
async function renderScore() {
  const el = document.getElementById('chart');
  const tiles = document.getElementById('tiles');
  const s = client.score || {};
  const p = client.progress || {};
  document.getElementById('score-cycle').textContent =
    client.latest_cycle ? `measured ${client.latest_cycle}` : '';
  tiles.innerHTML = [
    scoreTile('SEO', s.seo, 'Titles, metas, headings, canonicals, alt text, NAP.'),
    scoreTile('AEO', s.aeo, 'Schema and content depth — four checks, so it moves in big steps.'),
    // Not a score: a count. The operator asked for both and they answer different
    // questions — "how good is the site" and "how much work is left".
    `<div class="border border-outline-variant rounded p-md">
      <div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">FINDINGS LEFT</div>
      <div class="flex items-baseline gap-sm">
        <span class="${p.remaining ? 'text-tertiary' : 'text-green-400'}" style="font-size:32px;line-height:1;font-weight:600">${p.remaining ?? '—'}</span>
        <span class="font-mono-sm text-mono-sm text-on-surface-variant">of ${p.actionable ?? 0} actionable · ${p.fixed ?? 0} fixed</span>
      </div>
      <div class="font-body-sm text-body-sm text-on-surface-variant/60 mt-xs">
        ${p.tier_blocked ? `${p.tier_blocked} above this tier. ` : ''}${p.attempted_not_fixed ? `${p.attempted_not_fixed} attempted and not fixed. ` : ''}${p.cost_usd != null ? `$${p.cost_usd} spent.` : ''}</div></div>`,
  ].join('');

  try {
    const { series: rows, verified } = await api(`/api/clients/${encodeURIComponent(slug)}/series`);
    scoreChart(el, rows, verified);
  } catch (err) { fail(el, err); }
}

async function load() {
  try {
    client = await api(`/api/clients/${encodeURIComponent(slug)}`);
    renderHeader();
    renderStage();
    renderScore();
    renderConfig();
    const sel = document.getElementById('cycle');
    if (!client.cycles.length) {
      sel.innerHTML = '<option>none</option>'; sel.disabled = true;
      document.getElementById('artifacts').innerHTML = emptyState('No cycles yet',
        'No docs/audit/<YYYY-MM>/ folder in this repo. Run site-health from the Runs screen to produce the first one.');
      return;
    }
    sel.innerHTML = client.cycles.map((c) => `<option>${esc(c)}</option>`).join('');
    sel.value = currentCycle() || client.cycles[0];
    renderCycle(sel.value);
    sel.addEventListener('change', () => { setCycle(sel.value); renderCycle(sel.value); });
  } catch (err) { fail(document.getElementById('header'), err); }
}

function renderHeader() {
  const c = client;
  const cell = (label, value) => `<div>
    <div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">${label}</div>
    <div class="font-mono-base text-mono-base text-on-surface">${esc(value ?? '—')}</div></div>`;
  document.getElementById('header').innerHTML = `
    <div class="border-b border-outline-variant bg-surface-container px-md py-md flex items-center gap-lg flex-wrap">
      <div>
        <div class="font-headline-sm text-headline-sm text-primary">${esc(c.slug)}</div>
        <div class="font-body-sm text-body-sm text-on-surface-variant">${esc(c.domain || c.path)}</div>
      </div>
      ${cell('TIER', c.tier ? `T${c.tier}` : 'NOT DECLARED')}
      ${cell('TOPOLOGY', c.config.topology_class)}
      ${cell('PLATFORM', c.config.deploy_platform)}
      <div><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">GIT</div>${gitChip(c.git.state)}</div>
      <a href="/runs?client=${encodeURIComponent(slug)}" class="ml-auto bg-primary text-on-primary font-label-caps text-label-caps px-md py-sm rounded hover:opacity-90 flex items-center gap-xs">
        <span class="material-symbols-outlined" style="font-size:16px">play_arrow</span> RUN</a>
    </div>`;
}

async function renderCycle(ym) {
  const el = document.getElementById('artifacts');
  const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${ym}`);
  el.innerHTML = ARTIFACTS.map((a) => {
    const doc = bundle.artifacts[a.file];
    const present = doc != null;
    const body = present
      ? `<div class="font-mono-base text-mono-base text-on-surface">${esc(doc.error ? doc.error : a.count(doc))}</div>`
      : `<div class="font-mono-sm text-mono-sm text-on-surface-variant/60">absent — run ${esc(a.by)}</div>`;
    const link = present && a.href ? `?client=${encodeURIComponent(slug)}&cycle=${encodeURIComponent(ym)}` : null;
    const tag = link ? 'a' : 'div';
    const href = link ? `href="${a.href}${link}"` : '';
    return `<${tag} ${href} class="border ${present ? 'border-outline-variant hover:bg-surface-container' : 'border-outline-variant/40'} rounded p-md block ${link ? 'cursor-pointer' : ''}">
      <div class="flex justify-between items-center mb-xs">
        <span class="font-label-caps text-label-caps ${present ? 'text-primary' : 'text-on-surface-variant/50'}">${esc(a.label)}</span>
        <span class="material-symbols-outlined ${present ? 'text-primary' : 'text-on-surface-variant/30'}" style="font-size:16px">${present ? 'check_circle' : 'schedule'}</span>
      </div>
      <div class="font-mono-sm text-mono-sm text-on-surface-variant/70 mb-xs">${esc(a.file)}</div>
      ${body}</${tag}>`;
  }).join('');
}

function renderConfig() {
  // Read-only: PyYAML round-tripping would eat the starter file's comments, so
  // the tier block is written by `wf-bootstrap-config --add-tier`, not from here.
  const rows = Object.entries(client.config)
    .filter(([, v]) => typeof v !== 'object' || v === null)
    .map(([k, v]) => `<tr class="border-b border-outline-variant/40">
      <td class="py-xs pr-md font-mono-base text-mono-base text-on-surface-variant">${esc(k)}</td>
      <td class="py-xs font-mono-base text-mono-base text-on-surface">${esc(v)}</td></tr>`).join('');
  document.getElementById('config').innerHTML = `<table class="w-full">${rows}</table>
    <div class="mt-md font-body-sm text-body-sm text-on-surface-variant/70 border-t border-outline-variant pt-sm">
      Read-only. Declare the tier with <code class="font-mono-base">wf-bootstrap-config &lt;dir&gt; &lt;domain&gt; --add-tier</code>.</div>`;
}

load();
