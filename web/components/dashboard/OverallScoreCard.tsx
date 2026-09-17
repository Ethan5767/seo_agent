"use client";

import React from "react";
import { overallScore, type OverallScore, type PillarScore } from "@/lib/overallScore";

/**
 * The Overall SEO Score: four pillars, one number, and never a black box.
 *
 * Three rules it exists to keep, all defects the operator found in the old
 * headline number (2026-09-16):
 *
 *   * The number is always shown with its parts. A composite on its own invites
 *     optimising the number instead of the site.
 *   * Checks are weighted by importance, so a missing title outweighs a missing
 *     apple-touch-icon tenfold instead of matching it.
 *   * A pillar nobody measured is stated as unmeasured. No zero, no quiet drop
 *     from the average.
 *
 * Chart decisions, and why:
 *
 *   * **A gauge, not a donut.** One number is a hero number; the arc is there to
 *     place it on 0-100, not to be read against a second value.
 *   * **A weighted contribution bar, not a radar.** Radar distorts by area and
 *     cannot show weight at all, which is the whole point here: Content at 89
 *     carries 35 points of the score and AEO at 33 carries 10. The bar shows
 *     each pillar's earned points against the points it could contribute.
 *   * **Status is icon + label + colour**, never colour alone, and the segment
 *     hues are direct-labelled — both required, since two of the four sit under
 *     3:1 on the light surface.
 *
 * Palette: the design system's own categorical order (--chart-1..4), already
 * validated in DESIGN.md §14 — worst adjacent CVD ΔE 9.1. A second palette was
 * briefly defined here; two sources for one thing is how they drift.
 */

interface OverallScoreCardProps {
  report: unknown;
  onRunPillar?: (key: PillarScore["key"]) => void;
}

/* Status: reserved colours, each shipped with a word and a glyph. */
type Band = { label: string; glyph: string; color: string; tint: string };
const BANDS: Array<{ min: number } & Band> = [
  { min: 80, label: "Strong", glyph: "●", color: "var(--ok)", tint: "var(--ok-tint)" },
  { min: 50, label: "Needs improvement", glyph: "▲", color: "var(--warn)", tint: "var(--warn-tint)" },
  { min: 0, label: "Critical", glyph: "■", color: "var(--bad)", tint: "var(--bad-tint)" },
];
const UNMEASURED: Band = { label: "Not measured", glyph: "—", color: "var(--ink-muted)", tint: "var(--surface-3)" };

function band(score: number | null): Band {
  if (score === null) return UNMEASURED;
  return BANDS.find((b) => score >= b.min) ?? BANDS[BANDS.length - 1];
}

/** Pillar identity, fixed order, never cycled. */
const PILLAR_HUE: Record<PillarScore["key"], string> = {
  technical: "var(--chart-1)",
  content: "var(--chart-2)",
  backlinks: "var(--chart-3)",
  aeo: "var(--chart-4)",
};

/** Semi-circle gauge. Thin arc, ink number, status carried by the pill beside it. */
function Gauge({ score, tone }: { score: number | null; tone: string }) {
  const R = 84, CIRC = Math.PI * R;
  const filled = score === null ? 0 : (score / 100) * CIRC;
  return (
    <svg viewBox="0 0 200 112" className="ovr__gauge" role="img"
         aria-label={score === null ? "Overall score not yet available" : `Overall score ${score} out of 100`}>
      <path d="M 16 100 A 84 84 0 0 1 184 100" className="ovr__gauge-track" />
      {score !== null && (
        <path d="M 16 100 A 84 84 0 0 1 184 100" className="ovr__gauge-fill"
              style={{ stroke: tone, strokeDasharray: `${filled} ${CIRC}` }} />
      )}
      {score === null ? (
        <text x="100" y="84" textAnchor="middle" className="ovr__gauge-empty">No score yet</text>
      ) : (
        <>
          <text x="100" y="88" textAnchor="middle" className="ovr__gauge-num">{score}</text>
          <text x="100" y="105" textAnchor="middle" className="ovr__gauge-of">out of 100</text>
        </>
      )}
    </svg>
  );
}

