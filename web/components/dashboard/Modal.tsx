"use client";

import React from "react";
import { createPortal } from "react-dom";

/**
 * The one modal dialog (UX audit P1 #4). Every modal in the app renders through
 * this, so the accessibility contract lives in one place:
 *
 *   - role="dialog" + aria-modal="true", named by `label` or `labelledBy`;
 *   - on open, focus moves to the first form field (else the first control,
 *     else the dialog itself);
 *   - Tab and Shift+Tab stay inside the dialog;
 *   - Escape closes;
 *   - on close, focus returns to whatever opened it;
 *   - the page behind does not scroll while it is open.
 *
 * `children` is the dialog's own card. Pass `card` to get the standard card
 * (white, 12px radius, padding) instead of bringing one.
 */

const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type="hidden"]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

export function Modal({
  open = true, onClose, label, labelledBy, children, card = false, width = 560, align = "center", closeOnBackdrop = true,
}: {
  open?: boolean;
  onClose: () => void;
  /** Accessible name when the dialog has no visible heading id. */
  label?: string;
  /** id of the visible heading that names the dialog. */
  labelledBy?: string;
  children: React.ReactNode;
  /** Wrap children in the standard dialog card. */
  card?: boolean;
  width?: number;
  /** "top" for tall documents that scroll (reports). */
  align?: "center" | "top";
  closeOnBackdrop?: boolean;
}) {
  const dialogRef = React.useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  React.useEffect(() => {
    // The portal renders after mount, so wait for it before moving focus.
    if (!open || !mounted) return;
    const opener = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    const focusables = () => Array.from(dialog?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []).filter((el) => el.offsetParent !== null || el === document.activeElement);
    // First form field, else first control, else the dialog.
    const field = dialog?.querySelector<HTMLElement>('input:not([type="hidden"]):not([disabled]),select:not([disabled]),textarea:not([disabled])');
    (field ?? focusables()[0] ?? dialog)?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.stopPropagation(); onClose(); return; }
      if (e.key !== "Tab") return;
      const els = focusables();
      if (!els.length) { e.preventDefault(); dialog?.focus(); return; }
      const first = els[0], last = els[els.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog)) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKey, true);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.body.style.overflow = prevOverflow;
      if (opener && document.contains(opener)) opener.focus();
    };
    // onClose changes identity on every render of most callers; the effect is
    // about the open/close transition only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, mounted]);

  if (!open || !mounted) return null;
  return createPortal(
    <div
      className={`modal-backdrop${align === "top" ? " modal-backdrop--top" : ""}`}
      onMouseDown={(e) => { if (closeOnBackdrop && e.target === e.currentTarget) onClose(); }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={labelledBy ? undefined : label}
        aria-labelledby={labelledBy}
        tabIndex={-1}
        className={card ? "modal-card" : "modal-frame"}
        style={card ? { maxWidth: width } : undefined}
      >
        {children}
      </div>
    </div>,
    document.body,
  );
}
