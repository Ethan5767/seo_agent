// scoreChart — SEO/AEO score per cycle, as inline SVG.
//
// No chart library. Twelve points and two series do not justify a dependency, and
// the dashboard has none: everything here is <svg> the browser already draws.
//
// THREE STATES, VISUALLY DISTINCT, ON PURPOSE
// A solid line is a MEASUREMENT (findings.json, the live site as it was). A dashed
// segment to a hollow marker is a PROJECTION (what this cycle's changelog claims
// its fixes will do). A tick is VERIFICATION (acceptance_check re-measured the
// build output and agreed). Rendering a claim the same way as a measurement is the
// one thing this whole pipeline exists to prevent, so the chart does not do it
// either.
//
// COLOR
// SEO is always cyan and AEO always amber, assigned in fixed order and never
// cycled, so a filter can never repaint a series. These are the theme's own
// primary/tertiary ramps stepped into the dark-mode mark band — the theme's
// #38bdf8/#f1a02b are tuned for text, not marks. Validation figures are in the
// CHANGELOG entry.
const SERIES = [
  { key: 'seo', label: 'SEO', color: '#0284c7', projected: 'projected_seo' },
  { key: 'aeo', label: 'AEO', color: '#b45309', projected: 'projected_aeo' },
];

const PAD = { t: 16, r: 52, b: 28, l: 34 };

// Identity is never carried by color alone: the legend is always present for two
// series, and the last point of each is directly labelled.
function legend(verified) {
  const swatches = SERIES.map((s) => `
    <span class="flex items-center gap-xs">
      <span style="width:10px;height:10px;border-radius:2px;background:${s.color}"></span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">${s.label}</span>
    </span>`).join('');
  const states = `
    <span class="flex items-center gap-xs" title="From findings.json — the live site as measured">
      <svg width="18" height="8"><line x1="0" y1="4" x2="18" y2="4" stroke="currentColor" stroke-width="2"/></svg>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">measured</span></span>
    <span class="flex items-center gap-xs" title="What this cycle's changelog CLAIMS its fixes will do. Not a measurement.">
      <svg width="18" height="8"><line x1="0" y1="4" x2="18" y2="4" stroke="currentColor" stroke-width="2" stroke-dasharray="3 3"/></svg>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">projected</span></span>`;
  return `<div class="flex items-center gap-md flex-wrap px-md py-xs text-on-surface-variant/60">
    ${swatches}<span class="w-px h-4 bg-outline-variant"></span>${states}
    ${verifiedChip(verified)}</div>`;
}

// can_verify false and "not verified yet" mean opposite things about whether the
// claims should be trusted, so they never render the same.
function verifiedChip(v) {
  if (!v) return '';
  if (v.can_verify === true) {
    return `<span class="font-mono-sm text-mono-sm text-green-400 flex items-center gap-xs" title="${esc(v.reason)}">
      <span class="material-symbols-outlined" style="font-size:14px">verified</span> acceptance_check can verify</span>`;
  }
  const label = v.can_verify === false ? 'CANNOT verify' : 'verification unknown';
  return `<span class="font-mono-sm text-mono-sm text-tertiary flex items-center gap-xs" title="${esc(v.reason)}">
    <span class="material-symbols-outlined" style="font-size:14px">help</span> ${label}</span>`;
}

