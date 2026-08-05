// Report — phase 3. report.md rendered; a deliberately small markdown subset,
// because the producer is ours and a full parser is a dependency we do not need.
const slug = requireClient();
const bodyEl = document.getElementById('body');
document.getElementById('phase').textContent = 'produced by wf-site-plan · phase 3';

async function load() {
  try {
    const cycles = await api(`/api/clients/${encodeURIComponent(slug)}/cycles`);
    const sel = document.getElementById('cycle');
    if (!cycles.length) {
      sel.disabled = true;
      return void (bodyEl.innerHTML = emptyState('No cycles yet', 'Run site-health first.'));
    }
    sel.innerHTML = cycles.map((c) => `<option>${esc(c)}</option>`).join('');
    sel.value = currentCycle() || cycles[0];
    sel.addEventListener('change', () => show(sel.value));
    show(sel.value);
  } catch (err) { fail(bodyEl, err); }
}

async function show(ym) {
  const bundle = await api(`/api/clients/${encodeURIComponent(slug)}/cycles/${ym}`);
  const md = bundle.artifacts['report.md'];
  bodyEl.innerHTML = md
    ? `<article class="max-w-4xl">${markdown(md)}</article>`
    : emptyState('Report not built yet',
        'wf-site-plan (phase 3) writes report.md with the four lanes: RESOLVED, PERSISTING, NEW, REGRESSION. Without the ratchet there is nothing for it to say that Findings does not already show.');
}

// Headings, lists, tables, code fences, inline code, bold. Enough for a file we
// generate ourselves; anything more wants a library, and this does not.
function markdown(src) {
  const out = [];
  const lines = String(src).split('\n');
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (l.startsWith('```')) {
      const buf = [];
      for (i++; i < lines.length && !lines[i].startsWith('```'); i++) buf.push(lines[i]);
      i++;
      out.push(`<pre class="bg-surface-container-lowest border border-outline-variant rounded p-md my-md overflow-auto font-mono-base text-mono-base">${esc(buf.join('\n'))}</pre>`);
      continue;
    }
    if (/^\|/.test(l)) {
      const rows = [];
      for (; i < lines.length && /^\|/.test(lines[i]); i++) {
        if (/^\|[\s:|-]+\|$/.test(lines[i])) continue;
        rows.push(lines[i].split('|').slice(1, -1).map((c) => c.trim()));
      }
      const [head, ...rest] = rows;
      out.push(`<table class="w-full my-md border border-outline-variant">
        <thead><tr class="bg-surface-container">${head.map((c) => `<th class="text-left px-sm py-xs font-label-caps text-label-caps text-on-surface-variant border-b border-outline-variant">${inline(c)}</th>`).join('')}</tr></thead>
        <tbody>${rest.map((r) => `<tr class="border-b border-outline-variant/40">${r.map((c) => `<td class="px-sm py-xs font-mono-base text-mono-base">${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`);
      continue;
    }
    const h = l.match(/^(#{1,4})\s+(.*)/);
    if (h) {
      const size = ['text-headline-sm font-headline-sm text-primary', 'text-headline-sm font-headline-sm', 'font-label-caps text-label-caps text-on-surface-variant', 'font-label-caps text-label-caps text-on-surface-variant'][h[1].length - 1];
      out.push(`<h${h[1].length} class="${size} mt-lg mb-sm">${inline(h[2])}</h${h[1].length}>`);
      i++; continue;
    }
    if (/^\s*[-*]\s+/.test(l)) {
      const buf = [];
      for (; i < lines.length && /^\s*[-*]\s+/.test(lines[i]); i++) buf.push(lines[i].replace(/^\s*[-*]\s+/, ''));
      out.push(`<ul class="list-disc pl-lg my-sm">${buf.map((b) => `<li class="mb-xs">${inline(b)}</li>`).join('')}</ul>`);
      continue;
    }
    if (l.trim()) out.push(`<p class="my-sm text-on-surface">${inline(l)}</p>`);
    i++;
  }
  return out.join('');
}

const inline = (s) => esc(s)
  .replace(/`([^`]+)`/g, '<code class="font-mono-base text-mono-base text-primary bg-surface-container px-xs rounded-sm">$1</code>')
  .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-on-surface">$1</strong>');

load();
