# Technical Debt

Running log of known debt to address. Add new items at the top.

## UI / Theming

### Inconsistent light/dark theme across the app
**Status:** Open · **Priority:** Medium

The application mixes two visual themes:
- The main app (base layout, management screens, dashboards) uses a **light**
  "metallic / off-white" theme (Tailwind, `bg-off-white`, `metallic-card`).
- The **Operations Dashboard**, **TV Wall**, and **Operations Map** ship a
  **dark** theme, and now expose a light/dark basemap toggle for the map only.

There is no single source of truth for theme tokens (colors, surfaces, text) and
no app-wide light/dark switch. This causes visual inconsistency when navigating
between operations screens and the rest of the app.

**Goal:** pick one consistent approach and apply it everywhere:
- Decide the default theme (dark or light) for the whole app.
- Introduce shared theme tokens (CSS variables / Tailwind theme) used by every
  template instead of per-page hardcoded colors.
- Optional: a single user-level light/dark toggle persisted in `localStorage`
  (and/or user profile) that applies globally, replacing the map-only basemap
  toggle.

**Affected areas:** `templates/base.html`, `templates/dashboard/operations_dashboard.html`,
`templates/dashboard/operations_tv.html`, and all management/list templates under `templates/`.
