# Gjakova Municipality Pivot — Garbage Collection & Public-Area Cleaning

**Status:** Design / Documentation
**Last Updated:** July 7, 2026
**Applies to branch:** `feature/garbage-collection-pivot`

---

## 1. Purpose

This document re-targets the ARCOM / CCT tracker away from the NATO camp domain and
onto the **Municipality of Gjakova (Komuna e Gjakovës)** in western Kosovo. The
system now serves two parallel municipal service streams:

1. **Garbage collection (RFID / count-based)** — servicing dumpsters and
   containers along **streets and city blocks** grouped into **collection routes**.
2. **Public-area cleaning (SQM / area-based)** — cleaning **parks, city-center
   plazas, and school yards** measured in square metres against an SLA.

The underlying data model (`Camp → Compound → Building → Floor → Room`, `Team`,
`Route`, `DailyCleaningTask`, RFID/barcode scans) is **kept intact**; only its
*semantics, seed data, and labels* are re-interpreted for Gjakova.

---

## 2. Gjakova context (reference facts)

- Municipality of Gjakova, Gjakova District, Dukagjin Valley (between Prizren and Peja).
- Municipality population ≈ 94,556; city ≈ 40,827 (2011 census).
- Crossed by the **Krena river**; historic core is the **Grand Bazaar
  (Çarshia e Madhe)**, ~1 km long, linked to the centre by the **Islam-Beg Bridge**.
- Established neighbourhoods / urban zones (from the Municipal Zoning Plan
  *HARTA ZONALE 2024–2032* and informal-settlement studies): Qendra/Old Town,
  Dardania (Perëndimore), Ali Ibra, Kolonia, Piskota, Orize, Senjak, Çarapatok,
  Brekoc, Qerim, Zona e Spitalit (hospital zone), Jugu (south).
- Main streets: **Nëna Terezë**, **Mark Malota**, Bajram Curri, Skënderbeu,
  Musa Zajmi, Naum Veqilharxhi, Mbretëresha Teutë, Tirana, Fehmi Agani,
  Sadik Stavileci, Tivari, Rruga e Katolikëve.
- Public / green spaces: **Parku i Qytetit** (City Park), **Parku i Shkugëzës**
  (pine forest, ~3 km out, walking/bike trails), **Kodra e Çabratit** (Çabrati Hill),
  Krena riverbank promenade.
- Education: **University of Gjakova "Fehmi Agani"**, school "Mustafa Bakija", plus
  numerous primary/secondary school yards.

---

### Operations focus area (real OpenStreetMap geometry)

The demo now uses **real street geometry** from OpenStreetMap instead of hand-placed
points. Garbage collection concentrates on a **1.5 km-radius zone** around
**`42.37093, 20.43539`**, while **public-area cleaning covers the whole town**.

Data pipeline:

1. `locations/management/commands/data/build_gjakova_osm.py` reads two Overpass
   exports — drivable streets (`highway` = residential / living_street / service /
   unclassified / tertiary / secondary / primary, `around:1500`) and public areas
   (parks, school yards, squares town-wide) — and writes a compact
   `data/gjakova_osm.json` containing:
   - **streets[]** with dumpster coordinates pre-spaced **~80 m** apart along the
     real polylines (only points inside the 1.5 km zone, de-duplicated within 45 m), and
   - **public_areas[]** with centroid + approximate area (m²).
2. `seed_gjakova` consumes that JSON. It wipes the previous GJ seed, splits the zone
   into **4 collection sectors** (quadrants `ZNE/ZNW/ZSE/ZSW`) for routing, creates a
   `Building` per street, and places every dumpster (`Room`) with a rotating
   `CollectionClient` payment status. Public areas are assigned to the sector matching
   their direction so cleaning can be split North/South.

Current dataset: **206 streets → 896 dumpsters** and **68 town-wide public areas**.

### Weekly collection plan (3 teams, ≤5 streets/team/day, Mon–Fri)

The builder computes a **Mon–Fri plan** stored in the dataset:

- Streets are split into **3 contiguous, non-overlapping angular zones** (Z1/Z2/Z3).
  Because zones are angular slices, **collection teams never cross each other's roads**.
- Within a zone, streets are grouped by **vicinity** (greedy nearest-neighbour) into
  daily clusters of **≤5 streets**, and one cluster is assigned to each weekday
  (`Room.collection_weekday`, 0=Mon..4=Fri). So each team works ~5 adjacent streets a
  day; on any given day the three teams work three separate neighbourhoods. Streets
  beyond the 5-day plan are left **unscheduled** (not shown/tasked this week).
