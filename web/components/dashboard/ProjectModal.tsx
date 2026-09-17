"use client";

import React from "react";
import { RepoPicker } from "./RepoPicker";
import { Modal } from "./Modal";

/**
 * Create a project, or correct one that already exists.
 *
 * "I create a project, done — I also want to edit those details too. Example: I
 * put the wrong website URL, so I should be able to edit it."
 *
 * ONE form serves both. Create and edit ask for exactly the same nine fields,
 * and a second copy of this markup is a second place for them to drift apart —
 * which is how a field ends up editable on create and silently unreachable
 * afterwards.
 *
 * Lifted out of `ReaiDashboard.tsx` when adding edit pushed that file back over
 * the 13,000-line ratchet in `tests/measure.test.mjs`. AGENTS.md Rule 1 is 1,000
 * lines; the ratchet is there so the file cannot grow back, and raising it to
 * admit a new feature is exactly the move it exists to refuse.
 */
export function ProjectModal({
  open, editing, onClose, onSubmit, saving, error,
  biz, setBiz, url, setUrl, model, setModel, repo, setRepo,
  goal, setGoal, kw, setKw, kwList, setKwList, githubToken,
}: {
  open: boolean;
  /** The project being corrected, or null when creating one. */
  editing: any | null;
  onClose: () => void;
  onSubmit: (e: React.FormEvent) => void;
  saving: boolean;
  /** Why the last save failed. Rendered in place — the modal stays open. */
  error: string | null;
  biz: string; setBiz: (v: string) => void;
  url: string; setUrl: (v: string) => void;
  model: string; setModel: (v: string) => void;
  repo: string; setRepo: (v: string) => void;
  goal: string; setGoal: (v: string) => void;
  kw: string; setKw: (v: string) => void;
  kwList: string[]; setKwList: (v: string[]) => void;
  githubToken: () => Promise<string>;
}) {
  const ids = React.useId();
  const fid = (name: string) => `${ids}-${name}`;
  const [urlTouched, setUrlTouched] = React.useState(false);
  React.useEffect(() => { if (open) setUrlTouched(false); }, [open]);
  const urlError = urlTouched ? websiteProblem(url) : null;
  const addKeyword = () => {
    if (kw.trim() && !kwList.includes(kw.trim())) {
      setKwList([...kwList, kw.trim()]);
      setKw("");
    }
  };

  if (!open) return null;
  return (
    <Modal onClose={onClose} labelledBy={fid("title")} card width={560}>
      <div className="modal-card__head">
        <h2 id={fid("title")} className="modal-card__title">
          {editing ? "Edit Project" : "Create SEO Project"}
        </h2>
        <button type="button" onClick={onClose} className="modal-card__close" aria-label="Close">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      {!editing && (
        <p className="modal-card__lede">
          Add the website to audit. Keywords, goals and the code repository for fixes can be set later.
        </p>
      )}

      <form noValidate
        onSubmit={(e) => {
          if (websiteProblem(url)) { e.preventDefault(); setUrlTouched(true); return; }
          onSubmit(e);
        }}
      >
        {/* Create asks for the site and a name only (UX audit #29). Everything
            else is project settings, reached through Edit when it is needed. */}
        <div className="form-field">
          <label htmlFor={fid("url")} className="form-field__label">Website URL <span aria-hidden="true">*</span></label>
          <input
            id={fid("url")}
            type="url"
            inputMode="url"
            autoComplete="url"
            required
            aria-required="true"
            aria-invalid={urlError ? true : undefined}
            aria-describedby={urlError ? fid("url-error") : undefined}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={() => setUrlTouched(true)}
            placeholder="https://example.com"
            className="form-field__input"
          />
          {urlError && <p id={fid("url-error")} className="form-field__error" role="alert">{urlError}</p>}
        </div>

        <div className="form-field">
          <label htmlFor={fid("biz")} className="form-field__label">Business name <span className="muted">(optional)</span></label>
          <input
            id={fid("biz")}
            type="text"
            value={biz}
            onChange={(e) => setBiz(e.target.value)}
            placeholder="e.g. Acme Studio"
            className="form-field__input"
          />
        </div>

        {editing && (
          <>
            <div className="form-field">
              <label htmlFor={fid("kw")} className="form-field__label">Target keywords</label>
              <div style={{ display: "flex", gap: "var(--space-2)" }}>
                <input
                  id={fid("kw")}
                  type="text"
                  value={kw}
                  onChange={(e) => setKw(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") { e.preventDefault(); addKeyword(); }
                  }}
                  aria-describedby={fid("kw-hint")}
                  placeholder="keyword phrase"
                  className="form-field__input"
                  style={{ flex: 1 }}
                />
                <button type="button" onClick={addKeyword} className="btn btn--secondary btn--sm">Add</button>
              </div>
              <p id={fid("kw-hint")} className="form-field__hint">Press Enter or Add after each phrase.</p>
              {kwList.length > 0 && (
                <ul className="chip-list" aria-label="Keywords added">
                  {kwList.map((k) => (
                    <li key={k} className="chip">
                      {k}
                      <button type="button" className="chip__remove" aria-label={`Remove ${k}`} onClick={() => setKwList(kwList.filter((x) => x !== k))}>×</button>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="form-field">
              <label htmlFor={fid("goal")} className="form-field__label">Growth goal</label>
              <input
                id={fid("goal")}
                type="text"
                value={goal}
                onChange={(e) => setGoal(e.target.value)}
                placeholder="e.g. Increase organic signups"
                className="form-field__input"
              />
            </div>

            <div className="form-field">
              <label htmlFor={fid("model")} className="form-field__label">How fixes are made</label>
              <select id={fid("model")} value={model} onChange={(e) => setModel(e.target.value)} className="form-field__input">
                <option value="B">Model B — Claude Code fixes code directly</option>
                <option value="A">Model A — Read-only brief</option>
              </select>
            </div>

            {/* Tools check the live domain only. The repository is used by Fix
                (Model B) and nothing else, so it is tucked away, not asked up front. */}
            {model === "B" && (
              <details className="form-field" open={Boolean(repo)}>
                <summary className="form-field__label" style={{ cursor: "pointer" }}>Advanced: source code repository (optional, used only by Fix)</summary>
                <div style={{ marginTop: "var(--space-2)" }}>
                  <RepoPicker
                    value={repo}
                    onChange={setRepo}
                    getToken={githubToken}
                    open={open}
                  />
                </div>
              </details>
            )}
          </>
        )}

        {editing && url.trim() && url.trim() !== (editing.website || "") && (
          <div className="form-note form-note--warn">
            <b>This changes the site that gets measured.</b> Scans already on this project
            measured <code>{editing.domain}</code>. They keep the URL they ran against
            and are not rewritten, so past scores stay attached to the old site. The next
            scan is the first one that measures the new one.
          </div>
        )}

        {error && (
          <div role="alert" className="form-note form-note--bad">
            <b>Not saved.</b> {error}
          </div>
        )}

        <div className="modal-card__actions">
          <button type="button" onClick={onClose} className="btn btn--secondary">Cancel</button>
          <button type="submit" disabled={saving || !url.trim()} className="btn btn--primary">
            {saving ? (editing ? "Saving..." : "Creating...") : (editing ? "Save Changes" : "Create Project")}
          </button>
        </div>
      </form>
    </Modal>
  );
}

/** Why a website value cannot be audited, in plain words; null when it can. */
export function websiteProblem(value: string): string | null {
  const v = value.trim();
  if (!v) return "Enter the website address, for example https://example.com.";
  try {
    const u = new URL(/^[a-z]+:\/\//i.test(v) ? v : `https://${v}`);
    if (!/^https?:$/.test(u.protocol)) return "Use an http or https address.";
    if (!u.hostname.includes(".") || /\s/.test(v)) return "That does not look like a website address. Try https://example.com.";
    return null;
  } catch {
    return "That does not look like a website address. Try https://example.com.";
  }
}
