---
name: wf-dashboard
colors:
  surface: '#0b1326'
  surface-dim: '#0b1326'
  surface-bright: '#31394d'
  surface-container-lowest: '#060e20'
  surface-container-low: '#131b2e'
  surface-container: '#171f33'
  surface-container-high: '#222a3d'
  surface-container-highest: '#2d3449'
  on-surface: '#dae2fd'
  on-surface-variant: '#bdc8d1'
  inverse-surface: '#dae2fd'
  inverse-on-surface: '#283044'
  outline: '#87929a'
  outline-variant: '#3e484f'
  surface-tint: '#7bd0ff'
  primary: '#8ed5ff'
  on-primary: '#00354a'
  primary-container: '#38bdf8'
  on-primary-container: '#004965'
  inverse-primary: '#00668a'
  secondary: '#b9c8de'
  on-secondary: '#233143'
  secondary-container: '#39485a'
  on-secondary-container: '#a7b6cc'
  tertiary: '#ffc176'
  on-tertiary: '#472a00'
  tertiary-container: '#f1a02b'
  on-tertiary-container: '#613b00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#c4e7ff'
  primary-fixed-dim: '#7bd0ff'
  on-primary-fixed: '#001e2c'
  on-primary-fixed-variant: '#004c69'
  secondary-fixed: '#d4e4fa'
  secondary-fixed-dim: '#b9c8de'
  on-secondary-fixed: '#0d1c2d'
  on-secondary-fixed-variant: '#39485a'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb960'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#0b1326'
  on-background: '#dae2fd'
  surface-variant: '#2d3449'
typography:
  headline-sm:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  mono-base:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  mono-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.02em
  label-caps:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 12px
    letterSpacing: 0.05em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  unit: 4px
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  gutter: 1px
  panel-padding: 12px
---

## Brand & Style

The design system is centered on an **Operator Console** aesthetic: a high-density, utility-first environment built for technical precision. The brand personality is clinical, efficient, and transparent. It is designed for developers and system administrators who require a "command center" view of their workflows without the distraction of decorative ornamentation.

The style leans heavily into **Technical Minimalism**. It prioritizes information density and structural clarity over visual flair. The UI utilizes a "Developer Tool" vibe—characterized by strict grid alignment, monospaced data sets, and a high-contrast functional palette. There are no gradients, soft shadows, or rounded corners beyond functional necessity; every pixel serves a specific purpose in reporting state or facilitating action.

## Colors

The palette is optimized for long-duration monitoring in low-light environments. The foundation is a deep **Slate/Navy** stack, providing a low-strain background for high-contrast foreground elements.

- **Primary:** A sharp "Electric Blue" used sparingly for active states and primary actions.
- **Surface Tiers:** `bg_base` for the application canvas, `bg_surface` for panels and sidebars, and `bg_element` for nested components like code blocks or input fields.
- **Semantic System:** Status colors are high-chroma to ensure immediate recognition. Success (Green), Error (Red), Warning (Amber), and Info (Blue) must maintain a 4.5:1 contrast ratio against the background for accessibility.
- **Borders:** Use a consistent `#334155` (Slate-700) for structural division to maintain the "grid-like" feel of a terminal.

## Typography

Typography in this design system is split between **Functional Sans-Serif** (Inter) for navigation and controls, and **Technical Monospace** (JetBrains Mono) for data, logs, and git states.

