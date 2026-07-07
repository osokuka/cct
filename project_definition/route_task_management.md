# Route & Task Management

This document describes the route/task model for the Gjakova municipal pivot.
See `corporate_language_glossary.md` for terminology.

## Current approach (zone-centric)

Routes are **no longer created or managed as objects**. Instead, scheduling is
driven entirely by the **Zone**. Every Zone is assigned:

- an **assigned team** (`assigned_team`), and
- a **collection weekday** (`collection_weekday`, 0=Mon .. 6=Sun).

There are two kinds of zone (`Compound.zone_type`):

1. **Collection zone** (`zone_type='collection'`, default) — a city zone that
   contains **dumpsters** (`Room` with `space_type='dumpster'`). It is measured
   by **number of dumpsters** and generates **one task per dumpster** on the
   zone's day.
2. **Public area** (`zone_type='public_area'`) — an **independent zone** (park,
   cemetery, school yard, plaza, …) measured by **surface area (m²)** instead of
   dumpsters. It generates **one cleaning task per scheduled day** for the whole
   area. Public areas **do not inherit** anything from collection zones.

A **"daily route" is a derived view**, not a stored record — simply the
combination **(Zone × collection day × assigned team)**. The UI shows this so
operators can read "on Thursday, Ekipa 1 services Zona 1", but nothing is
persisted — there is **no Route to create, edit, or manage**.

The legacy `Route` / `RouteStreet` models still exist in `accounts/models.py`
but are **not part of this workflow**. Do not create routes for scheduling; use
zone assignments.

### Public-area representative Service Point

A `DailyCleaningTask` requires a `Room`. For a public-area zone, the backend
auto-maintains a **single representative Service Point** (`Room` with
`space_type='public_area'`, code `<zone-code>-AREA`) at the boundary centroid,
carrying the zone's area (m²) as its `actual_sqm`. `Compound.ensure_area_room()`
creates/updates it on zone save, area measurement, and generation. Operators do
not manage it directly.

## Where scheduling is set

On the **Zone edit form** (`locations:compound_edit`) under
"Collection assignment":

- **Assigned team** — the team responsible for the whole zone.
- **Collection day** — the weekday the zone is serviced.

Shifts remain a single standard **08:00–17:00** per Site (a backend detail); the
field manager owns the time, not the zone.

Saving a zone also:

- syncs `collection_weekday` onto the zone's dumpsters, and
- (re)computes the zone **surface area** (`area_sqm`) from the drawn boundary
  polygon (see "Area measurement").

## Task generation (backend artefact)

For reporting/tracking, the backend still generates **one Task per Service Point
per scheduled day** (`DailyCleaningTask`). Generation is **zone-driven**:

- `accounts/task_generation.py`
  - `generate_tasks_for_zone(zone, start, end)` — for a single zone that has
    **both** a team and a collection day, on every matching weekday in range:
    a **collection zone** creates one `DailyCleaningTask` per active dumpster; a
    **public-area zone** creates one task for its representative area Service
    Point (SLA credit = zone m²). Idempotent.
  - `generate_tasks_from_zones(start, end, camps=None)` — runs the above for all
    schedulable zones and reports counts, including **orphan Service Points that
    are skipped**.
- **Orphans are never generated**: a Service Point with no zone, or in a zone
  without a team or without a collection day, produces no tasks.

The old `generate_tasks_from_routes` remains for backward compatibility but is
not used by the current workflow.

## Management UI

- **Recurring Tasks** (`accounts:task_assignment_dashboard`,
  `/accounts/task-assignment/`): lists every dumpster as a recurring task with
  zone, street, team, day, type, GPS and client. Admin/manager can:
  - **Generate only**, **Clear & Generate**, or **Clear all** collection tasks,
  - set a **horizon (days)**,
  - see a readiness strip (schedulable vs orphan Service Points, existing tasks).
  - Backend: `manage_recurring_tasks` (`accounts:manage_recurring_tasks`).
- **Zone detail** (`locations:compound_view`): shows the zone's boundary, area,
  streets, dumpsters, and its (team × day) schedule, plus
  **"Measure area"** and **"Measure & generate tasks"** actions
  (`locations:zone_measure_area`).

## Area measurement

- `locations.geo.polygon_area_sqm(ring)` computes an approximate area (m²) from a
  boundary ring using a local equirectangular projection + shoelace formula.
- `Compound.compute_area_sqm()` / `area_sqm` / `area_hectares` expose it. Area is
  auto-computed on zone save and on demand from the zone detail page.

## Operations views

`dashboard/operations_views.py` derives what shows per day from **zone
assignments**, not routes:

- **Dumpsters** appear on the selected date when their zone's collection day
  matches; the responsible team is the zone's `assigned_team`.
- **Public areas** follow their zone's team; scheduled zones show **only on their
  assigned weekday**, unscheduled zones show daily.
- Date-selector semantics are unchanged: today uses live task state, past days
  are treated as serviced, future days are planned only.