function scoreChart(el, rows, verified) {
  const measured = rows.filter((r) => r.seo != null || r.aeo != null);
  if (measured.length === 0) {
    el.innerHTML = emptyState('No score yet',
      'A score needs a measured cycle. Run site-health — it chains into site-plan.');
    return;
  }

  const W = Math.max(el.clientWidth || 640, 320), H = 168;
  const iw = W - PAD.l - PAD.r, ih = H - PAD.t - PAD.b;
  // A score is a percentage, so the axis is 0-100 and never zoomed to the data.
  // Truncating it is the single most common way a chart overstates a change.
  const y = (v) => PAD.t + ih * (1 - v / 100);
  const x = (i) => rows.length === 1
    ? PAD.l + iw / 2
    : PAD.l + iw * (i / (rows.length - 1));

  const grid = [0, 25, 50, 75, 100].map((v) => `
    <line x1="${PAD.l}" y1="${y(v)}" x2="${PAD.l + iw}" y2="${y(v)}"
          stroke="currentColor" stroke-width="1" opacity="0.12"/>
    <text x="${PAD.l - 6}" y="${y(v) + 3}" text-anchor="end" font-size="9"
          fill="currentColor" opacity="0.5">${v}</text>`).join('');

  const ticks = rows.map((r, i) => `
    <text x="${x(i)}" y="${H - 8}" text-anchor="middle" font-size="9"
          fill="currentColor" opacity="0.5">${esc(r.cycle.slice(2))}</text>`).join('');

  // End-labels are decided for BOTH series together, before either is drawn. Two
  // score lines converge near 100 constantly, and the rule for converging series is
  // not to nudge the labels apart — that detaches them from their lines and reads
  // as noise. When they would collide, no label is drawn and the legend plus the
  // hover tooltip carry the values instead.
  const last = rows.length - 1;
  const endY = SERIES.map((s) => {
    const row = rows[last];
    if (!row || row[s.key] == null) return null;
    const shown = row[s.projected] != null ? row[s.projected] : row[s.key];
    return { y: y(shown), value: shown };
  });
  const labelsFit = endY.every(Boolean)
    ? Math.abs(endY[0].y - endY[1].y) >= 12
    : true;

  const marks = SERIES.map((s) => {
    // A cycle with no score is a GAP, not a zero and not an interpolation: joining
    // across it would draw a trend through a month nobody measured.
    const runs = [];
    let run = null;
    rows.forEach((r, i) => {
      if (r[s.key] == null) { run = null; return; }
      if (run === null) { run = []; runs.push(run); }
      run.push([x(i), y(r[s.key])]);
    });
    const lines = runs.filter((p) => p.length > 1).map((p) =>
      `<polyline points="${p.map(([px, py]) => `${px},${py}`).join(' ')}" fill="none"
                 stroke="${s.color}" stroke-width="2" stroke-linecap="round"/>`).join('');

    const dots = runs.flat().map(([px, py]) =>
      // 2px surface ring: where SEO and AEO cross, the marks must stay countable.
      `<circle cx="${px}" cy="${py}" r="4" fill="${s.color}"
               stroke="var(--chart-surface,#0b1326)" stroke-width="2"/>`).join('');

    // The projection: dashed from the last measured point to a HOLLOW marker. The
    // marker is a mark and always drawn; only the NUMBER is conditional.
    const row = rows[last];
    if (!row || row[s.key] == null) return lines + dots;

    const projects = row[s.projected] != null && row[s.projected] !== row[s.key];
    let out = lines + dots, lx = x(last), ly = y(row[s.key]);
    if (projects) {
      const px = x(last) + Math.min(28, PAD.r - 24);
      out += `<line x1="${x(last)}" y1="${y(row[s.key])}" x2="${px}" y2="${y(row[s.projected])}"
                    stroke="${s.color}" stroke-width="2" stroke-dasharray="3 3" opacity="0.8"/>
              <circle cx="${px}" cy="${y(row[s.projected])}" r="4" fill="none"
                      stroke="${s.color}" stroke-width="2"/>`;
      lx = px;
      ly = y(row[s.projected]);
    }
    if (labelsFit) {
      // `currentColor` is the muted text token the <svg> carries. Text never wears
      // the data color — a light categorical hue is illegible as text on the
      // surface, and identity already comes from the colored mark beside it.
      out += `<text x="${lx + 7}" y="${ly + 3}" font-size="10" fill="currentColor"
                    opacity="0.85">${projects ? row[s.projected] : row[s.key]}</text>`;
    }
    return out;
  }).join('');

  el.innerHTML = `${legend(verified)}
    <svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" class="text-on-surface-variant"
         role="img" aria-label="SEO and AEO score per cycle">
      ${grid}${ticks}${marks}
      <g id="ch-hover"></g>
      <rect x="${PAD.l}" y="${PAD.t}" width="${iw}" height="${ih}" fill="transparent" id="ch-hit"/>
    </svg>
    <div id="ch-tip" class="hidden absolute z-30 pointer-events-none bg-surface-container-highest border border-outline-variant rounded px-sm py-xs font-mono-sm text-mono-sm shadow-lg"></div>`;

  wireHover(el, rows, x, y, ih);
}

