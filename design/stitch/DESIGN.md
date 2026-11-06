---
name: Obsidian Precision Workstation
colors:
  surface: '#0f131c'
  surface-dim: '#0f131c'
  surface-bright: '#353942'
  surface-container-lowest: '#0a0e16'
  surface-container-low: '#181c24'
  surface-container: '#1c2028'
  surface-container-high: '#262a33'
  surface-container-highest: '#31353e'
  on-surface: '#dfe2ee'
  on-surface-variant: '#bcc9cd'
  inverse-surface: '#dfe2ee'
  inverse-on-surface: '#2c3039'
  outline: '#869397'
  outline-variant: '#3d494c'
  surface-tint: '#4cd7f6'
  primary: '#4cd7f6'
  on-primary: '#003640'
  primary-container: '#06b6d4'
  on-primary-container: '#00424f'
  inverse-primary: '#00687a'
  secondary: '#c0c1ff'
  on-secondary: '#1000a9'
  secondary-container: '#3131c0'
  on-secondary-container: '#b0b2ff'
  tertiary: '#4edea3'
  on-tertiary: '#003824'
  tertiary-container: '#1bbd85'
  on-tertiary-container: '#00452e'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#acedff'
  primary-fixed-dim: '#4cd7f6'
  on-primary-fixed: '#001f26'
  on-primary-fixed-variant: '#004e5c'
  secondary-fixed: '#e1e0ff'
  secondary-fixed-dim: '#c0c1ff'
  on-secondary-fixed: '#07006c'
  on-secondary-fixed-variant: '#2f2ebe'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#0f131c'
  on-background: '#dfe2ee'
  surface-variant: '#31353e'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.03em
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 12px
    letterSpacing: 0.05em
  mono-metric:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: -0.01em
  mono-code:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.5rem
  gutter-md: 0.75rem
  gutter-lg: 1rem
  margin: 0.75rem
  margin-mobile: 0.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1rem
  space-xl: 1.5rem
---

## Brand & Style

The design system establishes a high-performance creative workstation environment engineered for technical artists, 3D modelers, and technical AI creators. It merges the ergonomics of professional desktop digital content creation (DCC) software—such as Blender, Unreal Engine, and Houdini—with the real-time velocity of generative inference workflows.

### Brand Personality & Philosophy
- **Instrument-Grade Utility:** Every UI surface operates as a functional instrument. Aesthetic flair is subordinated to visual clarity, information density, and low optical fatigue during multi-hour generative sessions.
- **Controlled Luminescence:** Deep, light-absorbing obsidian foundations allow viewport renders, wireframes, and diffusion previews to claim visual dominance. Luminescent neon cyan accents act exclusively as active states, focus vectors, and precision indicators.
- **Architectural Determinism:** Visual rhythm is anchored by tight alignment grids, discrete structural borders, and standardized compact metrics. Nothing floats arbitrarily; all panels occupy explicit visual real estate.

### Design Movement: Modern Technical Workspace
The design system operates at the intersection of **Corporate / Pro-Workstation Modern** and **Precision Glass-Surface Utility**. It utilizes:
- Dark multi-tier layered slate surfaces that isolate complex canvas interactions from compute telemetry.
- Subtle 1px structural boundaries (`#243048` and `#334155`) with high contrast-to-content ratios instead of heavy dropshadows.
- Micro-radius chamfers and roundedness scale 1 (0.25rem / 4px base) to retain compact hardware feel and prevent wasted negative space in multi-pane layouts.

## Colors

> Colors are superseded by [docs/UI.md](../../docs/UI.md) §1–§4, the canonical theme specification.

The system uses a dark-mode architecture engineered for contrast stability under high-dynamic-range (HDR) viewports and prolonged visual production work.

### Palette Architecture

- **Primary (`#06B6D4` / Electric Cyan):** The primary interactive vector. Used for primary execution triggers ("Generate Mesh", "Bake Textures"), active scrubber playback heads, focused viewport handles, and active selection bounding boxes.
- **Secondary (`#6366F1` / Vibrant Cobalt):** Signifies secondary pipelines, tensor processing indicators, neural network nodes, and background compilation tasks.
- **Tertiary & Feedback Tones:**
  - **Success / Online (`#10B981` / Emerald):** VRAM buffer normal, inference complete, manifold geometry verified.
  - **Warning / Compute Throttled (`#F59E0B` / Amber):** Memory limits approaching, topology non-quad warning, high latency.
  - **Critical / Interrupted (`#F43F5E` / Rose):** CUDA out-of-memory, invalid prompt embedding, failed mesh generation.
