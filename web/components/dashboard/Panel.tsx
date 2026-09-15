"use client";

import React from "react";

/**
 * The shared building blocks of every tool page (DESIGN.md v2 §5): a panel with
 * one header (title, provenance, the link into the full tool) and a stat strip
 * for headline figures. Styles live in app/tokens.css (`.seo-panel`, `.stat-strip`).
 */

export function Panel({
  title, subtitle, action, children, area, className, id,
}: {
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  action?: { label: string; onClick: () => void };
  children: React.ReactNode;
  /** A named grid area, when the panel sits in a named-area grid. */
  area?: string;
  className?: string;
  id?: string;
}) {
  const auto = React.useId();
  const hid = id ?? `panel-${auto.replace(/:/g, "")}`;
  return (
    <section className={`seo-panel${className ? ` ${className}` : ""}`} style={area ? { gridArea: area } : undefined} aria-labelledby={hid}>
      <header className="seo-panel__head">
        <div style={{ minWidth: 0 }}>
          <h3 id={hid} className="seo-panel__title">{title}</h3>
          {subtitle && <div className="seo-panel__sub">{subtitle}</div>}
        </div>
        {action && (
          <button type="button" className="seo-panel__link" onClick={action.onClick}>
            {action.label}
            <span aria-hidden="true">→</span>
          </button>
        )}
      </header>
      <div className="seo-panel__body">{children}</div>
    </section>
  );
}

export type Stat = {
  label: string;
  value: React.ReactNode;
  /** A short qualifier under the number: provenance, unit, or an estimate label. */
  sub?: React.ReactNode;
  /** Text colour for a number whose colour means something (a status). */
  tone?: string;
};

/** Headline figures in one strip, divided by hairlines rather than boxed one by one. */
export function StatStrip({ stats, label }: { stats: Stat[]; label?: string }) {
  return (
    <dl className="stat-strip" aria-label={label}>
      {stats.map((s) => (
        <div key={s.label} className="stat-strip__cell">
          <dt className="stat-strip__label">{s.label}</dt>
          <dd className="stat-strip__value" style={s.tone ? { color: s.tone } : undefined}>{s.value}</dd>
          {s.sub && <dd className="stat-strip__sub">{s.sub}</dd>}
        </div>
      ))}
    </dl>
  );
}
