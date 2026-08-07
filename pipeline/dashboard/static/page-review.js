// Review Diff — GATE 2. The human reads what the agent wrote and approves it.
//
// APPROVING IS `git add`. There is no approvals file and no server-side state:
// staged means approved, unstaged means pending. The index is inspectable with
// `git status`, survives a refresh and a server restart, and cannot drift out of
// sync with the tree the way a parallel record would.
//
// Items that touched the same file are ONE unit, because their diffs are not
// separable — you cannot approve one and reject the other when both edited
// lib/page-meta.ts. The screen says so rather than offering a choice it cannot
// honour.
const slug = requireClient();
const logEl = document.getElementById('log');
let data = null, cycle = null;

const STATE_CHIP = {
  pending: 'bg-tertiary-container text-on-tertiary-container',
  approved: 'border border-green-500/50 text-green-400',
  partial: 'bg-primary-container text-on-primary-container',
  gone: 'border border-outline text-on-surface-variant',
};
const STATE_TITLE = {
  pending: 'Not yet approved — nothing about it is staged',
  approved: 'Approved: every file in this unit is staged',
  partial: 'Partly staged — an unstaged change is still sitting on top of a staged one',
  gone: 'Nothing in the working tree for these paths: already committed, or reverted',
};

// app.js::cycleScreen is the shared "pick a cycle, render it" wiring three other
// screens already use — including writing the choice back into the URL so the
// sidebar links follow it.
const load = () => cycleScreen(slug, document.getElementById('cycle'),
  document.getElementById('units'), show,
  'Nothing has been measured for this client. Run site-health from the Runs screen.');