- **Neutrals & Dark Substrates:**
  - `Canvas Canvas`: `#0B0F17` (Deep Obsidian base for inactive workspace canvas and viewport bounds).
  - `Surface Tier 1`: `#111827` (Panel containers, inspector sidebars, node graph backgrounds).
  - `Surface Tier 2`: `#1A2234` (Dock headers, input fields, control groups, tab trays).
  - `Surface Tier 3`: `#222D42` (Hover states, toggle track backgrounds, modal popovers).
  - `Border Rest`: `#243048` (Standard structural separation).
  - `Border Highlight`: `#334155` (Hovered frames, active panel perimeter).
  - `Text Primary`: `#F8FAFC` (High legibility display data and active values).
  - `Text Muted`: `#94A3B8` (Labels, property headers, unselected parameters).
  - `Text Ghost`: `#64748B` (Keyboard shortcuts, inactive dimensions, units).

### Application Rules
1. Never use saturated cyan fills for passive containers or large cards; cyan is strictly an operational catalyst.
2. Status indicators must pair luminous color chips with explicit numerical or textual states for accessibility and rapid diagnostic recognition.

## Typography

The typographic hierarchy prioritizes dense horizontal efficiency and scanning speed. 

### Font Assignment & Mechanics
- **Interface & Metrics Font (Inter):** Leveraged for all display, contextual body, and parametric data displays. Inter's optical geometry, robust tall x-height, and open counters maintain distinct glyph separation in sub-12px parameter sheets.
- **Tabular Figures & Tracking:** All numeric displays (vertices, face counts, GPU clock, tensor inference percentages, step counts) must employ tabular numbers (`tnum`) and slashed zero (`zero`) OpenType features to preserve strict vertical alignment within property columns.
- **Micro-Scale Legibility:** Labels below 12px utilize slightly expanded tracking (+0.03em to +0.05em) and uppercase transformation where context dictates fast visual separation (e.g., coordinate axes `X`, `Y`, `Z`, or texture slots `ALBEDO`, `NORMAL`, `ROUGHNESS`).

## Layout & Spacing

The layout model reflects a high-density, multi-panel workstation architecture capable of continuous resizing, pane docking, and flexible split-screen orchestration.

### Workstation Layout Architecture
- **Panel Grid Structure:** Instead of conventional fluid marketing grids, the interface is governed by an application-shell layout:
  - Top Utility Header: 40px fixed height.
  - Left Tool Shelf: 48px fixed or 240px collapsable navigation dock.
  - Central Multi-Viewport: Dynamically stretched primary work area with 8px internal tool gutters.
  - Right Property Inspector / Parameter Stack: Fixed width (320px–420px) scrollable utility zone.
  - Bottom Timeline & Telemetry Tray: 200px resizable drawer.
- **Density Principles:**
  - Component spacing relies strictly on a 4px/8px incremental rhythm (`space-xs` = 4px, `space-sm` = 8px, `space-md` = 12px).
  - Gutters between docked inspector panels are constrained to `gutter` (8px) or `gutter-md` (12px) to maximize real-estate efficiency.
- **Responsive & Dynamic Form Factors:**
  - **Desktop (1440px+):** Full multi-pane arrangement. Viewport, node graph, and parameter decks remain concurrently mounted.
  - **Compact Desktop / Tablet Landscape (1024px – 1439px):** Node graphs collapse into drawer overlays. Inspector dock converts to an accordion stack.
  - **Mobile / Review Companion (<1024px):** Layout switches from desktop workstation to an asset approval feed. Single-column view with sheet-based overlays for parameters; complex 3D canvas expands full-bleed with floating gesture pads.

## Elevation & Depth

Visual hierarchy within the workstation is maintained through high-precision structural boundaries, subtle surface darkening, and localized luminescence, avoiding heavy, diffuse shadows.

### Elevation Hierarchy
1. **Level 0 (Canvas Base - `#0B0F17`):** The foundational viewport floor. Carries infinite canvas grids, 3D transform widgets, and background environment maps.
2. **Level 1 (Docked Workstation Panels - `#111827`):** Anchored sidebars, header shelves, and attribute editors. Separated from Level 0 via 1px crisp borders (`#243048`).
3. **Level 2 (In-Panel Controls & Cards - `#1A2234`):** Input containers, nested fold-outs, collapsible property rollouts, and preview tiles. Separated via `#334155` border traces.
4. **Level 3 (Floating HUDs & Viewport Overlays - `#111827` with 85% opacity & 12px backdrop blur):** Viewport orientation gizmos, transform coordinates, and mini-stats. Uses `backdrop-filter: blur(12px)` with a 1px border of `rgba(6, 182, 212, 0.25)` to signify an active interactive overlay.
5. **Level 4 (Modals & Command Palettes - `#1A2234`):** Command-K terminal, mesh export configurations, and shader graph editors. Elevated with a dark ambient perimeter: `0 16px 36px -8px rgba(0, 0, 0, 0.65), 0 0 0 1px #334155`.