- Each street stores its **real road geometry** (`Building.geo_polyline`, GeoJSON
  MultiLineString) so routes follow the street layout and never cut across properties
  that have no street.

`seed_operations` wires **5 teams**: 3 collection (one per zone Z1/Z2/Z3) and 2 cleaning
(public areas, split North/South → PUBN/PUBS). Today's tasks are created **only for the
current weekday's scheduled streets** (collection) plus all public areas (cleaning).

### Operations map behaviour (today only, dots not lines)

- The operations map/TV show **only today's routes** — the ~15 scheduled streets
  (3 teams × 5) for the current weekday — instead of the full 896-dumpster inventory.
- **Dumpster dots** are coloured by collection status: **green = collected**,
  **amber = awaiting collection**, **red = not collected** (unpaid/overdue — passed but
  skipped). Every dumpster popup shows the anonymized client id, location (lat/lng),
  paid/not-paid, and last-collected time.
- **Route lines are hidden by default.** Selecting a collection team draws only that
  team's **today** street lines; selecting one street from the team's list draws only
  that street and zooms to it.
- Clicking a team lists its **today's streets one by one** with `collected/total`
  dumpster counts. **Cleaning teams show no lines** — their public areas simply turn
  **green when cleaned**.
- The full-inventory field map (`/map/`) still shows every dumpster for payment/lookup.

To move/widen the focus: adjust the centre/radius/spacing/teams/cap in
`build_gjakova_osm.py`, re-fetch the Overpass exports, re-run the builder, then
`seed_gjakova` + `seed_operations`. Keep `GJAKOVA_CENTER` (`dashboard/map_views.py`) in
sync with the zone centre.

## 3. Domain remapping

The physical hierarchy stays the same in the database; its meaning changes:

| Model (unchanged) | NATO-camp meaning (old) | Gjakova meaning (new) | Example |
|---|---|---|---|
| `Camp` | Military camp | **Municipality** | Komuna e Gjakovës (`GJ`) |
| `Compound` | Compound | **Neighbourhood / City block (Lagje / Zonë)** | Qendra (`QEN`), Dardania (`DAR`) |
| `Building` | Building | **Street (Rrugë)** | Rr. "Nëna Terezë" (`NTE`) |
| `Floor` | Floor | **Street segment / block section** | Segment A (nr. 1–45) |
| `Room` | Room/area | **Service point** — a dumpster OR a public area | Kontejner K-007 / Parku i Qytetit |
| `Team` (`team_type`) | Cleaning team | **Collection team** or **Cleaning team** | "Ekipi Gjelbër 1" |
| `Route` | Route (team → compounds) | **Collection / cleaning route** (team → neighbourhoods) | "Ruta Qendër – Mëngjes" |
| `DailyCleaningTask` | Daily cleaning task | **Daily collection or cleaning task** | Bosh. kontejneri K-007, 07:00 |
| `ScanEvent` | Barcode scan | **RFID/barcode scan** at a dumpster / area | tag `GJ-QEN-NTE-K007` |

> **Rule of thumb:** a `Room` with `space_type = 'dumpster'` is a **collection
> point** (count/RFID). Any area-based `space_type` (park, city center, school yard,
> …) is a **public-area cleaning site** (SQM/SLA). This split already drives the
> dynamic dashboard KPIs (`has_cleaning_teams` / `has_collection_teams`).

---

## 4. Two service streams

### 4.1 Garbage collection (count / RFID)

- Service points = `Room(space_type='dumpster')`, one per physical dumpster/container.
- Each dumpster carries an RFID tag / barcode; a `ScanEvent` on the round marks the
  matching `DailyCleaningTask` as `done` (1.0 "collection" credit, not SQM).
- Serviced by `Team(team_type='collection')` along a `Route` covering one or more
  neighbourhoods, ordered by street.
- KPI: **dumpsters collected / planned** (see `collection_stats` in
  `dashboard/views.py`).

### 4.2 Public-area cleaning (SQM / SLA)

- Service points = area `Room`s located in parks, city-center plazas, school yards.
- Measured by `actual_sqm` / `weekly_required_sqm` / `sla_credit_sqm`, exactly like
  the original SQM SLA engine.
- Serviced by `Team(team_type='cleaning')`.
- KPI: **SQM completed / required** (see `cleaning_stats` in `dashboard/views.py`).

---

## 5. Neighbourhoods (Compounds) — reference table

