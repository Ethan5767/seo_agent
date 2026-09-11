# Design

The visual system for the REAI web app (`web/`). Strategy, users, and principles
live in [PRODUCT.md](./PRODUCT.md). This file is the "how it looks" half.

**Register:** product. Design serves the task. Earned familiarity beats novelty.

## Status

The app currently has **no stylesheet and no tokens**. Every value is typed inline
across 3,240 `style={{ }}` objects, which produced:

| Dimension | Distinct values in code | Target |
|---|---|---|
| padding | 132 | 7 |
| hex colors | 170 | ~28 roles |
| font sizes | 47 | 8 |
| border radii | 32 | 5 |
| gaps | 12+ | shares the space scale |

This file defines the target. The migration is tracked in
`docs/superpowers/plans/2026-09-11-ia-consolidation-and-design-system.md`.

**The palette below preserves the existing identity** (the slate ramp, indigo
primary, emerald success). It renames hexes into roles and removes the duplicates;
it does not re-brand the product. Two colors are corrected for contrast, because
they fail WCAG AA today.

## Color

Strategy: **restrained**. Neutral surfaces, one accent for primary action and
current selection, semantic colors for status only. Accent is never decoration.

Tokens are authored in hex to match the existing code exactly, with the OKLCH
equivalent noted where a value is new or corrected.

### Neutrals (the slate ramp, already in use)

| Token | Value | Role |
|---|---|---|
| `--bg` | `#f4f5f7` | App background (already set on `body`) |
| `--surface` | `#ffffff` | Cards, panels, table rows |
| `--surface-2` | `#f8fafc` | Secondary panel, table header, hover row |
| `--surface-3` | `#f1f5f9` | Inset wells, disabled fields |
| `--border` | `#e2e8f0` | Default hairline |
| `--border-strong` | `#cbd5e1` | Emphasised divider, input border |
| `--ink` | `#0f172a` | Headings, primary numerals |
| `--ink-body` | `#1e293b` | Body text |
| `--ink-muted` | `#475569` | Secondary text, labels, captions |
| `--ink-faint` | `#64748b` | Non-text only: icons, rules, disabled glyphs |

**Corrections, non-negotiable.** `#64748b` is used 444 times as body text and
measures **4.34:1** on `--surface-3` and 4.36:1 on `--bg`. It fails AA. `#94a3b8`
measures **2.34:1** and fails everywhere. Both are demoted:

- Text that was `#64748b` becomes `--ink-muted` (`#475569`, 6.92:1 worst case).
- Text that was `#94a3b8` becomes `--ink-muted`. It survives only as an icon or
  rule color, never as text.
- `--ink-faint` may not be used for any text a user must read, including
  placeholders. Placeholders take `--ink-muted`.

### Accent

| Token | Value | Role |
|---|---|---|
| `--accent` | `#4f46e5` | Primary button fill, current nav item, focus ring |
| `--accent-hover` | `#4338ca` | Primary button hover |
| `--accent-ink` | `#3730a3` | Accent text on a light tint (8.1:1 on white) |
| `--accent-tint` | `#eef2ff` | Selected row, active nav background |
| `--accent-border` | `#c7d2fe` | Border on an accent-tinted surface |

Indigo on white is 7.0:1 as a fill behind white text, which passes. Accent text on
a white surface uses `--accent-ink`, never `--accent`.

### Status

Status is **never carried by color alone**. Every status pairs its color with an
icon and a word. The tints already exist in the code; the text colors are darkened
where they failed.

| Token | Value | Role |
|---|---|---|
| `--ok` | `#047857` | Pass text and icon (5.7:1 on white) |
| `--ok-tint` | `#ecfdf5` | Pass background |
| `--ok-border` | `#a7f3d0` | Pass border |
| `--warn` | `#b45309` | Warning text and icon (5.0:1 on white) |
| `--warn-tint` | `#fffbeb` | Warning background |
| `--warn-border` | `#fde68a` | Warning border |
| `--bad` | `#b91c1c` | Error text and icon (6.4:1 on white) |
| `--bad-tint` | `#fef2f2` | Error background |
| `--bad-border` | `#fecaca` | Error border |
| `--info` | `#1d4ed8` | Info text (7.0:1 on white) |
| `--info-tint` | `#eff6ff` | Info background |
| `--info-border` | `#bfdbfe` | Info border |