### Focus & Active Luminescence
Active panels and focused inputs reject conventional diffuse drop-shadows. Instead, they activate a 1px boundary of `#06B6D4` paired with an internal edge glow: `box-shadow: inset 0 0 0 1px #06B6D4, 0 0 8px -2px rgba(6, 182, 212, 0.4)`.

## Shapes

The design system employs a disciplined, micro-radius shape framework (`roundedness: 1`). Large circular fillets are prohibited in operational tooling as they degrade usable corner space for multi-attribute fields and nested panel headers.

### Shape Scales & Usage
- **Base Components (0.25rem / 4px):** Applied to inputs, buttons, segmented toggles, tab items, dropdown menus, and numeric steppers. Retains a crisp industrial character.
- **Panels & Overlays (0.5rem / 8px):** Applied to floating HUDs, popover flyouts, viewport containers, and modal window perimeters.
- **Pill Badges & Indicator Dots (Full / 9999px):** Strictly reserved for micro-status indicators (e.g., live streaming dots, active node state tags) to create instant visual contrast against geometric tool controls.

## Components

### Buttons & Interactive Triggers
- **Primary Workstation Trigger:** Cyan background (`#06B6D4`), dark text (`#0B0F17`, font-weight 600), 4px border radius, 32px height. Hover brings high brightness (`#22D3EE`) with micro-glow (`box-shadow: 0 0 12px rgba(6, 182, 212, 0.35)`). Active state depresses to `scale(0.99)`.
- **Secondary Tool Trigger:** Surface background (`#1A2234`), 1px border (`#243048`), text primary (`#F8FAFC`). Hover updates border to `#334155` and surface to `#222D42`.
- **Ghost / Tool Bar Icon Button:** Transparent background, muted text (`#94A3B8`), 28px x 28px square. Active state highlights with a 1px cyan border and subtle cyan tint (`rgba(6, 182, 212, 0.1)`).

### Input Fields & Scrubbers
- **Numeric Property Field:** 28px height, surface `#111827`, border 1px `#243048`, text `#F8FAFC`. Label sits anchored to the left in `#94A3B8`, value aligned to the right in tabular format. Supports horizontal click-and-drag scrubbing: cursor turns to `ew-resize`, and a micro-line cyan scrubber bar renders beneath the active value.
- **Text & Prompt Input:** Surface `#111827`, inset border 1px `#243048`, typography `body-sm`. Focused state transitions border to `#06B6D4` with 0.5s ease.

### Chips & Badges
- **Hardware Telemetry Badge:** Compact 20px height, background `rgba(17, 24, 39, 0.8)`, border 1px `#243048`. Features a leading 6px colored indicator dot (e.g., emerald for CUDA ready, amber for thermal limit). Typography `label-sm`.
- **Filter & Tag Chip:** Removable pill badge with dark slate background (`#1A2234`), border `#334155`. Selected state transitions to `#6366F1` text with subtle indigo glow.

### Checkboxes, Radios & Switches
- **Workstation Checkbox:** 14px x 14px square, 2px border radius, border 1px `#334155`, background `#111827`. Checked state triggers `#06B6D4` fill with obsidian checkmark glyph.
- **Precision Toggle Switch:** 28px width, 16px height track with `#1A2234` fill and 1px `#243048` border. The thumb is an 10px circular node that slides with a 150ms spring curve, illuminating from `#64748B` (inactive) to `#06B6D4` (active).

### Parameter Cards & Inspector Rollouts
- **Inspector Section Container:** Flat `#111827` surface with a 1px bottom border `#243048`.
- **Rollout Header:** 32px height, collapsible chevron glyph, title set in `headline-sm` with muted property summary counters right-aligned. Hover states transition header background to `rgba(255, 255, 255, 0.02)`.

### Viewport Overlays & Mini-Toolbars
- Floating HUD tool strips inside 3D viewport canvas. Built with semi-translucent slate (`#111827` at 90%), 12px blur, 4px border radius, 1px perimeter border `#334155`. Tool groupings separated by 12px vertical hairline dividers (`#243048`).