| Code | Neighbourhood (Lagje / Zonë) | Primary stream(s) | Notes |
|---|---|---|---|
| `QEN` | Qendra / Old Town (Qarshia e Madhe) | Collection + Cleaning | Bazaar, plazas, riverbank |
| `DAR` | Dardania (Perëndimore) | Collection | Residential |
| `ALI` | Ali Ibra | Collection | Residential complex |
| `KOL` | Kolonia | Collection | Dense residential |
| `PIS` | Piskota | Collection | North of town |
| `ORI` | Orize | Collection | Residential (Orize 1–8) |
| `SEN` | Senjak | Collection | Residential |
| `CAR` | Çarapatok | Collection | Residential |
| `BRE` | Brekoc | Collection | Peripheral settlement |
| `QER` | Qerim | Collection | Northern locality |
| `SPI` | Zona e Spitalit (Hospital zone) | Collection + Cleaning | High-priority, daily |
| `JUG` | Jugu (South) | Collection | Skënderbeu/Musa Zajmi corridor |

---

## 6. Streets & city blocks (Buildings) — collection layout

Streets are modelled as `Building` rows under their neighbourhood. `Floor` is used
as an optional **street segment** (e.g. by house-number range or block face) so a
long street can be split across rounds.

| Neighbourhood | Street (Building) | Street code | Segments (Floors) |
|---|---|---|---|
| `QEN` | Rr. "Nëna Terezë" | `NTE` | A (1–45), B (46–end) |
| `QEN` | Rr. "Mark Malota" | `MMA` | A, B |
| `QEN` | Rr. "Mbretëresha Teutë" | `MTE` | A |
| `QEN` | Qarshia e Madhe (Grand Bazaar) | `QAR` | A |
| `DAR` | Rr. "Tirana" | `TIR` | A, B |
| `DAR` | Rr. "Bajram Curri" | `BAC` | A |
| `ALI` | Rr. "Fehmi Agani" | `FAG` | A, B |
| `ALI` | Rr. "Sadik Stavileci" | `SST` | A |
| `JUG` | Rr. "Skënderbeu" | `SKE` | A, B |
| `JUG` | Rr. "Musa Zajmi" | `MZA` | A |
| `SPI` | Rr. e Spitalit | `SPT` | A |

> Segments (`Floor`) are optional; small streets can use a single default segment.

---

## 7. Collection points (dumpsters) & coding scheme

Each dumpster is a `Room(space_type='dumpster')`. On save, the model already
auto-fills `square_meters/actual_sqm = 1.0` and derives caps from frequency, so
dumpsters bypass SQM validation.

**Barcode / RFID tag format** (built by `cct/utils.generate_barcode_data`, then
normalised to `MUNI-NBHD-STREET-POINT`):

```
GJ-QEN-NTE-K007
│  │   │   └── Point code: K = Kontejner (dumpster), 3-digit sequence
│  │   └────── Street code (Building), 3 chars → normalised to B### in barcode
│  └────────── Neighbourhood code (Compound)
└───────────── Municipality code (Camp) = GJ
```

Example collection points:

| Tag | Street | Frequency/week | Type |
|---|---|---|---|
| `GJ-QEN-NTE-K001` | Nëna Terezë, seg. A | 7 | 1100 L dumpster |
| `GJ-QEN-NTE-K002` | Nëna Terezë, seg. A | 7 | 1100 L dumpster |
| `GJ-QEN-QAR-K010` | Grand Bazaar | 7 | Bazaar bin cluster |
| `GJ-SPI-SPT-K001` | Hospital zone | 7 | Clinical-adjacent |
| `GJ-DAR-TIR-K003` | Tirana, seg. B | 3 | Residential |

---

## 8. Public-area SQM sites (parks, city centers, school yards)

Public-area cleaning focuses on **parks, city-center public places, and school
yards**. These are area `Room`s with real `actual_sqm` and an SLA frequency.

| Site (Room) | Neighbourhood | Suggested `space_type` | Indicative SQM | Freq/week |
|---|---|---|---|---|
| Parku i Qytetit (City Park) | `QEN` | `park` | 18,000 | 7 |
| Parku i Shkugëzës | `QEN` | `park` | 40,000 | 3 |
| Kodra e Çabratit (recreation) | `QEN` | `park` | 12,000 | 2 |
| Sheshi "Nënë Tereza" (central plaza) | `QEN` | `city_center` | 6,500 | 7 |
| Riverbank promenade (Krena) | `QEN` | `city_center` | 9,000 | 5 |
| Grand Bazaar walkway | `QEN` | `city_center` | 8,000 | 7 |
| Oborri i shkollës "Mustafa Bakija" | `QEN` | `school_yard` | 3,200 | 5 |
| Kampusi "Fehmi Agani" (grounds) | `ALI` | `school_yard` | 5,000 | 3 |
| Oborr shkolle – Dardania | `DAR` | `school_yard` | 2,800 | 5 |