`#059669` (94 uses, 3.44:1) is replaced by `--ok` for text. It may remain as a
fill behind white text, or as a chart mark.

### Rules

- Gray text on a colored tint is banned. On `--ok-tint`, text is `--ok`, not
  `--ink-muted`.
- Heavy or full-saturation accents never appear on inactive states.
- Chart color is a separate concern. Before any chart work, load the `dataviz`
  skill; do not invent a categorical palette inline.

## Typography

One family: **Inter**, already loaded in `app/layout.tsx` with a system fallback
stack. No second family. Weight and size carry hierarchy.

Fixed rem scale, no `clamp()`. Product UI is viewed at consistent DPI; fluid type
in a sidebar looks worse, not better.

| Token | Size | Line height | Weight | Use |
|---|---|---|---|---|
| `--text-xs` | 12px / 0.75rem | 1.4 | 500 | Badges, table micro-labels, chart axes |
| `--text-sm` | 13px / 0.8125rem | 1.45 | 400 | Dense table cells, secondary UI |
| `--text-base` | 14px / 0.875rem | 1.55 | 400 | **Default body. The floor for prose.** |
| `--text-md` | 16px / 1rem | 1.5 | 500 | Card titles, form labels of weight |
| `--text-lg` | 18px / 1.125rem | 1.4 | 600 | Section headings |
| `--text-xl` | 22px / 1.375rem | 1.3 | 600 | Page headings |
| `--text-2xl` | 28px / 1.75rem | 1.25 | 700 | Screen title, hero metric |
| `--text-3xl` | 36px / 2.25rem | 1.15 | 700 | Score gauge numeral only |

**12px is the floor.** Nothing renders below it. Today 723 elements sit at 11px or
smaller; every one moves up. The migration map:

| Current | Becomes |
|---|---|
| 8, 9, 10, 11 | `--text-xs` (12) |
| 12, 13 | `--text-sm` (13) |
| 14, 15 | `--text-base` (14) |
| 16, 17 | `--text-md` (16) |
| 18, 19, 20 | `--text-lg` (18) |
| 22, 24, 26 | `--text-xl` (22) |
| 28, 32 | `--text-2xl` (28) |
| 36+ | `--text-3xl` (36) |

Other rules:

- Numerals in tables and metrics use `font-variant-numeric: tabular-nums`. Columns
  of figures that do not align are unreadable at a glance.
- Prose caps at 70ch. Table content may run wider.
- `text-wrap: balance` on headings, `text-wrap: pretty` on paragraphs.
- No uppercase tracked eyebrow above every section.

## Space

4px base. Seven steps replace 132 hand-typed padding values. Gap, padding, and
margin all draw from this one scale.

| Token | Value | Typical use |
|---|---|---|
| `--space-1` | 4px | Icon-to-label, badge internals |
| `--space-2` | 8px | Tight stack, chip padding |
| `--space-3` | 12px | Control padding, list row gap |
| `--space-4` | 16px | Card padding, standard block gap |
| `--space-5` | 24px | Section gap inside a panel |
| `--space-6` | 32px | Between panels |
| `--space-7` | 48px | Between major page regions |

Component padding is standardized, so the six near-identical values in the code
(`10px 14px`, `11px 14px`, `10px 12px`, `12px 14px`, `14px 16px`, `16px 18px`)
collapse to three real ones:

| Component | Padding |
|---|---|
| Chip / badge | `2px 8px` |
| Control (button, input, select) | `8px 12px`, min-height 34px |
| Control, large | `12px 16px`, min-height 42px |
| Table cell | `8px 12px` |
| Card / panel | `16px` |
| Panel, roomy | `24px` |

