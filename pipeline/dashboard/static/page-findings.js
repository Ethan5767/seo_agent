// Findings — the densest screen. findings.json rendered as a filterable table.
const slug = requireClient();
const tableEl = document.getElementById('table');
const drawerEl = document.getElementById('drawer');
let doc = null, findings = [], group = 'code', selected = null;
// Which group headers are expanded. Collapsed by default: one code can carry a
// thousand rows (leeserie.com opens with 1158 img_alt_missing), and a screen
// that scrolls for a minute before reaching the second code hides the shape of
// the site. Survives re-renders, so filtering does not close what you opened.
const open = new Set();

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
    renderProviders(doc.providers);
    fillSelect(document.getElementById('f-code'), uniq(findings.map((f) => f.code)), '', 'Code…');
    fillSelect(document.getElementById('f-lane'), uniq(findings.map((f) => f.lane)), '', 'Lane…');
    render();
  } catch (err) { fail(tableEl, err); }
}

// Provider statuses — the one thing on this screen that is NOT a finding.
//
// measure.py writes a status string per external source it was asked for, for
// one reason: a provider that returned nothing because it was never asked must
// not read as a provider that returned nothing because the site is clean. The
// table below cannot carry that — zero rows looks the same either way — so the
// strip states it in words above the count.
//
// Three states, because only one of them means "this number is complete":
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
    // The empty case is the one that misleads, so it is the loudest. An
    // HTTP-only cycle is a real measurement, just not of anything a provider
    // sees — and nothing else on this screen would say so.
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

const uniq = (xs) => [...new Set(xs.filter(Boolean))].sort();

function fillSelect(el, values, current, placeholder) {
  el.innerHTML = (placeholder ? `<option value="">${placeholder}</option>` : '') +
    values.map((v) => `<option ${v === current ? 'selected' : ''}>${esc(v)}</option>`).join('');
  // A lane filter with no lanes to filter is noise: lanes are stamped on by
  // wf-site-plan, so a measured-but-unplanned cycle has none.
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

// The header row IS the dropdown control: click to expand its findings. The
// preview is the first finding in the bucket, so a collapsed group still says
// what it is about instead of only how big it is.
function groupHeader(label, fs) {
  const cols = findings.some((f) => f.lane) ? 5 : 4;
  const on = open.has(label);
  const f = fs[0];
  const preview = [f.location, f.detail, f.context].filter(Boolean).join('  ');
  return `<tr data-grp="${esc(label)}" class="bg-surface-container-high hover:bg-surface-container-highest cursor-pointer">
    <td colspan="${cols}" class="px-md py-xs border-y border-outline-variant">
    <div class="flex items-center gap-sm">
      <span class="material-symbols-outlined text-on-surface-variant shrink-0" style="font-size:16px">${on ? 'expand_more' : 'chevron_right'}</span>
      <span class="font-mono-base text-mono-base text-primary shrink-0">${esc(label)}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant/70 truncate">${on ? '' : esc(preview)}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant ml-auto shrink-0">${fs.length}</span>
    </div></td></tr>`;
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
    // Filtering down to one group means you already chose it — collapsing it
    // would make the filter look like it returned a single empty row.
    const keys = Object.keys(buckets);
    if (keys.length === 1) open.add(keys[0]);
    tableEl.innerHTML = table(Object.entries(buckets)
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0]))
      .map(([k, fs]) => groupHeader(k, fs) + (open.has(k) ? fs.map(row).join('') : '')).join(''));
  }
  tableEl.querySelectorAll('tr[data-grp]').forEach((tr) =>
    tr.addEventListener('click', () => {
      const k = tr.dataset.grp;
      open.has(k) ? open.delete(k) : open.add(k);
      render();
    }));
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
document.getElementById('f-cycle').addEventListener('change', (e) => {
  setCycle(e.target.value); load(e.target.value);
});
load();
