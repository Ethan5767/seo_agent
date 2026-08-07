// Git / PR — the dashboard's write surface. It stops at the PR.
const slug = requireClient();
const logEl = document.getElementById('log');
let st = null;

const cycleBranch = () => {
  const d = new Date();
  return `cycle/${slug}-${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
};

async function load() {
  try {
    st = await api(`/api/clients/${encodeURIComponent(slug)}/git`);
    renderState(); renderChanged(); renderActions();
  } catch (err) { return void fail(document.getElementById('state'), err); }
  // The PR lookup is a network call. Paint everything else first, then fill it in.
  document.getElementById('pr').innerHTML =
    '<div class="font-body-sm text-body-sm text-on-surface-variant/70">Checking GitHub…</div>';
  try {
    st.pr = (await api(`/api/clients/${encodeURIComponent(slug)}/pr`)).pr;
  } catch { st.pr = null; }
  renderPR();
}

function renderState() {
  const onDefault = st.branch === st.default_branch;
  document.getElementById('state').innerHTML = `
    <div class="border border-outline-variant rounded bg-surface-container-low p-md flex items-center gap-lg flex-wrap">
      <div><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">BRANCH</div>
        <div class="font-mono-base text-mono-base text-primary">${esc(st.branch || '—')}</div></div>
      <div><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">STATE</div>${gitChip(st.state)}</div>
      <div><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">AHEAD / BEHIND</div>
        <div class="font-mono-base text-mono-base ${st.ahead ? 'text-tertiary' : 'text-on-surface'}">${st.ahead} / ${st.behind}</div></div>
      <div><div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">DEFAULT</div>
        <div class="font-mono-base text-mono-base text-on-surface-variant">${esc(st.default_branch || '—')}</div></div>
      ${st.ahead ? `<div class="ml-auto font-body-sm text-body-sm text-tertiary max-w-sm">
        ${st.ahead} commit(s) exist only in this checkout. Until they are pushed, nobody else can see them.</div>` : ''}
      ${onDefault ? `<div class="ml-auto font-body-sm text-body-sm text-on-surface-variant max-w-sm">
        You are on the default branch. Push and PR are refused from here — create a cycle branch first.</div>` : ''}
    </div>`;
}

function renderChanged() {
  const el = document.getElementById('changed');
  el.innerHTML = st.changed.length === 0
    ? '<div class="text-on-surface-variant/70 font-body-sm text-body-sm">Clean — nothing to stage.</div>'
    : st.changed.map((l) => {
        const code = l.slice(0, 2), path = l.slice(3);
        const colour = code.includes('?') ? 'text-tertiary' : code.includes('M') ? 'text-primary' : 'text-on-surface';
        return `<div class="flex gap-sm"><span class="${colour} w-6">${esc(code.trim() || '·')}</span><span class="text-on-surface">${esc(path)}</span></div>`;
      }).join('');
}

function button(id, label, icon, primary, disabled, title) {
  const base = primary
    ? 'bg-primary text-on-primary hover:opacity-90'
    : 'bg-surface-container-highest border border-outline-variant text-on-surface hover:bg-surface-bright';
  return `<button id="${id}" ${disabled ? 'disabled' : ''} title="${esc(title || '')}"
    class="${base} ${disabled ? 'opacity-40 cursor-not-allowed' : ''} font-label-caps text-label-caps px-md py-sm rounded flex items-center gap-xs justify-center">
    <span class="material-symbols-outlined" style="font-size:16px">${icon}</span> ${label}</button>`;
}

function renderActions() {
  const onDefault = st.branch === st.default_branch;
  document.getElementById('actions').innerHTML = [
    button('a-pull', 'PULL --FF-ONLY', 'download', false, false),
    button('a-branch', 'CREATE CYCLE BRANCH', 'call_split', false, !onDefault,
      onDefault ? `Creates ${cycleBranch()}` : 'Already on a non-default branch'),
    button('a-stage', 'STAGE ALL CHANGES', 'add', false, st.changed.length === 0,
      'git add -A — the audit artifacts AND the files the remediator edited'),
    button('a-commit', 'COMMIT', 'check', false, st.changed.length === 0),
    button('a-push', 'PUSH', 'upload', false, onDefault, onDefault ? 'Refused from the default branch' : ''),
    button('a-pr', 'OPEN PR', 'merge_type', true, onDefault, onDefault ? 'Refused from the default branch' : ''),
    // Merge is absent by design, not by omission. Saying so here stops the next
    // person adding it back as a "missing" button.
    `<div class="border-t border-outline-variant pt-sm mt-xs font-body-sm text-body-sm text-on-surface-variant/70">
      No merge button. A human merging on GitHub is the only path to production, and reading the diff is the point.</div>`,
  ].join('');

  wire('a-pull', 'pull');
  wire('a-stage', 'stage-all');
  wire('a-push', 'push');
  wire('a-pr', 'pr');
  document.getElementById('a-branch').addEventListener('click', () =>
    run('branch', { branch: prompt('Branch name', cycleBranch()) }));
  document.getElementById('a-commit').addEventListener('click', () =>
    run('commit', { message: prompt('Commit message', `audit: ${slug} cycle artifacts`) }));
}

const wire = (id, action) => document.getElementById(id).addEventListener('click', () => run(action));

async function run(action, extra) {
  if (extra && Object.values(extra).some((v) => v == null)) return;   // prompt cancelled
  logEl.innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/git`, { action, extra });
    const es = new EventSource(`/api/runs/${run_id}/stream`);
    es.addEventListener('line', (e) => {
      const d = document.createElement('div');
      d.textContent = JSON.parse(e.data).line;
      logEl.appendChild(d); logEl.scrollTop = logEl.scrollHeight;
    });
    es.addEventListener('exit', (e) => {
      const ex = JSON.parse(e.data);
      logEl.insertAdjacentHTML('beforeend', `<div class="mt-sm">${exitChip(ex)}</div>`);
      es.close(); load();
    });
  } catch (err) { fail(logEl, err); }
}

function renderPR() {
  const el = document.getElementById('pr');
  if (!st.pr) {
    el.innerHTML = `<div class="font-body-sm text-body-sm text-on-surface-variant/70">
      No open PR for this branch${st.branch === st.default_branch ? '' : ' — use OPEN PR above'}.</div>`;
    return;
  }
  el.innerHTML = `<div class="flex items-center gap-md flex-wrap">
    <span class="font-mono-base text-mono-base text-primary">#${esc(st.pr.number)}</span>
    <span class="font-body-md text-body-md text-on-surface">${esc(st.pr.title)}</span>
    <span class="font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm bg-surface-container-high">${esc(st.pr.state)}</span>
    <a href="${esc(st.pr.url)}" target="_blank" rel="noopener"
       class="ml-auto bg-surface-container-highest border border-outline-variant text-on-surface font-label-caps text-label-caps px-md py-sm rounded hover:bg-surface-bright flex items-center gap-xs">
      <span class="material-symbols-outlined" style="font-size:16px">open_in_new</span> REVIEW &amp; MERGE ON GITHUB</a>
  </div>`;
}

load();
