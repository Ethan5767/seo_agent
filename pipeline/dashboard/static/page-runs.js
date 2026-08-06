// Run console — pick a command from the server's allow-list, stream its output.
const slug = requireClient();
const logEl = document.getElementById('log');
const cmdEl = document.getElementById('command');
const argsEl = document.getElementById('args');
let commands = {}, stream = null, clientCycles = [];

async function init() {
  try {
    // Independent calls. The cycle widget offers the cycles that exist rather
    // than a free-text box: the server refuses anything that is not YYYY-MM, and
    // a typo costs a round-trip to find out. A failure here throws into fail()
    // below — an empty cycle list must never quietly look like "no cycles".
    [commands, clientCycles] = await Promise.all([
      api('/api/commands'),
      api(`/api/clients/${encodeURIComponent(slug)}/cycles`),
    ]);
    cmdEl.innerHTML = Object.entries(commands)
      .map(([k, v]) => `<option value="${esc(k)}">${esc(k)} — ${esc(v.label)}</option>`).join('');
    renderArgs();
    history();
  } catch (err) { fail(logEl, err); }
}

// One widget per declared argument type. A kind with no branch here used to fall
// through to the path-list input, which sent `["2026-08"]` for a `cycle` and a
// list for a `flag` — every phase 3-5 command failed validation on arrival. A
// missing branch is now a visible refusal, not a broken input.
const CLS = 'w-full bg-surface-container-highest border border-outline-variant text-on-surface font-mono-base text-mono-base rounded px-sm py-xs mb-md focus:outline-none focus:border-primary';

function widget(name, kind) {
  const a = `class="${CLS} arg" data-arg="${esc(name)}" data-kind="${esc(kind)}"`;
  if (kind === 'int') return `<input ${a} type="number" min="1" placeholder="default"/>`;
  if (kind === 'path-list') return `<input ${a} placeholder="/one/ /two/ — blank uses the sitemap"/>`;
  if (kind === 'cycle') {
    return `<select ${a}><option value="">newest</option>${
      clientCycles.map((c) => `<option>${esc(c)}</option>`).join('')}</select>`;
  }
  if (kind === 'flag') {
    return `<label class="flex items-center gap-sm mb-md font-mono-base text-mono-base text-on-surface">
      <input type="checkbox" class="arg accent-primary" data-arg="${esc(name)}" data-kind="flag"/>
      <span>--${esc(name)}</span></label>`;
  }
  return `<div class="mb-md font-mono-sm text-mono-sm text-error">no input for argument type ${esc(kind)}</div>`;
}

function renderArgs() {
  const spec = commands[cmdEl.value];
  argsEl.innerHTML = Object.entries(spec.args).map(([name, kind]) => {
    // The checkbox carries its own label, so the caps label would be a duplicate.
    const label = kind === 'flag' ? ''
      : `<label class="font-label-caps text-label-caps text-on-surface-variant block mb-xs">--${esc(name)}</label>`;
    return label + widget(name, kind);
  }).join('') || '<div class="font-body-sm text-body-sm text-on-surface-variant/70 mb-md">No arguments.</div>';
  argsEl.querySelectorAll('.arg').forEach((i) => {
    i.addEventListener('input', preview);
    i.addEventListener('change', preview);
  });
  preview();
}

function collect() {
  const args = {};
  argsEl.querySelectorAll('.arg').forEach((i) => {
    const kind = i.dataset.kind;
    // A flag is only ever sent as an explicit true; the server refuses false.
    if (kind === 'flag') { if (i.checked) args[i.dataset.arg] = true; return; }
    const v = i.value.trim();
    if (!v) return;
    args[i.dataset.arg] = kind === 'int' ? parseInt(v, 10)
      : kind === 'path-list' ? v.split(/\s+/) : v;
  });
  return args;
}

// Show the exact argv before it runs. Nothing is joined into a shell string,
// and the operator can see that.
function preview() {
  const args = collect();
  const flags = Object.entries(args).flatMap(([k, v]) =>
    Array.isArray(v) ? v.flatMap((x) => [`--${k}`, x])
      : v === true ? [`--${k}`] : [`--${k}`, v]);
  const base = commands[cmdEl.value].argv.map((t) => t === '{project}' ? `<${slug}>` : t);
  document.getElementById('argv').textContent = [...base, ...flags].join(' ');
}

async function execute() {
  const btn = document.getElementById('run');
  btn.disabled = true;
  logEl.innerHTML = '';
  document.getElementById('stream-exit').innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`,
      { command: cmdEl.value, args: collect() });
    attach(run_id, `${cmdEl.value} · ${slug}`);
  } catch (err) {
    fail(logEl, err);
  } finally { btn.disabled = false; }
}

function line(text) {
  const cls = /^\[(ERROR|BLOCKER|REFUSE)/.test(text) ? 'text-error'
    : /^\[WARN/.test(text) ? 'text-tertiary'
    : /^\$ /.test(text) ? 'text-primary'
    : 'text-on-surface';
  const div = document.createElement('div');
  div.className = cls;
  div.textContent = text;
  logEl.appendChild(div);
  logEl.scrollTop = logEl.scrollHeight;
}

function attach(runId, label) {
  document.getElementById('stream-label').textContent = label;
  if (stream) stream.close();
  stream = new EventSource(`/api/runs/${runId}/stream`);
  stream.addEventListener('line', (e) => line(JSON.parse(e.data).line));
  stream.addEventListener('exit', (e) => {
    const ex = JSON.parse(e.data);
    document.getElementById('stream-exit').innerHTML = exitChip(ex);
    stream.close(); stream = null; history();
  });
  document.getElementById('stream-exit').innerHTML = exitChip(null);
}

async function history() {
  const runs = await api('/api/runs');
  document.getElementById('history').innerHTML = runs.length === 0
    ? '<div class="px-md py-sm font-body-sm text-body-sm text-on-surface-variant/70">Nothing run in this session. History is per-process; the durable record is the artifact a run wrote.</div>'
    : runs.map((r) => `<button data-run="${esc(r.run_id)}" class="hist w-full text-left px-md py-xs hover:bg-surface-container-highest flex items-center gap-md border-b border-outline-variant/40">
        <span class="font-mono-base text-mono-base text-primary w-40 shrink-0">${esc(r.command)}</span>
        <span class="font-mono-sm text-mono-sm text-on-surface-variant w-24 shrink-0">${esc(r.slug)}</span>
        <span class="ml-auto">${exitChip(r.exit)}</span></button>`).join('');
  document.querySelectorAll('.hist').forEach((b) => b.addEventListener('click', async () => {
    const r = await api(`/api/runs/${b.dataset.run}`);
    logEl.innerHTML = '';
    r.output.forEach(line);
    document.getElementById('stream-label').textContent = `${r.command} · ${r.slug}`;
    document.getElementById('stream-exit').innerHTML = exitChip(r.exit);
    if (r.running) attach(r.run_id, `${r.command} · ${r.slug}`);
  }));
}

cmdEl.addEventListener('change', renderArgs);
document.getElementById('run').addEventListener('click', execute);
init();
