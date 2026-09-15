# Design System

**Project:** REAI (the web app in `web/`)
**Version:** 2.0
**Style reference:** Semrush.com (bold, data-driven SaaS aesthetic)
**Last updated:** 2026-09-15

Strategy, users and principles live in [PRODUCT.md](./PRODUCT.md). This file is the
"how it looks" half. It replaces version 1 (slate and indigo, 2026-09-11).

**Register:** product. The tokens live in `web/app/tokens.css`; components reach them
through `var(--…)`. §12 says how this system maps onto the names the code already uses,
and §13 records where a value was changed to meet the accessibility rules in §8.

---

## 1. Design Principles

1. **Clarity first.** Every screen should communicate its purpose in under 3 seconds.
2. **Data-forward.** Charts, numbers and stats are treated as hero content, not afterthoughts.
3. **Confident contrast.** Bold dark sections paired with clean light sections create rhythm. In the app, the navigation is the dark section and the workspace is light.
4. **Consistency over novelty.** Reuse the same components everywhere; don't invent one-off patterns.
5. **Accessible by default.** Minimum AA contrast, visible focus states, readable type at every size.

---

## 2. Color Palette

### 2.1 Brand Colors

| Token | Hex | Usage |
|---|---|---|
| `--color-primary` | `#FF642D` | Brand mark, highlights, active indicators, chart accents, large fills with no text on them |
| `--color-primary-strong` | `#C2410C` | Primary CTA buttons (white label), links, focus ring. See §13 |
| `--color-primary-hover` | `#9A3412` | Hover/active state for primary buttons and links |
| `--color-primary-light` | `#FFE8DE` | Subtle backgrounds, badges, tags, selected rows |
| `--color-primary-border` | `#FFC9B3` | Border on a primary-light surface |

### 2.2 Neutrals (Dark UI)

| Token | Hex | Usage |
|---|---|---|
| `--color-ink-900` | `#111317` | Primary dark background (navigation, dark sections) |
| `--color-ink-800` | `#1B1E24` | Secondary dark surface (cards and hover on dark bg) |
| `--color-ink-700` | `#2A2E36` | Borders and dividers on dark surfaces |

### 2.3 Neutrals (Light UI)

| Token | Hex | Usage |
|---|---|---|
| `--color-white` | `#FFFFFF` | Cards, panels, inputs |
| `--color-gray-50` | `#F7F8FA` | Page background, section backgrounds, alternating rows |
| `--color-gray-100` | `#EDEFF2` | Dividers, table rules |
| `--color-gray-300` | `#878E99` | Input and control borders. See §13 |
| `--color-gray-400` | `#9AA0AA` | Disabled glyphs, icons, chart gridlines. Never text a user must read |
| `--color-gray-600` | `#5C6470` | Secondary/body text, labels, placeholders |
| `--color-gray-900` | `#1A1D22` | Primary text, headings, numbers |

### 2.4 Semantic Colors

Each status has a **fill** (the brand hue, for bars, dots and icons beside a word) and a
**text** shade that passes 4.5:1 on white.

| Token | Hex | Usage |
|---|---|---|
| `--color-success` | `#1DB954` | Positive fills: chart bars, status dots |
| `--color-success-text` | `#15803D` | Positive text and icons |
| `--color-warning` | `#F5A623` | Warning fills |
| `--color-warning-text` | `#B45309` | Warning text and icons |
| `--color-error` | `#E5484D` | Error fills, destructive button background with a dark-red hover |
| `--color-error-text` | `#C62828` | Error text and icons |
| `--color-info` | `#3B82F6` | Informational fills, links on dark bg |
| `--color-info-text` | `#2563EB` | Informational text on light bg |

### 2.5 Usage Rules
- Never place `--color-primary` text on `--color-primary-light` background (2.5:1). Text on a primary-light surface is `--color-primary-hover`.
- Dark sections (`--color-ink-900`) always pair with white or `--color-gray-100` text, never gray-600.
- Use no more than **one** accent color per screen section to avoid visual noise.
- Status is never carried by color alone: pair it with an icon and a word.

---

## 3. Typography

### 3.1 Font Family

```css
--font-heading: 'Inter', 'Helvetica Neue', Arial, sans-serif;
--font-body: 'Inter', 'Helvetica Neue', Arial, sans-serif;
--font-mono: 'Roboto Mono', 'SF Mono', monospace;
```