// An SVG chart in a browser IS interactive; a crosshair and a tooltip are the
// default, not an enhancement. The hit area is the whole plot rather than the 4px
// dots, so reading a cycle does not require hitting a mark.
function wireHover(el, rows, x, y, ih) {
  const svg = el.querySelector('svg');
  const hover = el.querySelector('#ch-hover');
  const tip = el.querySelector('#ch-tip');
  if (!svg || !hover) return;

  const nearest = (clientX) => {
    const box = svg.getBoundingClientRect();
    const vx = ((clientX - box.left) / box.width) * svg.viewBox.baseVal.width;
    let best = 0, bestD = Infinity;
    rows.forEach((_, i) => {
      const d = Math.abs(x(i) - vx);
      if (d < bestD) { bestD = d; best = i; }
    });
    return best;
  };

  const show = (ev) => {
    const i = nearest(ev.clientX);
    const r = rows[i];
    hover.innerHTML = `<line x1="${x(i)}" y1="${PAD.t}" x2="${x(i)}" y2="${PAD.t + ih}"
      stroke="currentColor" stroke-width="1" opacity="0.35"/>`;
    const line = (s) => {
      if (r[s.key] == null) return `<div class="text-on-surface-variant/60">${s.label} not measured</div>`;
      const p = r[s.projected];
      return `<div class="text-on-surface">${s.label} ${r[s.key]}` +
        (p != null && p !== r[s.key]
          ? `<span class="text-on-surface-variant/70"> → ${p} projected</span>` : '') + '</div>';
    };
    tip.innerHTML = `<div class="text-primary mb-xs">${esc(r.cycle)}</div>${SERIES.map(line).join('')}`;
    tip.classList.remove('hidden');
    const host = el.getBoundingClientRect();
    tip.style.left = `${Math.min(ev.clientX - host.left + 12, host.width - 150)}px`;
    tip.style.top = `${ev.clientY - host.top + 12}px`;
  };

  svg.addEventListener('mousemove', show);
  svg.addEventListener('mouseleave', () => {
    hover.innerHTML = '';
    tip.classList.add('hidden');
  });
}

// A score is one number about a whole site, which is exactly the case for a stat
// tile rather than a chart. `failing/total` rides along because the number alone
// hides how much was measured — AEO rests on four checks, so it moves in big steps.
function scoreTile(label, fam, hint) {
  if (!fam || fam.score == null) {
    return `<div class="border border-outline-variant/40 rounded p-md">
      <div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">${esc(label)}</div>
      <div class="font-mono-base text-mono-base text-on-surface-variant/60">not measured</div>
      <div class="font-body-sm text-body-sm text-on-surface-variant/50 mt-xs">A cycle that was never run is not a clean site.</div></div>`;
  }
  const colour = fam.score >= 90 ? 'text-green-400' : fam.score >= 70 ? 'text-primary' : 'text-tertiary';
  const skipped = (fam.skipped || []).length
    ? `<div class="font-mono-sm text-mono-sm text-on-surface-variant/50 mt-xs"
            title="These checks did not run — their config field is unset — so they are excluded from the denominator rather than counted as passes.">
         not scored: ${fam.skipped.map((c) => esc(c.replace('health.', ''))).join(', ')}</div>`
    : '';
  return `<div class="border border-outline-variant rounded p-md">
    <div class="font-label-caps text-label-caps text-on-surface-variant mb-xs">${esc(label)}</div>
    <div class="flex items-baseline gap-sm">
      <span class="${colour}" style="font-size:32px;line-height:1;font-weight:600">${fam.score}</span>
      <span class="font-mono-sm text-mono-sm text-on-surface-variant">${fam.failing} of ${fam.total} page-checks failing</span>
    </div>
    ${hint ? `<div class="font-body-sm text-body-sm text-on-surface-variant/60 mt-xs">${esc(hint)}</div>` : ''}
    ${skipped}</div>`;
}