### 8.1 Required model adjustment (public-area space types)

`Room.SPACE_TYPE_CHOICES` currently has no public-area categories. To model the
focus areas cleanly, add:

```python
('park', 'Park / Green Space'),
('city_center', 'City Center / Public Plaza'),
('school_yard', 'School Yard'),
```

These are ordinary SQM space types (they keep the standard area validation, unlike
`dumpster`). A data migration can also relabel any legacy `front_yard`/`garage`
choices if needed. **Not yet implemented** — see §12.

---

## 9. Teams & routes

### 9.1 Collection teams (`team_type='collection'`)

| Team | Shift | Route (neighbourhoods) | Streets covered |
|---|---|---|---|
| Ekipi i Grumbullimit 1 | 06:00–14:00 | Ruta Qendër | QEN (NTE, MMA, QAR) |
| Ekipi i Grumbullimit 2 | 06:00–14:00 | Ruta Veriore | PIS, QER, ORI |
| Ekipi i Grumbullimit 3 | 06:00–14:00 | Ruta Jugore | JUG (SKE, MZA), DAR |
| Ekipi i Grumbullimit 4 | 14:00–22:00 | Ruta Spitali+Qendër (pasdite) | SPI, QEN |

### 9.2 Cleaning teams (`team_type='cleaning'`)

| Team | Shift | Focus |
|---|---|---|
| Ekipi i Parqeve | 05:00–13:00 | Parku i Qytetit, Shkugëza, Çabrati |
| Ekipi i Qendrës | 05:00–13:00 | Sheshi qendror, Bazaar walkway, riverbank |
| Ekipi i Shkollave | 06:00–14:00 | School yards |

Routing is already team-type aware: `dashboard/roster_views.py` selects a
`collection` route for dumpster rooms and a `cleaning` route for area rooms via
`team__team_type` on the `Route`/`Team`.

---

## 10. Data seeding plan

To stand up a demo Gjakova dataset:

1. **Camp** → one row: `code='GJ'`, `name='Komuna e Gjakovës'`, `timezone='Europe/Belgrade'` (Kosovo local time).
2. **Compounds** → the 12 neighbourhoods in §5.
3. **Buildings** → the streets in §6 (a handful per neighbourhood to start).
4. **Floors** → 1–2 segments per street (or a single default).
5. **Rooms**:
   - dumpsters (`space_type='dumpster'`) per street with realistic weekly frequency;
   - public-area sites (`park` / `city_center` / `school_yard`) per §8 with SQM.
6. **Shifts** → morning/afternoon per §9.
7. **Teams** → collection + cleaning teams with `team_type` set.
8. **Routes** → map teams to neighbourhoods.
9. Generate `DailyCleaningTask`s via the existing generator; verify dashboard KPIs
   show both **SQM** and **dumpster** cards.

A management command (e.g. `python manage.py seed_gjakova`) is the recommended way
to make this repeatable. **Not yet implemented** — see §12.

> All commands run in Docker: `docker compose exec web python manage.py <cmd>`.

---

## 11. Operations map (Gjakova)

An interactive Leaflet + OpenStreetMap page shows the whole municipality:

- **Public-area cleaning sites** (parks, city centers, school yards) render as blue
  areas (a circle sized from `actual_sqm`, or a polygon if `Room.geo_polygon`
  GeoJSON is set).
- **Garbage-collection points** (dumpsters) render as dots coloured by whether the
  team may collect: **green = paid (collect)**, **red = unpaid/overdue/unconfirmed
  (do NOT collect)**.

Each dumpster popup shows: **dumpster ID**, barcode, **anonymized client ID** (no
name), **payment status** badge, paid-until date, street & neighbourhood, and an
explicit *OK to collect / Do NOT collect — confirm payment* line so field teams
know whether they should service it.

**Privacy / GDPR:** `CollectionClient` holds **no personal name**. Only
`client_code` + `payment_status` are serialized to the map API; human-readable
notes live in `internal_note` and are never exposed.