> Semrush uses a tight, grotesque sans-serif. Inter is a strong, free alternative with similar proportions and excellent screen legibility. It is already loaded in `web/app/layout.tsx`.

### 3.2 Type Scale

| Token | Size / Line Height | Weight | Usage |
|---|---|---|---|
| `--text-display` | 56px / 64px | 700 | Hero headlines only (marketing; not used in the app) |
| `--text-h1` | 40px / 48px | 700 | Marketing page titles |
| `--text-h2` | 32px / 40px | 700 | Section headers |
| `--text-h3` | 24px / 32px | 600 | App page titles, card/subsection headers |
| `--text-h4` | 18px / 26px | 600 | Panel titles, small headers |
| `--text-body-lg` | 18px / 28px | 400 | Lead paragraphs |
| `--text-body` | 16px / 24px | 400 | Default body text |
| `--text-body-sm` | 14px / 20px | 400 | Secondary text, captions, dense table cells |
| `--text-caption` | 12px / 16px | 500 | Labels, tags, timestamps. The floor: nothing renders smaller |

### 3.3 Rules
- Headlines are always tight-tracked (`letter-spacing: -0.02em`) and bold.
- Body copy uses `--color-gray-600` at 100% opacity, never lighter.
- Never use more than 3 type sizes on a single screen fold.
- Numbers/stats (KPIs) use tabular figures (`font-variant-numeric: tabular-nums`).

---

## 4. Spacing & Layout

### 4.1 Spacing Scale (8px base grid)

| Token | Value |
|---|---|
| `--space-1` | 4px |
| `--space-2` | 8px |
| `--space-3` | 12px |
| `--space-4` | 16px |
| `--space-6` | 24px |
| `--space-8` | 32px |
| `--space-12` | 48px |
| `--space-16` | 64px |
| `--space-24` | 96px |

### 4.2 Grid
- **Max content width:** 1280px, centered (marketing). App workspaces use the full column beside the navigation.
- **Columns:** 12-column grid, 24px gutters (desktop), 16px (mobile).
- **Section vertical padding:** 96px desktop / 48px mobile (marketing). App panels are separated by 24px.

### 4.3 Breakpoints

| Name | Width |
|---|---|
| `sm` | 480px |
| `md` | 768px |
| `lg` | 1024px |
| `xl` | 1280px |
| `2xl` | 1440px |

Dashboard grids respond to their container width (container queries), because the
workspace width depends on the navigation, not on the viewport.

---

## 5. Components

### 5.1 Buttons

| Variant | Background | Text | Border | Hover |
|---|---|---|---|---|
| Primary | `--color-primary-strong` | White | none | `--color-primary-hover` |
| Secondary | `--color-white` | `--color-gray-900` | 1px `--color-gray-300` | bg `--color-gray-50` |
| Ghost (on dark) | Transparent | White | 1px rgba(255,255,255,0.3) | bg rgba(255,255,255,0.1) |
| Destructive | `--color-error-text` | White | none | darken 10% |

- Height: 44px (default), 36px (small, dense toolbars and table rows), 52px (large).
- Border radius: `8px`.
- Padding: `12px 24px` (default), `8px 16px` (small).
- Font: `--text-body`, weight 600 (small: `--text-body-sm`).

### 5.2 Cards
- Background: white on light sections, `--color-ink-800` on dark sections.
- Border radius: `12px`.
- Shadow: `0 2px 8px rgba(0,0,0,0.06)` (light), none on dark (use 1px border instead).
- Padding: `24px` (16px below 680px of container width).

### 5.3 Navigation
- **Marketing bar:** 72px, `--color-ink-900`, sticky. Logo left, links center/left, CTAs right (Log In ghost, Start Free primary).
- **App rail:** `--color-ink-900`, full height, sticky. Labels `--color-gray-100`; hover `--color-ink-800`; the current section carries a `--color-primary` indicator and white label.
- Menus and dropdowns: white background, 12px radius, drop shadow, 150ms fade.

### 5.4 Forms
- Input height: 44px (36px in dense toolbars).
- Border: 1px `--color-gray-300`; focus ring: 2px `--color-primary-strong`.
- Border radius: `8px`.
- Label: `--text-caption`, `--color-gray-600`, positioned above field.
- Error state: border `--color-error-text`, helper text in `--color-error-text` below field.

### 5.5 Data Display (Stats/KPI Blocks)
- Big number: `--text-h3` to `--text-h1` depending on prominence, weight 700, `--color-gray-900` (or white on dark).
- Label below or above number: `--text-body-sm`, `--color-gray-600`.
- Use a 4–5 column grid for stat rows.