Rhythm comes from varying which step is used between regions, not from inventing
a value between steps. A layout that needs 11px is a layout that wants 12.

## Radius

| Token | Value | Use |
|---|---|---|
| `--radius-xs` | 4px | Chips, badges, tags |
| `--radius-sm` | 6px | Buttons, inputs, selects |
| `--radius-md` | 8px | Cards, panels, popovers |
| `--radius-lg` | 12px | Modals, large feature panels |
| `--radius-full` | 999px | Pills, avatars, status dots |

The 32 distinct radii in the code map onto these: 0-2 → none, 3-5 → xs, 6-7 → sm,
8-10 → md, 12-20 → lg, anything >= 24 or 50 → full.

## Elevation

Shadow is used sparingly. A hairline border does most of the separating work.

| Token | Value | Use |
|---|---|---|
| `--shadow-sm` | `0 1px 2px rgb(15 23 42 / 0.06)` | Resting card |
| `--shadow-md` | `0 4px 12px rgb(15 23 42 / 0.08)` | Popover, dropdown |
| `--shadow-lg` | `0 12px 32px rgb(15 23 42 / 0.12)` | Modal |

## Z-index

A named scale. Never an arbitrary 999.

```
--z-base: 0
--z-dropdown: 100
--z-sticky: 200
--z-backdrop: 300
--z-modal: 400
--z-toast: 500
--z-tooltip: 600
```

## Motion

| Token | Value | Use |
|---|---|---|
| `--ease` | `cubic-bezier(0.16, 1, 0.3, 1)` | ease-out-expo, the default |
| `--dur-fast` | 120ms | Hover, focus, color change |
| `--dur` | 180ms | Disclosure, tab change, popover |
| `--dur-slow` | 240ms | Drawer, modal |

- Motion conveys state. No orchestrated page-load choreography; the operator loads
  into a task.
- No bounce, no elastic.
- Never animate layout properties. Transform and opacity, plus blur or clip-path
  when they genuinely serve.
- Every transition needs a `prefers-reduced-motion: reduce` branch, and the
  existing `reaiShimmer` keyframe must be covered by it.
- Reveals enhance already-visible content. Never gate visibility on a transition.

## Components

Every interactive component ships all seven states: default, hover, focus-visible,
active, disabled, loading, error. Shipping four of seven is shipping a bug.

- **Focus** is a 2px `--accent` ring at 2px offset. `outline: none` without a
  replacement is banned.
- **Loading** is a skeleton in the content's own shape, not a centered spinner.
  `reaiShimmer` already exists for this and stays.
- **Empty states** teach the interface: what this screen is for, and the one
  action that fills it. Never a bare "No data".
- **Tables** are real `<table>` elements with scoped `<th>`. Numeric columns are
  right-aligned and tabular. Header row is `--surface-2` and sticky.
- **Buttons** come in exactly three variants: primary (accent fill), secondary
  (surface fill, `--border-strong` hairline), and quiet (text only). One shape
  across the whole app.
- **Cards are not the default answer.** A list of findings is a list. Nested cards
  are always wrong.
- **Modals are the last resort.** Exhaust inline disclosure first.

## Layout

- App shell: one sidebar plus a content column. The second nav layer (the icon
  rail) is removed; see the IA plan.
- Content column caps at 1200px and centers, which matches the existing
  `maxWidth: 1200` convention already in `Overview.tsx`.
- Flexbox for one dimension, grid for two. Responsive grids use
  `repeat(auto-fit, minmax(280px, 1fr))` rather than breakpoint ladders.
- Responsive behavior is structural: the sidebar collapses, tables scroll inside
  their own container, columns stack. Type does not fluidly resize.
- The page body never scrolls horizontally. Tables and code blocks scroll inside
  `overflow-x: auto` wrappers.

## Dark mode

Not in scope for this pass. When it lands, every token above gets a dark value in
a single `:root[data-theme="dark"]` block. Because components will reference
tokens rather than hexes by then, that is one file, not 3,240 edits. This is the
main structural reason to do the token sweep.
