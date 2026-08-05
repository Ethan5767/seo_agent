// Findings — the densest screen. findings.json rendered as a filterable table.
const slug = requireClient();
const tableEl = document.getElementById('table');
const drawerEl = document.getElementById('drawer');
let doc = null, findings = [], group = 'code', selected = null;

const ACTIVE = 'bg-surface-container-highest text-on-surface';
const IDLE = 'text-on-surface-variant hover:text-on-surface';

async function load(cycle) {
  try {
    const cyc = await api(`/api/clients/${encodeURIComponent(slug)}/cycles`);
    if (!cyc.length) return void (tableEl.innerHTML = emptyState(
      'No cycles yet', `No docs/audit/<YYYY-MM>/ folder in ${slug}. Run site-health from the Runs screen to produce one.`));
    const ym = cycle || currentCycle() || cyc[0];
    fillSelect(document.getElementById('f-cycle'), cyc, ym, null);
    const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${ym}`);
    doc = bundle.artifacts['findings.json'];
    if (!doc) return void (tableEl.innerHTML = emptyState(
      'Not measured', `Cycle ${ym} has no findings.json. This is not a clean site — it is a cycle that was never run.`));
    if (doc.error) return void fail(tableEl, new Error(doc.error));
    findings = doc.findings || [];
    fillSelect(document.getElementById('f-code'), uniq(findings.map((f) => f.code)), '', 'Code…');
    fillSelect(document.getElementById('f-lane'), uniq(findings.map((f) => f.lane)), '', 'Lane…');
    render();
  } catch (err) { fail(tableEl, err); }
}

const uniq = (xs) => [...new Set(xs.filter(Boolean))].sort();

function fillSelect(el, values, current, placeholder) {
  el.innerHTML = (placeholder ? `<option value="">${placeholder}</option>` : '') +
    values.map((v) => `<option ${v === current ? 'selected' : ''}>${esc(v)}</option>`).join('');
  // A lane filter with no lanes to filter is noise until phase 3 ships the ratchet.
  if (!placeholder) return;
  el.disabled = values.length === 0;
  el.classList.toggle('opacity-40', values.length === 0);
}

function visible() {
  const code = document.getElementById('f-code').value;
  const lane = document.getElementById('f-lane').value;
  const url = document.getElementById('f-url').value.toLowerCase();
  return findings.filter((f) =>
    (!code || f.code === code) && (!lane || f.lane === lane) &&
    (!url || (f.location || '').toLowerCase().includes(url)));
}

function row(f, i) {
  const on = selected === f.fingerprint;
  return `<tr data-fp="${esc(f.fingerprint)}" class="${on ? 'bg-surface-container-high' : 'hover:bg-surface-container'} cursor-pointer border-b border-outline-variant/40">
    <td class="px-md py-xs font-mono-base text-mono-base text-primary whitespace-nowrap">${esc(f.code)}</td>
    <td class="px-md py-xs font-mono-base text-mono-base text-on-surface">${esc(f.location)}</td>
    <td class="px-md py-xs font-mono-base text-mono-base text-tertiary whitespace-nowrap">${esc(f.detail)}</td>
    <td class="px-md py-xs font-mono-base text-mono-base text-on-surface-variant truncate max-w-xs">${esc(f.context)}</td>
    ${findings.some((x) => x.lane) ? `<td class="px-md py-xs font-mono-sm text-mono-sm">${esc(f.lane || '')}</td>` : ''}
  </tr>`;
}

// One table, one header row. Groups are header rows inside the same tbody so
// the columns stay aligned down the whole page.
function table(rows) {
  const cols = findings.some((f) => f.lane) ? 5 : 4;
  const th = (t) => `<th class="px-md py-sm font-label-caps text-label-caps text-on-surface-variant">${t}</th>`;
  return `<table class="w-full border-collapse" data-cols="${cols}">
    <thead class="sticky top-0 bg-surface-container z-20"><tr class="border-b border-outline-variant text-left">
      ${th('CODE')}${th('LOCATION (URL)')}${th('DETAIL')}${th('CONTEXT')}${cols === 5 ? th('LANE') : ''}
    </tr></thead><tbody>${rows}</tbody></table>`;
}

function groupHeader(label, n) {
  const cols = findings.some((f) => f.lane) ? 5 : 4;
  return `<tr class="bg-surface-container-high"><td colspan="${cols}" class="px-md py-xs border-y border-outline-variant">
    <div class="flex justify-between">
      <span class="font-mono-base text-mono-base text-primary">${esc(label)}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">${n}</span></div></td></tr>`;
}

function render() {
  const shown = visible();
  document.getElementById('counts').textContent =
    `TOTAL ${findings.length} · VISIBLE ${shown.length} · ${doc.urls_checked} URLs checked` +
    (doc.urls_unreachable ? ` · ${doc.urls_unreachable} UNREACHABLE` : '');
  document.querySelectorAll('.grp').forEach((b) =>
    b.className = `grp font-mono-sm text-mono-sm px-sm py-xs ${b.dataset.group === group ? ACTIVE : IDLE}`);

  if (!findings.length) {
    // Clean and not-yet-run look identical in a naive table and mean opposite things.
    tableEl.innerHTML = emptyState('Clean',
      `${doc.urls_checked} URL(s) checked on ${doc.generated}, zero findings. This site was measured and passed.`);
    return;
  }
  if (!shown.length) { tableEl.innerHTML = emptyState('No match', 'No finding matches these filters.'); return; }

  if (group === 'flat') {
    tableEl.innerHTML = table(shown.map(row).join(''));
  } else {
    const key = group === 'code' ? 'code' : 'location';
    const buckets = {};
    for (const f of shown) (buckets[f[key]] ||= []).push(f);
    tableEl.innerHTML = table(Object.entries(buckets)
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
      .map(([k, fs]) => groupHeader(k, fs.length) + fs.map(row).join('')).join(''));
  }
  tableEl.querySelectorAll('tr[data-fp]').forEach((tr) =>
    tr.addEventListener('click', () => { selected = tr.dataset.fp; render(); drawer(); }));
  if (selected) drawer();
}

function drawer() {
  const f = findings.find((x) => x.fingerprint === selected);
  if (!f) { drawerEl.classList.add('hidden'); return; }
  drawerEl.classList.remove('hidden');
  const field = (label, value, mono = true) => value
    ? `<div class="mb-md"><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">${label}</div>
       <div class="${mono ? 'font-mono-base text-mono-base' : 'font-body-md text-body-md'} text-on-surface break-all">${esc(value)}</div></div>`
    : '';
  drawerEl.innerHTML = `
    <div class="flex justify-between items-center px-md py-sm border-b border-outline-variant sticky top-0 bg-surface-container-low">
      <span class="font-label-caps text-label-caps text-on-surface-variant">INSPECTION DETAIL</span>
      <button id="close" class="material-symbols-outlined text-on-surface-variant hover:text-on-surface" style="font-size:18px">close</button>
    </div>
    <div class="p-md">
      ${field('CODE', f.code)}${field('LOCATION', f.location)}${field('DETAIL', f.detail)}
      ${field('CONTEXT', f.context)}${field('LANE', f.lane)}
      <div class="mb-md"><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">ORDINAL</div>
        <div class="font-mono-base text-mono-base text-on-surface">${f.ordinal}</div>
        <div class="font-body-sm text-body-sm text-on-surface-variant/70 mt-xs">Disambiguates repeated identical findings on one page.</div></div>
      ${field('FINGERPRINT', f.fingerprint)}
      <div class="font-body-sm text-body-sm text-on-surface-variant/70 border-t border-outline-variant pt-sm">
        DETAIL is excluded from the fingerprint, so a finding cannot become &ldquo;new&rdquo; by getting worse.</div>
    </div>`;
  document.getElementById('close').addEventListener('click', () => { selected = null; render(); drawerEl.classList.add('hidden'); });
}

document.querySelectorAll('.grp').forEach((b) =>
  b.addEventListener('click', () => { group = b.dataset.group; render(); }));
['f-code', 'f-lane', 'f-url'].forEach((id) =>
  document.getElementById(id).addEventListener('input', render));
document.getElementById('f-cycle').addEventListener('change', (e) => load(e.target.value));
load();