export function OverallScoreCard({ report, onRunPillar }: OverallScoreCardProps) {
  const [showWhy, setShowWhy] = React.useState(false);
  const o: OverallScore = overallScore(report as never);
  const tone = band(o.score);
  const measured = o.pillars.filter((p) => p.measured);
  const earnedTotal = measured.reduce((s, p) => s + ((p.score ?? 0) * p.weight) / 100, 0);

  return (
    <section className="ovr" aria-labelledby="ovr-title">
      <header className="ovr__head">
        <div>
          <h2 id="ovr-title" className="ovr__title">Overall SEO Score</h2>
          <p className="ovr__sub">
            Four pillars, each scored on the share of check <em>weight</em> that passed, then weighted into one number.
          </p>
        </div>
      </header>

      <div className="ovr__hero">
        <div className="ovr__gauge-wrap">
          <Gauge score={o.score} tone={tone.color} />
          <span className="ovr__badge" style={{ color: tone.color, background: tone.tint }}>
            <span aria-hidden="true">{tone.glyph}</span>{tone.label}
          </span>
        </div>

        <div className="ovr__hero-side">
          <p className="ovr__lede" id="ovr-lede">
            {o.score === null ? (
              <><b>{o.measuredCount} of {o.pillarCount} pillars measured.</b> The score stays blank until all four
                have run, so an unmeasured pillar is never counted as a failing one.</>
            ) : (
              <><b>{earnedTotal.toFixed(1)} points earned of 100.</b> Each pillar can contribute up to its weight;
                the pale part of each band is what it lost.</>
            )}
          </p>

          {/* One 100-point bar: band width IS the pillar's weight, the solid part
              is what it earned. Four separate tracks fragmented the total and
              squeezed AEO into an unreadable sliver. */}
          <div className="ovr__bar" role="img"
               aria-label={`Weighted contribution out of 100 points: ${o.pillars.map((p) => `${p.title} ${p.measured ? `${(((p.score ?? 0) * p.weight) / 100).toFixed(1)} of ${p.weight}` : `not measured, ${p.weight} available`}`).join("; ")}`}>
            {o.pillars.map((p) => (
              <div key={p.key} className="ovr__band" style={{ width: `${p.weight}%`, color: PILLAR_HUE[p.key] }}
                   title={`${p.title}: ${p.measured ? `${(((p.score ?? 0) * p.weight) / 100).toFixed(1)} of ${p.weight} points` : "not measured"}`}>
                <div className="ovr__band-track">
                  <span className="ovr__band-fill" style={{ width: `${p.measured ? p.score : 0}%` }} />
                  {/* Benchmark: the 80 that counts as Strong. The distance from
                      the fill to this notch is the work left in that pillar. */}
                  <span className="ovr__band-target" aria-hidden="true" />
                </div>
              </div>
            ))}
          </div>

          <ul className="ovr__legend">
            <li className="ovr__legend-item ovr__legend-item--key">
              <span className="ovr__target-key" aria-hidden="true" />
              <span className="ovr__legend-name">target 80</span>
            </li>
            {o.pillars.map((p) => (
              <li key={p.key} className="ovr__legend-item">
                <span className="ovr__swatch" style={{ background: PILLAR_HUE[p.key] }} aria-hidden="true" />
                <span className="ovr__legend-name">{p.title}</span>
                <span className="ovr__legend-val">
                  {p.measured ? `${(((p.score ?? 0) * p.weight) / 100).toFixed(1)}` : "—"}
                  <span className="ovr__legend-max">/{p.weight}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="ovr__pillars">
        {o.pillars.map((p) => {
          const t = band(p.score);
          return (
            <article key={p.key} className="ovr__pillar" style={{ borderTopColor: PILLAR_HUE[p.key] }}>
              <div className="ovr__pillar-top">
                <span className="ovr__pillar-title">{p.title}</span>
                <span className="ovr__pillar-weight">{p.weight}%</span>
              </div>
              <div className="ovr__pillar-score" data-empty={!p.measured || undefined}>
                {p.measured ? <>{p.score}<span className="ovr__pillar-outof">/100</span></> : "Not measured"}
              </div>
              <div className="ovr__pillar-foot" style={{ color: t.color }}>
                <span aria-hidden="true">{t.glyph}</span>
                {p.measured
                  ? (p.deductions.length === 0
                      ? "all checks pass"
                      : `${p.deductions.length} failing`)
                  : `${p.weight} points unclaimed`}
              </div>
              {!p.measured && (
                <button type="button" className="link ovr__pillar-run" onClick={() => onRunPillar?.(p.key)}>
                  {p.howToMeasure} →
                </button>
              )}
            </article>
          );
        })}
      </div>

      {o.topDeductions.length > 0 && (
        <div className="ovr__why">
          <button type="button" className="link" onClick={() => setShowWhy((v) => !v)} aria-expanded={showWhy}>
            {showWhy ? "Hide what costs the most" : "Why this score →"}
          </button>
          {showWhy && (
            <table className="ovr__table">
              <caption className="ovr__caption">Failing checks ranked by weight — fixing the top rows moves the score most.</caption>
              <thead>
                <tr>{["Check", "Pillar", "Severity", "Weight"].map((h) => <th key={h} scope="col">{h}</th>)}</tr>
              </thead>
              <tbody>
                {o.topDeductions.map((d, i) => (
                  <tr key={`${d.code}-${i}`}>
                    <td>
                      <div className="ovr__check">{d.what}</div>
                      <code className="ovr__code">{d.code}</code>
                    </td>
                    <td className="ovr__muted">{d.group}</td>
                    <td style={{ color: d.severity === "error" ? "var(--bad)" : "var(--warn)", fontWeight: 600, whiteSpace: "nowrap" }}>
                      <span aria-hidden="true">{d.severity === "error" ? "■ " : "▲ "}</span>
                      {d.severity === "error" ? "Error" : "Warning"}
                    </td>
                    <td className="ovr__muted">{d.weight}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </section>
  );
}
