/**
 * Typed access to the design tokens in `app/tokens.css`.
 *
 * The app styles itself with inline `style={{ }}` objects. That stays legal.
 * What stops is the magic number: 132 distinct padding values, 170 hex colors,
 * 47 font sizes and 32 radii, all typed by hand, which is why spacing reads as
 * misaligned and the same gray appears in six shades.
 *
 * Reference a token instead:
 *
 *     <div style={{ padding: space[4], background: color.surface }} />
 *
 * Every value resolves to a CSS custom property, so a future theme is one file.
 * Spec and rationale: /DESIGN.md.
 */

/** 4px base. Padding, margin and gap all draw from this one scale. */
export const space = {
  /** 4px — icon-to-label, badge internals */
  1: "var(--space-1)",
  /** 8px — tight stack, chip padding */
  2: "var(--space-2)",
  /** 12px — control padding, list row gap */
  3: "var(--space-3)",
  /** 16px — card padding, standard block gap */
  4: "var(--space-4)",
  /** 24px — section gap inside a panel */
  5: "var(--space-5)",
  /** 32px — between panels */
  6: "var(--space-6)",
  /** 48px — between major page regions */
  7: "var(--space-7)",
} as const;

/**
 * Standard component padding. Use these rather than composing two space steps,
 * so every button in the app is the same height.
 */
export const pad = {
  chip: "2px var(--space-2)",
  control: "var(--space-2) var(--space-3)",
  controlLg: "var(--space-3) var(--space-4)",
  cell: "var(--space-2) var(--space-3)",
  card: "var(--space-4)",
  panel: "var(--space-5)",
} as const;

/** Minimum hit heights that go with `pad.control` / `pad.controlLg`. */
export const controlHeight = { sm: 34, lg: 42 } as const;

/** Fixed rem scale. No clamp: product UI is read at consistent DPI. */
export const text = {
  /** 12px — badges, table micro-labels, chart axes. The floor. */
  xs: "var(--text-xs)",
  /** 13px — dense table cells, secondary UI */
  sm: "var(--text-sm)",
  /** 14px — default body, the floor for prose */
  base: "var(--text-base)",
  /** 16px — card titles, weighted form labels */
  md: "var(--text-md)",
  /** 18px — section headings */
  lg: "var(--text-lg)",
  /** 22px — page headings */
  xl: "var(--text-xl)",
  /** 28px — screen title, hero metric */
  "2xl": "var(--text-2xl)",
  /** 36px — score gauge numeral only */
  "3xl": "var(--text-3xl)",
} as const;

export const leading = {
  tight: "var(--leading-tight)",
  snug: "var(--leading-snug)",
  normal: "var(--leading-normal)",
} as const;

export const color = {
  bg: "var(--bg)",
  surface: "var(--surface)",
  surface2: "var(--surface-2)",
  surface3: "var(--surface-3)",
  border: "var(--border)",
  borderStrong: "var(--border-strong)",

  /** Headings and primary numerals. */
  ink: "var(--ink)",
  /** Body text. */
  inkBody: "var(--ink-body)",
  /** Secondary text, labels, captions, placeholders. */
  inkMuted: "var(--ink-muted)",
  /**
   * Icons, rules and disabled glyphs ONLY.
   * 4.34:1 on `surface3` — it fails WCAG AA for body text. Never use it for
   * text a user has to read.
   */
  inkFaint: "var(--ink-faint)",

  /** Primary button fill, current nav item, focus ring. Never decoration. */
  accent: "var(--accent)",
  accentHover: "var(--accent-hover)",
  /** Accent-colored TEXT on a light surface. `accent` itself is too light. */
  accentInk: "var(--accent-ink)",
  accentTint: "var(--accent-tint)",
  accentBorder: "var(--accent-border)",

  ok: "var(--ok)",
  okTint: "var(--ok-tint)",
  okBorder: "var(--ok-border)",
  warn: "var(--warn)",
  warnTint: "var(--warn-tint)",
  warnBorder: "var(--warn-border)",
  bad: "var(--bad)",
  badTint: "var(--bad-tint)",
  badBorder: "var(--bad-border)",
  info: "var(--info)",
  infoTint: "var(--info-tint)",
  infoBorder: "var(--info-border)",
} as const;

export const radius = {
  /** 4px — chips, badges, tags */
  xs: "var(--radius-xs)",
  /** 6px — buttons, inputs, selects */
  sm: "var(--radius-sm)",
  /** 8px — cards, panels, popovers */
  md: "var(--radius-md)",
  /** 12px — modals, large feature panels */
  lg: "var(--radius-lg)",
  /** pills, avatars, status dots */
  full: "var(--radius-full)",
} as const;

export const shadow = {
  sm: "var(--shadow-sm)",
  md: "var(--shadow-md)",
  lg: "var(--shadow-lg)",
} as const;

/** Named stacking order. Never write an arbitrary 999. */
export const z = {
  base: "var(--z-base)",
  dropdown: "var(--z-dropdown)",
  sticky: "var(--z-sticky)",
  backdrop: "var(--z-backdrop)",
  modal: "var(--z-modal)",
  toast: "var(--z-toast)",
  tooltip: "var(--z-tooltip)",
} as const;

export const motion = {
  ease: "var(--ease)",
  fast: "var(--dur-fast)",
  base: "var(--dur)",
  slow: "var(--dur-slow)",
  /** `transition: ${motion.transition("background", "border-color")}` */
  transition: (...props: string[]) =>
    props.map((p) => `${p} var(--dur) var(--ease)`).join(", "),
} as const;

export const layout = {
  contentMax: "var(--content-max)",
  proseMax: "var(--prose-max)",
} as const;

/**
 * Status role for a pass / warn / fail indicator.
 * Returns the trio so callers never pair a gray text with a colored tint.
 */
export type StatusTone = "ok" | "warn" | "bad" | "info" | "neutral";

export function tone(status: StatusTone): {
  fg: string;
  bg: string;
  border: string;
} {
  switch (status) {
    case "ok":
      return { fg: color.ok, bg: color.okTint, border: color.okBorder };
    case "warn":
      return { fg: color.warn, bg: color.warnTint, border: color.warnBorder };
    case "bad":
      return { fg: color.bad, bg: color.badTint, border: color.badBorder };
    case "info":
      return { fg: color.info, bg: color.infoTint, border: color.infoBorder };
    case "neutral":
      return {
        fg: color.inkMuted,
        bg: color.surface3,
        border: color.border,
      };
  }
}