async function show(ym) {
  cycle = ym;
  try {
    data = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${ym}/review`);
  } catch (err) { return void fail(document.getElementById('units'), err); }
  render();
}

function render() {
  const el = document.getElementById('units');
  const p = data.progress || {};
  document.getElementById('counts').textContent =
    `${p.fixed ?? 0} claimed fixed · ${p.remaining ?? 0} still to do` +
    (p.cost_usd != null ? ` · $${p.cost_usd}` : '');

  if (data.missing_changelog) {
    document.getElementById('bulk').innerHTML = '';
    document.getElementById('finish').innerHTML = '';
    el.innerHTML = emptyState('No remediation run for this cycle',
      `Cycle ${cycle} has no changelog.json, so no agent has written anything to review. Run site-remediate first.`);
    return;
  }
  if (!data.units.length) {
    document.getElementById('bulk').innerHTML = '';
    el.innerHTML = emptyState('Nothing to review',
      'The changelog records no changed files. Every item was no_change or errored — read the Changelog screen, because a run that fixed nothing is not a clean site.');
    renderFinish();
    return;
  }

  const pending = data.units.filter((u) => u.state === 'pending' || u.state === 'partial');
  document.getElementById('bulk').innerHTML = pending.length
    ? `<div class="border border-outline-variant rounded bg-surface-container-low p-md flex items-center gap-md flex-wrap">
        <div class="flex-1 min-w-[14rem]">
          <div class="font-headline-sm text-headline-sm text-on-surface">${pending.length} unit(s) awaiting your approval</div>
          <div class="font-body-sm text-body-sm text-on-surface-variant">Approving stages the files. Nothing is committed until you say so, and
            <code class="font-mono-sm">tier_check</code> still judges the whole diff on the PR.</div>
        </div>
        <button id="all" class="bg-primary text-on-primary font-label-caps text-label-caps px-md py-sm rounded hover:opacity-90 flex items-center gap-xs">
          <span class="material-symbols-outlined" style="font-size:16px">done_all</span> APPROVE ALL</button>
      </div>`
    : `<div class="border border-green-500/40 rounded bg-surface-container-low p-md font-body-md text-body-md text-green-400">
        Every unit approved. Finish up below.</div>`;

  el.innerHTML = data.units.map(unit).join('');
  wire();
  renderFinish();
}

function unit(u, i) {
  const shared = u.files.length > 1 && u.items.length > 1;
  const body = (u.diff || u.staged_diff || '').trim();
  return `<section class="border border-outline-variant rounded bg-surface-container-low" data-unit="${i}">
    <div class="px-md py-sm border-b border-outline-variant flex items-center gap-md flex-wrap">
      <span class="${STATE_CHIP[u.state]} font-mono-sm text-mono-sm px-xs py-[2px] rounded-sm uppercase"
            title="${esc(STATE_TITLE[u.state])}">${esc(u.state)}</span>
      <span class="font-mono-base text-mono-base text-primary">${u.items.map(esc).join(', ') || '(no item recorded)'}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">${u.files.map(esc).join('  ')}</span>
      <div class="ml-auto flex gap-sm">
        <button data-act="approve" data-unit="${i}" ${u.state === 'approved' || u.state === 'gone' ? 'disabled' : ''}
          class="act bg-surface-container-highest border border-outline-variant text-on-surface font-label-caps text-label-caps px-md py-xs rounded hover:bg-surface-bright disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-xs">
          <span class="material-symbols-outlined" style="font-size:14px">check</span> APPROVE</button>
        <button data-act="reject" data-unit="${i}" ${u.state === 'gone' ? 'disabled' : ''}
          title="${u.untracked.length ? 'These files did not exist before this run — rejecting a create means deleting it, which this console will not do silently.' : 'Discards these changes and restores the previous version'}"
          class="act bg-surface-container-highest border border-error/40 text-error font-label-caps text-label-caps px-md py-xs rounded hover:bg-error-container/20 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-xs">
          <span class="material-symbols-outlined" style="font-size:14px">undo</span> REJECT</button>
      </div>
    </div>
    ${shared ? `<div class="px-md py-xs bg-tertiary-container/20 font-body-sm text-body-sm text-tertiary border-b border-outline-variant">
      These ${u.items.length} items share ${u.files.length === 1 ? 'a file' : 'files'}, so their diffs cannot be split — approve or reject them together.</div>` : ''}
    ${u.untracked.length ? `<div class="px-md py-xs font-body-sm text-body-sm text-on-surface-variant border-b border-outline-variant">
      New file(s): ${u.untracked.map(esc).join(', ')}</div>` : ''}
    <div class="overflow-x-auto">${diffHtml(body)}</div>
  </section>`;
}

// Raw unified diff with +/- colouring. No diff library: the operator sees exactly
// what `git diff` said, which is the point of a review screen.
function diffHtml(text) {
  if (!text) {
    return `<div class="p-md font-body-sm text-body-sm text-on-surface-variant/70">
      No diff for these paths. They are already staged and unchanged since, or the working tree no longer has them.</div>`;
  }
  const rows = text.split('\n').map((l) => {
    const cls = l.startsWith('+++') || l.startsWith('---') ? 'text-on-surface-variant/60'
      : l.startsWith('@@') ? 'text-primary'
      : l.startsWith('diff ') || l.startsWith('index ') ? 'text-on-surface-variant/50'
      : l.startsWith('+') ? 'text-green-400 bg-green-500/5'
      : l.startsWith('-') ? 'text-error bg-error/5'
      : 'text-on-surface-variant';
    return `<div class="${cls} whitespace-pre">${esc(l) || '&nbsp;'}</div>`;
  });
  return `<div class="p-md font-mono-sm text-mono-sm leading-[1.45]">${rows.join('')}</div>`;
}

function wire() {
  const all = document.getElementById('all');
  if (all) {
    all.onclick = () => {
      const files = data.units
        .filter((u) => u.state !== 'gone')
        .flatMap((u) => u.files);
      act('approve', files);
    };
  }
  document.querySelectorAll('.act').forEach((b) => {
    b.onclick = () => {
      const u = data.units[Number(b.dataset.unit)];
      if (b.dataset.act === 'reject' &&
          !confirm(`Discard the changes to ${u.files.join(', ')}? This cannot be undone.`)) return;
      act(b.dataset.act, u.files);
    };
  });
}

async function act(action, files) {
  logEl.innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/review`,
      { action, cycle, files });
    await streamRun(run_id, logEl);
    show(cycle);
  } catch (err) { fail(logEl, err); }
}

