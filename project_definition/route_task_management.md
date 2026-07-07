# Route & Task Management

This document describes the corporate route/task model introduced for the
Gjakova municipal pivot. See `corporate_language_glossary.md` for terminology.

## Concept

- A **Team** is given a **daily Route** — one Route per weekday (Mon–Fri for
  collection; cleaning teams use an always-on route with no weekday).
- A **Route** contains N **Streets** (`locations.Building`). Each street carries
  its geolocated dumpsters (**Service Points**, `locations.Room` with
  `space_type='dumpster'`).
- For reporting and efficient tracking, the backend generates **one Task per
  dumpster** (`DailyCleaningTask`) for each scheduled day. Tasks are a backend
  artefact — operators interact with routes/streets on the map, not raw tasks.

## Data model (`accounts/models.py`)

- `Route`: `team`, `weekday` (0=Mon..6=Sun, nullable = always-on), `streets`
  (M2M to `Building` through `RouteStreet`), `compounds` (Zones, derived from the
  streets), `priority`, `is_active`. Unique per `(team, weekday)`.
- `RouteStreet`: ordered membership of a Street in a Route (`order`).
- `PlanGenerationConfig` (one per Site/Camp): `cadence` (`weekly` | `biweekly`),
  `anchor_date` (parity reference for bi-weekly), `last_generated_on`,
  `is_active`.

## Task generation

- Service: `accounts/task_generation.py::generate_tasks_from_routes(camp, start, end)`.
  For each active route whose `weekday` matches a date in range, it creates a
  `DailyCleaningTask` per active dumpster on each street, assigned to the route's
  team. Idempotent (`get_or_create` on room + date + index). It also keeps
  `Room.collection_weekday` in sync for the map.
- Command: `python manage.py generate_route_tasks [--camp CODE] [--days N] [--start YYYY-MM-DD] [--force]`.
  Horizon defaults to 7 days (weekly) or 14 days (bi-weekly). Bi-weekly weeks are
  skipped unless `--force` or it is a generation week.
- Schedule: a cron job runs the command **every Sunday at 00:01**
  (`docker/cron/Dockerfile`, entry `1 0 * * 0`). Management chooses the cadence
  in the UI (Team Management → Plan Generation) and can also **Generate now**.

## Management UI (Field Manager / Operations Manager)

- **Routes** (`accounts:route_list`): lists every daily route with weekday,
  street count and dumpster count. Create/edit builds a route from Team +
  weekday + ordered streets; the zone is derived from the chosen streets.
- **Plan Generation** (`accounts:plan_config`): cadence settings + manual
  "Generate tasks now".

## Operations views

`dashboard/operations_views.py` derives each team's daily streets and dumpsters
from `Route(team, weekday).streets` (collection) and `Route.compounds`
(cleaning). The date selector keeps its semantics: today uses live task state,
past days are treated as serviced, future days are planned only.