### Endpoints & files
| Piece | Location |
|---|---|
| Map page | `GET /map/` → `dashboard.map_views.collection_map` |
| Map data (JSON) | `GET /map/data/` → `dashboard.map_views.collection_map_data` |
| Template | `templates/dashboard/collection_map.html` (Leaflet) |
| Nav link | "Operations Map" (admin/manager/cleaner) in `templates/base.html` |
| Model | `Room.latitude/longitude/geo_polygon/client`, `CollectionClient` |

### Payment → collection rule
`Room.can_collect` is `True` only when the linked `CollectionClient.can_collect`
is true — i.e. `payment_status` is `paid`/`exempt` **and** `paid_until` (if set) is
not in the past. Dumpsters with no client default to **blocked** (must be confirmed).

---

## 12. Impact on existing code

| Area | Status |
|---|---|
| `Team.team_type` (cleaning/collection) | ✅ done |
| Dumpster `space_type` + SQM-bypass on save | ✅ done |
| Dynamic dashboard KPIs (SQM vs dumpster) | ✅ done |
| Team-type-aware roster routing | ✅ done |
| RFID/barcode format usable as `GJ-NBHD-STREET-POINT` | ✅ works via `cct/utils.generate_barcode_data` |
| Public-area space types (`park`/`city_center`/`school_yard`) | ✅ done (§8.1) |
| Geo fields + `CollectionClient` (anonymized + payment) | ✅ done |
| Operations map (dumpster dots + public areas + paid/unpaid) | ✅ done (§11) |
| Gjakova seed command (`seed_gjakova`) | ✅ done (§10) |
| Albanian labels / municipality wording in UI | ⛔ optional follow-up |

---

## 13. Operations Manager dashboard & TV wall

A dedicated **Operations Manager** role and a map/team-centric console reduce the
overloaded admin dashboard for day-to-day field supervision.

### Role
`operations_manager` added to `UserProfile.ROLE_CHOICES`. Logging in redirects to
`/operations/` (not the heavy admin dashboard). Demo user: `opsmanager / ops123`.

### Pages
| Page | URL | Purpose |
|---|---|---|
| Operations dashboard | `/operations/` | Map + live team progress cards + stream KPIs; refreshes every 30s. Has an **Open TV Wall** button. |
| TV wall | `/operations/tv/` | Full-screen, dark, big-font office monitor. **Left:** map with route polylines + dumpster/area dots. **Right:** live team progress bars + a rolling activity feed. Auto-refreshes every 15s. Standalone layout (no sidebar). |
| Data feed | `/operations/data/` | JSON powering both pages. |

### `/operations/data/` payload
- `teams[]` — per team today: type, shift, members, done/in_progress/planned/missed,
  `percent`, `last_activity`.
- `totals` — collection vs cleaning done/total/percent.
- `activity[]` — latest ≤30 done / in-progress tasks (team, room, neighbourhood, time).
- `routes[]` — polyline coordinates per active route, coloured; collection = solid,
  cleaning = dashed.
- `dumpsters[]` / `public_areas[]` / `counts` — reused from the map builder.

### Files
| Piece | Location |
|---|---|
| Views | `dashboard/operations_views.py` |
| Dashboard template | `templates/dashboard/operations_dashboard.html` |
| TV template | `templates/dashboard/operations_tv.html` |
| Shared map builder | `dashboard/map_views.build_map_features()` |
| Demo seed | `locations/management/commands/seed_operations.py` |

### Seeding the demo
```bash
docker compose exec web python manage.py seed_gjakova       # geography + dumpsters + areas
docker compose exec web python manage.py seed_operations    # shifts, teams, routes, today's tasks + ops manager
```
`seed_operations` creates 2 shifts, 5 teams (3 collection + 2 cleaning) with leaders
and members, routes per neighbourhood, and today's `DailyCleaningTask`s with
simulated progress so the dashboard/TV show live numbers immediately.

---

## 14. Open questions & next steps

1. **Confirm neighbourhood list** — should we mirror the 23 official PRrU zones
   from *HARTA ZONALE 2024–2032*, or the ~12 practical operational zones in §5?
2. **Timezone** — the seed uses `Europe/Belgrade` (Kosovo local time). Confirm this
   is the standard for the municipality deployment.
3. **Real coordinates** — the `seed_gjakova` points are approximate demo locations
   around the city centre; replace with surveyed dumpster/area coordinates.
4. **Editing UI** — add lat/lng + client + payment fields to the room/space admin
   forms so operators can place points without the seed command.
5. **Localisation** — decide whether UI strings should be Albanian (sq) for the
   municipality users.