### 5.6 Tags / Badges
- Padding: `4px 10px`.
- Border radius: `999px` (pill).
- Background: `--color-primary-light`, text: `--color-primary-hover`, weight 600, `--text-caption`.
- Status badges use the status tint with the status text shade.

### 5.7 Tables
- Real `<table>` with scoped `<th>`. Header: `--text-caption`, `--color-gray-600`.
- Rows: `--text-body-sm`, 1px `--color-gray-100` rules, hover `--color-gray-50`.
- Numeric columns right-aligned and tabular. Wide tables scroll inside their own container.

---

## 6. Iconography & Imagery

- **Icon style:** Line icons, 1.5–2px stroke, 24x24px default size (20px in the app rail).
- **Illustration style:** Flat, abstract, geometric. Product screenshots shown inside browser-chrome frames or floating cards with soft shadows.
- **Photography:** Avoid generic stock photos; prefer UI screenshots, data visualizations, and abstract gradients.
- **Logos (customer/partner walls):** Grayscale by default, full color on hover.
- **Third-party marks keep their own colors:** Google's colors in the SERP preview and the Google connect button are not re-themed.

---

## 7. Motion

| Interaction | Duration | Easing |
|---|---|---|
| Hover state | 150ms | `ease-out` |
| Dropdown/menu open | 200ms | `ease-in-out` |
| Modal/dialog | 250ms | `cubic-bezier(0.16, 1, 0.3, 1)` |
| Page transition | 300ms | `ease-in-out` |

- Motion should always support understanding (e.g., expanding a card to reveal detail), never be purely decorative.
- Respect `prefers-reduced-motion`.

---

## 8. Accessibility Checklist

- [ ] All text meets WCAG AA contrast (4.5:1 body, 3:1 large text).
- [ ] All interactive elements have a visible focus state (2px outline, `--color-primary-strong`).
- [ ] All images/icons have descriptive `alt` text or `aria-hidden` if decorative.
- [ ] Forms have associated `<label>` elements, not placeholder-only labels.
- [ ] Color is never the only signal (pair with icon/text for success/error states).
- [ ] Minimum tap target size: 44x44px on mobile.

---

## 9. Voice & Tone

- **Confident, direct, benefit-led** headlines (e.g., "Be found everywhere search happens").
- Short sentences. Active voice. Avoid jargon in headlines; save technical detail for body copy.
- CTAs are action-first and specific: "Run Audit", "Start for free", "Book a demo". Avoid vague "Learn more" where a stronger action exists.
- In the app, PRODUCT.md's rules still hold: plain words, and every number labelled with where it came from.

---

## 10. File & Naming Conventions

```
web/app/tokens.css            every token below, plus shared component classes
web/components/dashboard/     components (PascalCase files)
```

- Use `kebab-case` for CSS tokens, `PascalCase` for component files.
- Prefix all custom CSS variables with `--` and a category (`--color-`, `--text-`, `--space-`).
- A component never types a raw hex. It names a token. Third-party marks (§6) are the one exception.

---

## 11. Notes

This system is inspired by the visual language of semrush.com (bold dark sections, orange
accent, data-forward stat blocks, clean card-based layout) as of September 2026. The
accent and specific values were adjusted where §8 required it (§13).

---

## 12. Mapping onto the app's existing token names

The code already reads a set of role names (`--accent`, `--ink`, `--ok`, …). They stay,
and now point at this system, so every component that uses them changed with no edit:

| App token | Now resolves to |
|---|---|
| `--bg` | `--color-gray-50` |
| `--surface` / `--surface-2` / `--surface-3` | `--color-white` / `--color-gray-50` / `--color-gray-100` |
| `--border` / `--border-strong` | `--color-gray-100` / `--color-gray-300` |
| `--ink` / `--ink-body` | `--color-gray-900` |
| `--ink-muted` | `--color-gray-600` |
| `--ink-faint` | `--color-gray-400` (non-text only) |
| `--accent` / `--accent-hover` | `--color-primary-strong` / `--color-primary-hover` |
| `--accent-ink` / `--accent-tint` / `--accent-border` | `--color-primary-hover` / `--color-primary-light` / `--color-primary-border` |
| `--ok` / `--warn` / `--bad` / `--info` | the `-text` shades in §2.4 |
| `--ok-fill` / `--warn-fill` / `--bad-fill` / `--info-fill` | the brand fills in §2.4 |
| `--text-xs` / `sm` / `base` / `md` / `lg` / `xl` / `2xl` / `3xl` | caption 12 / body-sm 14 / body 16 / h4 18 / h3 24 / h2 32 / h1 40 / display 56 |
| `--radius-sm` / `md` / `lg` | 8 (buttons, inputs) / 12 (cards) / 16 (modals) |

