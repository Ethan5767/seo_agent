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

async function load() {
  try {
    client = await api(`/api/clients/${encodeURIComponent(slug)}`);
    renderHeader();
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
