// Run console — pick a command from the server's allow-list, stream its output.
const slug = requireClient();
const logEl = document.getElementById('log');
const cmdEl = document.getElementById('command');
const argsEl = document.getElementById('args');
let commands = {}, stream = null;

async function init() {
  try {
    commands = await api('/api/commands');
    cmdEl.innerHTML = Object.entries(commands)
      .map(([k, v]) => `<option value="${esc(k)}">${esc(k)} — ${esc(v.label)}</option>`).join('');
    renderArgs();
    history();
  } catch (err) { fail(logEl, err); }
}

// Inputs come from the command's declared argument types. The server validates
// them again on arrival — this is convenience, the allow-list is the boundary.
function renderArgs() {
  const spec = commands[cmdEl.value];
  argsEl.innerHTML = Object.entries(spec.args).map(([name, kind]) => {
    const label = `<label class="font-label-caps text-label-caps text-on-surface-variant block mb-xs">--${esc(name)}</label>`;
    const cls = 'w-full bg-surface-container-highest border border-outline-variant text-on-surface font-mono-base text-mono-base rounded px-sm py-xs mb-md focus:outline-none focus:border-primary';
    if (kind === 'int') return `${label}<input class="${cls} arg" data-arg="${esc(name)}" data-kind="int" type="number" min="1" placeholder="all"/>`;
    return `${label}<input class="${cls} arg" data-arg="${esc(name)}" data-kind="path-list" placeholder="/one/ /two/ — blank uses the sitemap"/>`;
  }).join('') || '<div class="font-body-sm text-body-sm text-on-surface-variant/70 mb-md">No arguments.</div>';
  argsEl.querySelectorAll('.arg').forEach((i) => i.addEventListener('input', preview));
  preview();
}

function collect() {
  const args = {};
  argsEl.querySelectorAll('.arg').forEach((i) => {
    const v = i.value.trim();
    if (!v) return;
    args[i.dataset.arg] = i.dataset.kind === 'int' ? parseInt(v, 10) : v.split(/\s+/);
  });
  return args;
}

// Show the exact argv before it runs. Nothing is joined into a shell string,
// and the operator can see that.
function preview() {
  const args = collect();
  const flags = Object.entries(args).flatMap(([k, v]) =>
    Array.isArray(v) ? v.flatMap((x) => [`--${k}`, x]) : [`--${k}`, v]);
  document.getElementById('argv').textContent =
    ['wf-' + cmdEl.value.replace(/^wf-/, ''), '--project', `<${slug}>`, ...flags].join(' ');
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