- **Scale:** Small font sizes (11px–14px) are utilized to achieve high information density. 
- **Monospace Usage:** Any value that represents a hash, path, git branch, or log output must use `mono-base` or `mono-sm`. This ensures character alignment in data-heavy views.
- **Labels:** Uppercase `label-caps` is used for section headers and table column titles to provide visual structure without requiring large font sizes.
- **Contrast:** Default text uses a high-white color (#F8FAFC), while secondary metadata uses Slate-400 to create a clear hierarchy.

## Layout & Spacing

This design system uses a **Fixed-Grid / Panel-based** layout. The screen is divided into functional quadrants or panels, separated by 1px borders rather than wide gutters. 

- **Density:** Padding is tight (typically 8px or 12px) to maximize the visible data on screen.
- **The 1px Rule:** Use 1px borders (#334155) to separate logical sections. This mimics the appearance of a TUI (Terminal User Interface).
- **Responsive Behavior:** On smaller screens, panels stack vertically. On desktop, sidebars are fixed-width (typically 240px–280px) while the main log/table area expands to fill the remaining viewport.
- **Alignment:** All elements must align to the 4px baseline grid.

## Elevation & Depth

This system avoids ambient shadows and skeuomorphism. Depth is achieved through **Tonal Layering** and **Hard Borders**.

- **Z-Index:** Content is conceptually "flat." When a modal or popover is required, it uses a solid 1px border of a lighter slate and a slight background darken of the layer beneath.
- **Active State:** Focus and active states are indicated by 1px solid outlines in the `primary_color` or by a subtle background shift to `bg_element`. 
- **Interactions:** Hover states on rows or buttons should result in a discrete background color change (e.g., from `bg_surface` to `bg_element`) rather than any "lift" effect.

## Shapes

The design system uses a "Soft" roundedness level (0.25rem / 4px) but applies it selectively. 

- **Panels/Layout:** These should remain perfectly sharp (0px) to maintain the structural grid feel.
- **Controls/Chips:** Use 4px (rounded) for buttons, input fields, and status badges to provide a subtle visual hint that they are interactive elements.
- **Code Blocks:** Use 4px for the containers of log outputs to visually group the code separate from the UI frame.

## Components

### Status Chips (Git States)
- **Design:** Compact, uppercase `mono-sm` text. 
- **Variants:** 
  - `Clean`: Subtle green border, green text, no background fill.
  - `Dirty/Ahead`: Solid Amber background, black text.
  - `Error`: Solid Red background, white text.
- **Sizing:** Fixed height (20px), minimal horizontal padding (6px).

### Provider Status Strip (Findings)
- **Design:** One line under the toolbar, `mono-sm`, `PROVIDERS` label in `label-caps`, one `name status` pair per external source read from `findings.json`'s `providers` map.
- **Variants:** green `ok:` · red `failed:` · amber everything else (`skipped:`, `partial:`, `timed out:`, `no field data:`).
- **Amber is about the measurement, not the site.** It means this cycle's finding count is incomplete, which no count on the screen can express on its own.
- **Wraps, never scrolls.** With `overflow-x-auto` the fourth provider fell off the right edge, and a skip pushed off-screen defeats the strip's only purpose.
- **The empty case is the loud one.** No providers at all renders a full-width amber sentence, because "0 findings" and "0 findings from sources nobody ran" are the same table otherwise.

### Compact Tables
- **Styling:** No outer border, 1px horizontal dividers only.
- **Cells:** Use `mono-base` for data columns. The first column (ID or Name) is typically `primary_color`.
- **Hover:** Highlight the entire row in `bg_element`.

### Log Viewer / Code Blocks
- **Styling:** `bg_base` background (darker than the UI panels).
- **Text:** `mono-base` with syntax highlighting for common config formats (YAML/JSON/Bash).
- **Gutter:** Include a line-number gutter on the left for log correlation.

### Form Controls (Config Editor)
- **Inputs:** Dark background (`bg_element`), 1px Slate-600 border. Focus state is a 1px `primary_color` border.
- **Labels:** Positioned above the input using `label-caps`.
- **Buttons:** Primary buttons are solid `primary_color` with black text. Secondary buttons are outline-only with `secondary_color` text.

### Header/Brand Mark
- **Styling:** The `wf-dashboard` mark is rendered in `Inter Bold`, all-lowercase, with tight tracking. It should look like a typed command.