`--ink-body` resolves to gray-900, not gray-600: in the app it colours table cells and
figures, which are content rather than secondary copy. Secondary copy uses `--ink-muted`.

## 13. Accessibility corrections to the reference palette

Measured against white (`#FFFFFF`) with the WCAG relative-luminance formula:

| Pair | Ratio | Needs | Resolution |
|---|---|---|---|
| White on `#FF642D` (primary button) | 2.95:1 | 4.5:1 | Buttons and links use `--color-primary-strong` `#C2410C` (5.18:1). `#FF642D` stays for fills with no text. |
| `#FF642D` text on white | 2.95:1 | 4.5:1 | Link and accent text use `#C2410C`. |
| `#FF642D` on `#FFE8DE` | 2.51:1 | 4.5:1 | Text on primary-light uses `#9A3412`. |
| `#1DB954` success text | 2.59:1 | 4.5:1 | Text `#15803D` (5.02:1); `#1DB954` for fills. |
| `#F5A623` warning text | 2.03:1 | 4.5:1 | Text `#B45309` (5.02:1); `#F5A623` for fills. |
| `#E5484D` error text | 3.91:1 | 4.5:1 | Text `#C62828` (5.62:1); `#E5484D` for fills. |
| `#3B82F6` info text | 3.68:1 | 4.5:1 | Text `#2563EB` (5.17:1); `#3B82F6` for fills and on dark (5.06:1 on ink-900). |
| `#9AA0AA` placeholder | 2.63:1 | 4.5:1 | Placeholders use `#5C6470` (5.98:1). gray-400 is for non-text only. |
| `#EDEFF2` input border | 1.15:1 | 3:1 (WCAG 1.4.11) | Controls use `--color-gray-300` `#878E99` (3.3:1 on white, 3.11:1 on gray-50); gray-100 stays for dividers. |

## 14. Data visualisation

Charts follow the method in the `dataviz` skill. Colour is assigned by the job it does:

| Job | Colours | Rule |
|---|---|---|
| One series, or any magnitude (bars, trends, distributions) | `--chart-1` `#2A78D6` | Always blue. A second hue on a single-series chart implies a second series. |
| Categorical (link types, channels, devices) | `--chart-1` … `--chart-8`: `#2A78D6 #EB6834 #1BAF7A #EDA100 #E87BA4 #008300 #4A3AA7 #E34948` | Fixed order, never cycled. Validated on white: worst adjacent CVD ΔE 9.1, normal-vision ΔE 19.6. Slots 3–5 sit under 3:1, so those charts always carry a legend with values. |
| Pass / fail (working vs broken, new vs lost, errors vs warnings) | the status fills (§2.4) | Only where the colour means a state, and always beside a word. |
| Action and selection | `--color-primary-strong` | Never a data mark. |

- Numbers are ink (`--color-gray-900`), not the accent. A number takes a status text shade only when its colour is the point (errors, broken links).
- Tracks and gridlines: `--chart-track` / `--chart-grid`. Axes and labels: gray-600 / gray-400.
- Movement (new / up / down / lost) is neutral numbers with a glyph (`+ ▲ ▼ −`), never four colours.

## 15. Tool page template

Every tool page is the same four parts, from the shared components:

1. **Header** (`.tool-head`): the page title (`--text-h3`) and one line on what the tool reads, left-aligned. No centred hero card.
2. **Toolbar** (`.tool-bar`, `CompareInputPanel` / `SectionScanButton`): the project's domain, only the inputs the tool reads, one primary button, and the price beside it.
3. **Headline figures** (`StatStrip`): one strip divided by hairlines, not a card per number.
4. **Panels** (`Panel`, `ChartCard`, `.tool-grid`, `.chart-card--1/2/3`): rows always fill the width; a page shows one dashboard, never a second summary of the same data.

An unscanned page shows one empty state, not an empty stat strip, an empty chart card and an empty table.
Below 860px the second navigation column hides and the rail keeps switching sections.
