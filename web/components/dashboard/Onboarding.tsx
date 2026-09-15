"use client";

import React from "react";
import { websiteProblem } from "@/components/dashboard/ProjectModal";

/**
 * First run (UX audit P1 #3, P3 #28). With no project the Dashboard used to
 * render a "() ▼" title, a blank project picker, nine empty panels and a
 * disabled Run Audit. Now it renders this and nothing else: one field, one
 * button, and where the user is in the three steps.
 */

export type OnboardingStep = 1 | 2 | 3;

const STEPS: Array<{ n: OnboardingStep; label: string }> = [
  { n: 1, label: "Add your website" },
  { n: 2, label: "Run the on-page audit" },
  { n: 3, label: "Fix what it finds" },
];

/** The three steps with the current one marked; used here and on a project's first visit. */
export function OnboardingSteps({ current }: { current: OnboardingStep }) {
  return (
    <ol className="onboard-steps" aria-label={`Getting started, step ${current} of 3`}>
      {STEPS.map((s) => {
        const state = s.n < current ? "done" : s.n === current ? "current" : "todo";
        return (
          <li key={s.n} className={`onboard-steps__item onboard-steps__item--${state}`} aria-current={state === "current" ? "step" : undefined}>
            <span className="onboard-steps__num" aria-hidden="true">
              {state === "done" ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12l5 5L20 7" /></svg>
              ) : s.n}
            </span>
            <span className="onboard-steps__label">
              {s.label}
              {state === "done" && <span className="visually-hidden"> (done)</span>}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function Onboarding({
  url, setUrl, biz, setBiz, saving, onSubmit, projects, onChooseProject,
}: {
  url: string;
  setUrl: (v: string) => void;
  biz: string;
  setBiz: (v: string) => void;
  saving: boolean;
  onSubmit: (e: React.FormEvent) => void;
  /** Projects that exist but none is open: offer them before a new one. */
  projects?: Array<{ id: string; business?: string; domain?: string }>;
  onChooseProject?: (id: string) => void;
}) {
  const ids = React.useId();
  const [touched, setTouched] = React.useState(false);
  const problem = touched ? websiteProblem(url) : null;
  const hasProjects = Boolean(projects && projects.length);

  return (
    <section className="onboard" aria-labelledby={`${ids}-title`}>
      <OnboardingSteps current={1} />
      <h1 id={`${ids}-title`} className="onboard__title">{hasProjects ? "Choose a project" : "Add your website"}</h1>
      <p className="onboard__lede">
        REAI checks your site&apos;s pages for what holds it back in search and AI answers, ranks what to fix first,
        and can make the fixes for you to review.
      </p>

      {hasProjects && onChooseProject && (
        <ul className="onboard__projects" aria-label="Your projects">
          {projects!.map((p) => (
            <li key={p.id}>
              <button type="button" className="btn btn--secondary onboard__project" onClick={() => onChooseProject(p.id)}>
                <span>{p.business || p.domain}</span>
                {p.domain && p.business && <span className="muted">{p.domain}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}

      <form
        className="onboard__form"
        noValidate
        onSubmit={(e) => {
          if (websiteProblem(url)) { e.preventDefault(); setTouched(true); return; }
          onSubmit(e);
        }}
      >
        {hasProjects && <h2 className="onboard__subtitle">Or add another website</h2>}
        <div className="form-field">
          <label htmlFor={`${ids}-url`} className="form-field__label">Website address</label>
          <input
            id={`${ids}-url`}
            type="url"
            inputMode="url"
            autoComplete="url"
            required
            aria-required="true"
            aria-invalid={problem ? true : undefined}
            aria-describedby={problem ? `${ids}-url-error` : undefined}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={() => setTouched(true)}
            placeholder="https://example.com"
            className="form-field__input"
          />
          {problem && <p id={`${ids}-url-error`} role="alert" className="form-field__error">{problem}</p>}
        </div>
        <div className="form-field">
          <label htmlFor={`${ids}-biz`} className="form-field__label">Business name <span className="muted">(optional)</span></label>
          <input id={`${ids}-biz`} type="text" value={biz} onChange={(e) => setBiz(e.target.value)} placeholder="e.g. Acme Studio" className="form-field__input" />
        </div>
        <button type="submit" className="btn btn--primary btn--lg" disabled={saving}>
          {saving ? "Adding…" : "Add website"}
        </button>
        <p className="form-field__hint">Free. The audit reads your public pages only; nothing on your site changes.</p>
      </form>
    </section>
  );
}