// ── the finish panel ─────────────────────────────────────────────────────────
// Ordered commit -> check -> push -> PR, and each step only appears once the one
// before it is done. The order is the point: the two gates diff
// origin/<default>...HEAD, so running them before the commit judges an empty diff
// and reports a pass over nothing (B-015). Making the correct order the ONLY order
// the screen offers is stronger than a sentence in the docs saying "commit first".
function renderFinish() {
  const el = document.getElementById('finish');
  const pending = data.units.filter((u) => u.state === 'pending' || u.state === 'partial');
  if (pending.length) {
    el.innerHTML = `<div class="border border-outline-variant/40 rounded p-md font-body-sm text-body-sm text-on-surface-variant/60">
      Approve every unit above, then the commit / push / PR steps appear here.</div>`;
    return;
  }
  const staged = data.units.some((u) => u.state === 'approved');
  const st = data.git || {};
  const steps = [];

  // Keyed on `commits_to_judge` and `pushed`, NOT on `ahead`. A fresh cycle branch
  // has no upstream, so `ahead` is 0 the moment it is created — keying the gate
  // step on `ahead` skipped gating entirely on exactly the branch that needs it and
  // sent the operator straight to a PR. `commits_to_judge` is the quantity the
  // gates actually diff.
  if (data.on_default) {
    steps.push(step('f-branch', 'CREATE CYCLE BRANCH', 'call_split',
      `Push and PR are refused from ${esc(st.branch)}. The scaffold belongs on the default branch; the cycle does not.`, true));
  } else if (staged) {
    steps.push(step('f-commit', 'COMMIT THE APPROVED WORK', 'check',
      'Commits exactly what you approved.', true));
  } else if (data.commits_to_judge > 0 && !st.pushed) {
    steps.push(step('f-check', 'RUN THE GATES', 'gavel',
      'tier_check and claim_provenance, now over a real commit. Before the commit they would judge an empty diff and pass over nothing.', false));
    steps.push(step('f-push', 'PUSH', 'upload',
      st.upstream ? `${st.ahead} commit(s) exist only in this checkout.`
        : 'This branch has never been pushed, so nobody else can see it.', true));
  } else if (st.pushed) {
    steps.push(step('f-pr', 'OPEN A PULL REQUEST?', 'merge_type',
      'Asked, not assumed. Answering no leaves the branch pushed and nothing else happens.', true));
  }

  el.innerHTML = `<div class="border border-primary/40 rounded bg-surface-container-low">
    <div class="px-md py-sm border-b border-outline-variant font-label-caps text-label-caps text-primary">FINISH UP</div>
    <div class="p-md flex flex-col gap-sm">${steps.join('') ||
      `<div class="font-body-md text-body-md text-on-surface-variant">Nothing left here. The PR is open — Gate 3 is a human reading the diff on GitHub, and that is the only path to production.</div>`}
    </div></div>`;
  wireFinish();
}

function step(id, label, icon, detail, primary) {
  const cls = primary ? 'bg-primary text-on-primary hover:opacity-90'
    : 'bg-surface-container-highest border border-outline-variant text-on-surface hover:bg-surface-bright';
  return `<div class="flex items-center gap-md flex-wrap">
    <button id="${id}" class="${cls} font-label-caps text-label-caps px-md py-sm rounded flex items-center gap-xs shrink-0">
      <span class="material-symbols-outlined" style="font-size:16px">${icon}</span> ${label}</button>
    <span class="font-body-sm text-body-sm text-on-surface-variant flex-1 min-w-[12rem]">${detail}</span></div>`;
}

function wireFinish() {
  const on = (id, fn) => { const b = document.getElementById(id); if (b) b.onclick = fn; };
  on('f-branch', () => git('branch', { branch: prompt('Branch name', cycleBranchName(slug, cycle)) }));
  on('f-commit', () => git('commit', {
    message: prompt('Commit message',
      `audit: ${slug} ${cycle} — ${(data.progress || {}).fixed ?? 0} fixed`),
  }));
  on('f-push', () => git('push'));
  on('f-check', runGates);
  on('f-pr', () => {
    if (confirm('Open a pull request for this branch now?')) git('pr');
  });
}

async function git(action, extra) {
  if (extra && Object.values(extra).some((v) => v == null)) return;   // prompt cancelled
  logEl.innerHTML = '';
  try {
    const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/git`, { action, extra });
    await streamRun(run_id, logEl);
    show(cycle);
  } catch (err) { fail(logEl, err); }
}

// Both gates, in sequence, so a red one is visible before the push. The server
// refuses either outright when there is nothing committed to judge.
async function runGates() {
  logEl.innerHTML = '';
  for (const command of ['tier-check', 'claim-provenance']) {
    try {
      const { run_id } = await post(`/api/clients/${encodeURIComponent(slug)}/runs`,
        { command, args: command === 'claim-provenance' ? { cycle } : {} });
      const ex = await streamRun(run_id, logEl);
      if (ex && ex.kind !== 'clean' && ex.kind !== 'findings') break;   // red stops here
    } catch (err) { return void fail(logEl, err); }
  }
  show(cycle);
}

load();
