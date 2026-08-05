// Config — read-only for now.
//
// The form this screen will become edits the tier block (tier, text_paths,
// content.*), and that block does not exist in any config until phase 2. Writing
// it back also has to survive a 16KB commented starter file, which PyYAML
// round-tripping does not. Both are phase-2 problems; showing the real config
// now is what is honestly buildable.
const slug = requireClient();
const bodyEl = document.getElementById('body');
document.getElementById('cycle').classList.add('hidden');
document.getElementById('phase').textContent = 'editing ships with the tier block · phase 2';

const TIER_KEYS = ['tier', 'text_paths', 'content', 'deny'];

async function load() {
  try {
    const cfg = await api(`/api/clients/${encodeURIComponent(slug)}/config`);
    const tierSet = TIER_KEYS.some((k) => k in cfg);
    bodyEl.innerHTML = `
      ${tierSet ? '' : banner()}
      <section class="border border-outline-variant rounded bg-surface-container-low mb-md">
        <div class="px-md py-sm border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant">TIERING</div>
        <div class="p-md">${TIER_KEYS.map((k) => field(k, cfg[k])).join('')}</div>
      </section>
      <section class="border border-outline-variant rounded bg-surface-container-low">
        <div class="px-md py-sm border-b border-outline-variant font-label-caps text-label-caps text-on-surface-variant">
          docs/client-config.yml — ALL KEYS</div>
        <div class="p-md">${Object.entries(cfg).map(([k, v]) => field(k, v)).join('')}</div>
      </section>`;
  } catch (err) { fail(bodyEl, err); }
}

function banner() {
  return `<div class="border border-tertiary/40 bg-tertiary-container/10 rounded p-md mb-md">
    <div class="font-label-caps text-label-caps text-tertiary mb-xs">NO TIER DECLARED</div>
    <div class="font-body-md text-body-md text-on-surface">
      This client has no <code class="font-mono-base text-mono-base text-primary">tier</code> key. Until phase 2 extends
      bootstrap_config with the tier block, no client has one, and the agent has no declared authority over this repo.</div>
    <div class="font-body-sm text-body-sm text-on-surface-variant/70 mt-xs">
      Note that no <code class="font-mono-base">content.location</code> means T2 is unavailable: no declared content home,
      no content writing.</div></div>`;
}

function field(key, value) {
  const missing = value === undefined;
  const shown = missing ? 'not set'
    : typeof value === 'object' ? JSON.stringify(value, null, 2)
    : String(value);
  const danger = key === 'deny';
  return `<div class="mb-md">
    <div class="font-label-caps text-label-caps ${danger ? 'text-error' : 'text-on-surface-variant'} mb-xs">
      ${esc(key)}${danger ? ' — load-bearing, edit with care' : ''}</div>
    <pre class="font-mono-base text-mono-base ${missing ? 'text-on-surface-variant/40' : 'text-on-surface'} whitespace-pre-wrap break-all bg-surface-container-lowest border border-outline-variant/50 rounded p-sm">${esc(shown)}</pre>
  </div>`;
}

load();
