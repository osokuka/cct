# 📋 NATO Camp Cleaning Tracker — MVP Jira Backlog (Django, due Sept 8)

## EPIC 1 — Authentication & Security

**Goal:** Ensure strong, role-based authentication with multi-tenant scoping from day 1.

### Story 1.1 — User Authentication (Public)

* **Description:** Implement Django authentication with secure login/logout.

* **Acceptance Criteria:**
  * Secure session cookies (`Secure`, `HttpOnly`, `SameSite=Strict`)
  * CSRF protection enabled
  * Password complexity enforced
  * Lockout after 5 failed attempts (django-axes)

* **Developer Prompt:**
  * "Implement login/logout with secure session settings and `django-axes` lockout (5/min). Add tests for success, CSRF, and lockout."

### Story 1.2 — Password Reset (Public)

* **Description:** Email-based password reset flow.

* **Acceptance Criteria:**
  * Email flow (token-based) with rate limit
  * SMTP configuration
  * Branded templates

* **Developer Prompt:**
  * "Implement password reset via Django's auth views, connect SMTP, throttle requests, and template per branding."

### Story 1.3 — Roles & Scopes (Groups + Compound scoping)

* **Description:** Multi-tenant role-based access control with compound scoping.

* **Acceptance Criteria:**
  * Roles: `Admin`, `Supervisor`, `Cleaner`, `Authority`
  * `Authority` users are restricted to **assigned compounds only**
  * A user can be assigned to **multiple compounds**
  * Data access for Authority is **read-only**

* **Developer Prompt:**
  * "Implement Django Groups (`Admin`, `Supervisor`, `Cleaner`, `Authority`) and a `CompoundAssignment(user, compound)` model (unique `(user, compound)`). Add a `get_authority_compound_ids(user)` util. Write unit tests ensuring Authorities only retrieve objects within assigned compounds."

### Story 1.4 — RBAC Middleware (view-level + queryset-level)

* **Description:** Middleware-driven role enforcement with data scoping.

* **Acceptance Criteria:**
  * Middleware reads user role and attaches `request.role` + `request.scope.compound_ids`
  * DRF permissions + queryset filters enforce scoping server-side
  * Template guards hide forbidden links/actions

* **Developer Prompt:**
  * "Create `RBACMiddleware` that sets `request.role` and `request.scope.compound_ids` from DB. Add DRF `permissions.py` classes: `IsAdmin`, `IsSupervisor`, `IsCleaner`, `IsAuthorityReadOnly`. Add a `ScopedQuerysetMixin` base view to auto-filter by `compound_id__in=request.scope.compound_ids` for Authority users. Add tests."

### Story 1.5 — Audit Middleware (security logging)

* **Description:** Comprehensive security logging for all user actions.

* **Acceptance Criteria:**
  * Logs user, IP, method, path, status, latency, and object IDs when present
  * CSV export in Admin
  * PII minimization (no secrets)

* **Developer Prompt:**
  * "Build `AuditMiddleware` capturing user/IP/path/method/status/duration and `object_ref` when available via `request.audit_ref`. Store to `AuditLog`. Add `/admin/audit-logs` with filters + CSV export."

---

## EPIC 2 — Core Domain Models

**Goal:** Represent the camp hierarchy and cleaning events with multi-tenant support.

### Story 2.1 — Camp Hierarchy & Policy

* **Entities:** Camp → Compound → Building → Floor → Room.

* **Acceptance Criteria:** 
  * Each room has sqm, code, active status, barcode, and detailed cleaning schedule
  * Unique constraints per hierarchy level: `(parent, code)`
  * UUID primary keys for all models
  * Barcode field stores generated barcode data
  * Camp policy includes timezone, week cut-off, month cut-off, holiday handling
  * Room frequency includes per_day, per_week, time windows, shift binding

* **Developer Prompt:**
  * "Create Django models + migrations for Camp (with timezone, week_cutoff_day, week_cutoff_hour, month_cutoff_day, month_cutoff_hour, skip_holidays), Compound, Building, Floor, Room with UUID PKs, parent/child relationships, unique constraints. Add `sqm`, `room_code`, `is_active`, `barcode_data`, `frequency_per_day`, `frequency_per_week`, `time_window_start`, `time_window_end`, `shift_binding`. Register in admin with inline editing."

### Story 2.2 — Scan Events & Task Lifecycle

* **Description:** Store room scan events with device tracking and task state management.

* **Acceptance Criteria:** 
  * Event type = `CLEANED`, `RECLEANED`, `URGENT_CLEAN`
  * Linked to user + room + daily cleaning task
  * Device ID tracking
  * Duplicate prevention (room, user, timestamp ±5s)
  * Urgent cleaning flag for priority handling
  * Task state transitions: `PLANNED → IN_PROGRESS → DONE / MISSED / RE_CLEAN_REQUIRED`

* **Developer Prompt:**
  * "Implement `ScanEvent` model with fields: `room`, `user`, `scan_type`, `timestamp`, `device_id`, `is_urgent`, `daily_task`. Create `DailyCleaningTask` model with states: `PLANNED`, `IN_PROGRESS`, `DONE`, `MISSED`, `RE_CLEAN_REQUIRED`. Enforce `scan_type` enum including `URGENT_CLEAN`. Create DRF endpoint to record scans, validate duplicates by (`room`,`user`,`timestamp ±5s`). Write tests."

### Story 2.3 — Shifts & Roster Management

* **Description:** Define cleaning shifts and generate daily cleaning tasks.

* **Acceptance Criteria:**
  * Shifts defined per camp with time windows (e.g., Morning 08:00–12:00, Evening 14:00–18:00)
  * Daily cleaning tasks generated automatically based on room frequencies
  * Tasks unique per `(room, date, index_in_day)`
  * Idempotent roster generation (no duplicates)
  * Rolling horizon generation (e.g., next 7 days)

* **Developer Prompt:**
  * "Create `Shift` model with `camp`, `name`, `start_time`, `end_time`. Create `DailyCleaningTask` model with `room`, `date`, `index_in_day`, `shift`, `state`, `assigned_to`. Build roster generator service that creates tasks from room frequencies, honors camp cut-offs, and handles holidays. Include preview mode and idempotent generation."

### Story 2.4 — Multi-Tenant Compound Assignment

* **Description:** Link users to specific compounds for data scoping.

* **Acceptance Criteria:**
  * Unique `(user, compound)` constraint
  * Support multiple compound assignments per user
  * Audit trail for assignments

* **Developer Prompt:**
  * "Create `CompoundAssignment` model with `user`, `compound`, `created_at` fields. Add unique constraint on `(user, compound)`. Include admin interface for bulk assignment."

---

## EPIC 3 — Admin Dashboard

**Goal:** Management console for internal staff with comprehensive controls.

### Story 3.1 — Dashboard Home (KPIs & Roster)

* **Description:** Show key performance indicators, activity metrics, and roster status.

* **Acceptance Criteria:**
  * Show totals: rooms cleaned today, pending re-cleans, active users
  * Roster status: planned vs done vs missed tasks (aligned to camp cut-offs)
  * Fast queries; indexes present
  * "Top 5 buildings by scans today" chart
  * SLA metrics based on camp policy cut-offs

* **Developer Prompt:**
  * "Build `/admin/dashboard` with KPIs including roster status (planned/done/missed tasks), SLA metrics aligned to camp cut-offs, and "Top 5 buildings by scans today" chart. Ensure indexes on `ScanEvent(room, timestamp)` and `DailyCleaningTask(date, state)`. Add query tests."

### Story 3.2 — User Management (roles + compound assignment)

* **Description:** CRUD for users + assign roles and compounds.

* **Acceptance Criteria:**
  * Admin can create users, set roles, and attach multiple compounds
  * Deactivate/reactivate users
  * Search and filter capabilities
  * Validate at least one role per user

* **Developer Prompt:**
  * "Create CRUD views for users + inline `CompoundAssignment`. Validate at least one role. Add search + filters. Write tests for assignment and access."

### Story 3.3 — Reports (export CSV/PDF with scoping)

* **Description:** Generate filtered reports with proper authorization.

* **Acceptance Criteria:**
  * Filters: date range, camp/compound/building, team
  * Export **only what the viewer is allowed to see**
  * Authority users get **auto-scoped** exports
  * XLSX and PDF formats

* **Developer Prompt:**
  * "Implement `/admin/reports` with filters and exports (XLSX via `xlsxwriter`, PDF via WeasyPrint). Authorize exports via the same queryset scoping used for on-screen results. Add tests ensuring Authority export cannot include out-of-scope rows."

### Story 3.4 — Audit Logs (viewer)

* **Description:** View and export audit trail.

* **Acceptance Criteria:**
  * Paginated view + CSV export
  * Filters: user, date, status, action
  * PII minimization

* **Developer Prompt:**
  * "Build `/admin/audit-logs` with filters (user, date, status, action) and CSV export. Ensure PII minimization (no secrets)."

### Story 3.5 — Bulk Import (Locations & Rooms)

* **Description:** Import camp hierarchy data via CSV with cleaning schedules and frequencies.

* **Acceptance Criteria:**
  * CSV template with required columns:`Camp_Name`, `Compound_Name`, `BLDG_Location`, `m²`, `Qty_of_rooms`, `Actual_Sqm_m2`, `Frequency_Per_Day`, `Frequency_Per_Week`, `Max_Frequency_Per_Month`, `Total_m²_Week`, `EoM_Invoicing_max_Sqm_m2`, `#_Weeks_of_service`, `Start_Date`, `End_Date`, `Shift_Code`, `Time_Window_Start`, `Time_Window_End`
  * **Dry-run** shows: would-create, would-update, conflicts
  * **Apply** runs in transaction; creates missing parents automatically
  * Validate uniqueness per parent hierarchy
  * Auto-generate barcodes for imported rooms
  * Parse building location to extract hierarchy (e.g., "Bld. 87, 1 single container (toilet)")
  * Preview roster generation for imported rooms

* **Developer Prompt:**
  * "Build `/admin/import/locations` with a two-step flow: dry-run and apply. Parse CSV with cleaning schedule and frequency columns, extract building hierarchy from `BLDG_Location` field, normalize codes (uppercase/trim), validate, then show a diff table. On apply, wrap in `transaction.atomic()` and auto-generate barcodes for new rooms. Include roster preview showing how many tasks will be generated. Log a single `AuditLog` entry with counts. Tests for edge cases and rollbacks."

### Story 3.6 — Roster Management (Admin)

* **Description:** Configure camp policies, shifts, and generate daily cleaning rosters.

* **Acceptance Criteria:**
  * Configure camp policy: timezone, week cut-off, month cut-off, holiday handling
  * Define shifts with time windows per camp
  * Generate roster for rolling horizon (e.g., next 7 days)
  * Preview mode shows task count before generation
  * Idempotent generation (no duplicates)
  * Manual roster regeneration capability

* **Developer Prompt:**
  * "Create `/admin/roster-management` page with camp policy configuration, shift management, and roster generation. Include preview mode showing how many tasks will be created. Build roster generator service that creates `DailyCleaningTask` objects from room frequencies, honors camp cut-offs, and handles holidays. Make generation idempotent and include manual regeneration option."

### Story 3.7 — Barcode Generator (Admin)

* **Description:** Generate and manage barcodes for room identification.

* **Acceptance Criteria:**
  * Generate barcodes for individual rooms or bulk generation
  * Download barcode images (PNG/PDF) for printing
  * Regenerate barcodes if needed
  * Barcode format: Code128 with room identification data
  * Preview barcode before generation

* **Developer Prompt:**
  * "Create `/admin/barcode-generator` page with room selection, bulk generation options, and download functionality. Use `python-barcode` library to generate Code128 barcodes. Include preview, individual/bulk generation, and PDF/PNG export options. Add barcode regeneration capability."

---

## EPIC 4 — Contracting Authority Dashboard (Multi-Tenant)

**Goal:** Transparency for NATO contracting authorities with compound-scoped data access.

### Story 4.1 — Dashboard Home (Read-Only, scoped)

* **Description:** Read-only dashboard with daily/weekly cleaning status and SLA metrics.

* **Acceptance Criteria:**
  * Show only data from assigned compounds
  * Filters: date, building, room status
  * No edit actions available
  * SLA metrics based on camp cut-offs (not calendar periods)
  * Planned vs completed vs missed tasks per compound

* **Developer Prompt:**
  * "Implement `/authority/dashboard` read-only views with SLA metrics aligned to camp cut-offs. Show planned vs completed vs missed tasks per compound. Apply `ScopedQuerysetMixin` everywhere. Add tests to ensure cross-compound leakage is impossible."

### Story 4.2 — Re-clean Requests (Authority → Admin workflow)

* **Description:** Authority can flag rooms for re-cleaning with comments.

* **Acceptance Criteria:**
  * Authority can submit "Request Re-clean" with comment (scoped)
  * Creates extra PLANNED task for same day (or next if past cut-off)
  * Admin/Supervisor can mark resolved
  * Status visible in both dashboards
  * Workflow: `OPEN → RESOLVED`
  * SLA calculations include re-cleans as required tasks

* **Developer Prompt:**
  * "Create `RecleanRequest(room, requested_by, reason, status, resolved_by, timestamps)` with transitions `OPEN → RESOLVED`. Automatically generate extra `DailyCleaningTask` when re-clean requested. Views for Authority (create/list) and Admin/Supervisor (list/resolve). Enforce scoping. Tests included."

### Story 4.3 — Urgent Cleaning Requests (Authority)

* **Description:** Authority can request urgent cleaning for immediate attention.

* **Acceptance Criteria:**
  * Authority can submit "Urgent Cleaning Request" with priority flag
  * Urgent requests appear at top of cleaning queue
  * Real-time notifications to cleaners/supervisors
  * Status tracking: `URGENT_REQUESTED → IN_PROGRESS → COMPLETED`
  * Escalation if not completed within time limit

* **Developer Prompt:**
  * "Create `UrgentCleaningRequest(room, requested_by, reason, priority_level, status, assigned_to, created_at, completed_at)` with priority levels and status transitions. Add real-time notifications using WebSockets or polling. Include escalation logic for overdue urgent requests. Enforce scoping for Authority users."

---

## EPIC 5 — Scanning Interface (Web MVP)

**Goal:** Enable cleaners to scan rooms using device cameras.

### Story 5.1 — Barcode Scanner (Mobile)

* **Description:** Use device camera to scan room barcodes for cleaners with task management.

* **Acceptance Criteria:**
  * Camera scanning for 1D barcodes (Code128)
  * Manual room code entry fallback
  * Posts `room_code`, records `ScanEvent` (CLEANED / RECLEANED / URGENT_CLEAN)
  * Show cleaner's tasks for today from generated roster
  * Show last 5 scans with room details
  * Mobile-optimized interface
  * Offline capability with sync when online
  * Display urgent cleaning requests for assigned rooms
  * Task state transitions: PLANNED → IN_PROGRESS → DONE

* **Developer Prompt:**
  * "Build `/scan` page: Use BarcodeDetector API for 1D barcode scanning (fallback QuaggaJS for older browsers). POST to `/api/scans/`. Show cleaner's daily tasks from `DailyCleaningTask` roster, last 5 scans with room names and timestamps. Display urgent cleaning requests for the cleaner's assigned rooms. Mobile-responsive design with large scan button. Server validates room exists, user role allows scans, and updates task states. Tests for API and client."

### Story 5.2 — Barcode Validation & Room Lookup

* **Description:** Server-side barcode validation and room identification.

* **Acceptance Criteria:**
  * Validate barcode format and decode room identification
  * Lookup room by barcode data
  * Handle invalid/missing barcodes gracefully
  * Return room details for successful scans

* **Developer Prompt:**
  * "Create API endpoint `/api/rooms/scan/` that accepts barcode data, validates format, decodes room identification, and returns room details. Handle invalid barcodes with appropriate error messages. Include room hierarchy path in response."

---

## EPIC 6 — Roster & SLA Management

**Goal:** Automated roster generation, task lifecycle management, and SLA tracking aligned to camp policies.

### Story 6.1 — Day Closing & SLA Automation

* **Description:** Automated day closing and SLA calculation based on camp cut-offs.

* **Acceptance Criteria:**
  * At end of operational day (camp timezone), PLANNED tasks become MISSED
  * SLA metrics calculated based on camp's cut-off rules (not calendar week/month)
  * Automated task state transitions
  * Escalation for overdue urgent requests

* **Developer Prompt:**
  * "Create daily closing service that runs at camp timezone end-of-day. Mark remaining PLANNED tasks as MISSED. Calculate SLA metrics based on camp cut-offs. Include escalation logic for overdue urgent requests. Add management command for manual day closing."

### Story 6.2 — Roster Preview & Validation

* **Description:** Preview roster generation before applying changes.

* **Acceptance Criteria:**
  * Preview mode shows how many tasks will be created
  * Validation of room frequencies and shift assignments
  * Holiday handling based on camp policy
  * Conflict detection and resolution

* **Developer Prompt:**
  * "Build roster preview system that shows task generation without creating actual tasks. Validate room frequencies, shift assignments, and holiday policies. Include conflict detection for overlapping shifts or invalid frequencies. Provide detailed preview with task counts per room/shift/day."

---

## EPIC 7 — Security Exports & Guarantees

**Goal:** Ensure all exports respect authorization and are properly audited.

### Story 7.1 — Export Guard (centralized)

* **Description:** Centralized export authorization and logging.

* **Acceptance Criteria:**
  * All export endpoints use **the same scoped queryset** as the UI
  * Exports are logged (who/when/filters/count)
  * Authority cannot export out-of-scope data

* **Developer Prompt:**
  * "Implement an `export_queryset(qs, format, user, filters)` helper that requires a pre-scoped queryset and logs the export to `AuditLog` with metadata. Replace inline export code with this helper. Tests ensure Authority cannot export out-of-scope data by manipulating params."

### Story 7.2 — Session & CSRF Hardening

* **Description:** Comprehensive security hardening.

* **Acceptance Criteria:**
  * `SECURE_*` and cookie flags set
  * CSRF tokens enforced across POST/PUT/PATCH/DELETE
  * HSTS and SSL redirect

* **Developer Prompt:**
  * "Add secure Django settings (HSTS, SSL redirect, secure cookies, SameSite=Strict). Verify CSRF protection on all forms and APIs. Add tests for CSRF failure and success."

---

## EPIC 8 — Deployment & Ops

**Goal:** Make app runnable quickly for MVP.

### Story 8.1 — Docker Setup

* **Developer Prompt:**
  * "Write docker-compose with Django (gunicorn), Postgres, Redis, and NGINX. Configure volumes for db/data, env-based secrets, healthchecks. Add `manage.py migrate` and `collectstatic` on startup."

### Story 8.2 — Backups

* **Developer Prompt:**
  * "Create cronjob container or systemd timer that runs nightly `pg_dump` to volume. Keep last 7 days. Document restore procedure."

---

# 🎯 Timeline (Sept 1 → Sept 8)

* **Sept 1–2:** Auth, RBAC, Audit, Models, Multi-tenant scoping
* **Sept 3–4:** Admin Dashboard, Reports, Bulk Import
* **Sept 5–6:** Contracting Authority Dashboard + Re-clean flow
* **Sept 7:** Scanning Interface, Security hardening, testing
* **Sept 8:** Delivery demo + packaging

---

# Models (Concise Spec)

* **Camp(id, code, name, timezone, week_cutoff_day, week_cutoff_hour, month_cutoff_day, month_cutoff_hour, skip_holidays)**
* **Compound(id, camp, code, name)**
* **Building(id, compound, code, name)**
* **Floor(id, building, code, name)**
* **Room(id, floor, code, name, sqm, is_active, barcode_data, frequency_per_day, frequency_per_week, time_window_start, time_window_end, shift_binding)**
* **Shift(id, camp, name, start_time, end_time)**
* **DailyCleaningTask(id, room, date, index_in_day, shift, state[PLANNED|IN_PROGRESS|DONE|MISSED|RE_CLEAN_REQUIRED], assigned_to, created_at, completed_at)**
* **CompoundAssignment(id, user, compound, created_at)**
* **ScanEvent(id, room, user, scan_type[CLEANED|RECLEANED|URGENT_CLEAN], device_id, barcode_scanned, is_urgent, daily_task, timestamp)**
* **RecleanRequest(id, room, requested_by, reason, status[OPEN|RESOLVED], resolved_by, created_at, resolved_at)**
* **UrgentCleaningRequest(id, room, requested_by, reason, priority_level, status[URGENT_REQUESTED|IN_PROGRESS|COMPLETED], assigned_to, created_at, completed_at)**
* **AuditLog(id, user, ip, method, path, status, latency_ms, object_ref, created_at)**

**Indexes:**
* `(ScanEvent.room, ScanEvent.timestamp)`
* `(CompoundAssignment.user, CompoundAssignment.compound)` unique
* Uniqueness per hierarchy level: `(parent, code)`
* `(Room.barcode_data)` unique index for fast barcode lookups
* `(DailyCleaningTask.room, DailyCleaningTask.date, DailyCleaningTask.index_in_day)` unique
* `(DailyCleaningTask.date, DailyCleaningTask.state)` for roster queries
* `(DailyCleaningTask.assigned_to, DailyCleaningTask.date)` for cleaner task lists

---

# Barcode System Requirements

**Barcode Format:** Code128
**Barcode Content:** Room identification string (e.g., "CAMP-COMPOUND-BUILDING-FLOOR-ROOM")
**Generation Library:** `python-barcode` with `Pillow` for image generation
**Scanning Library:** Browser `BarcodeDetector` API with `QuaggaJS` fallback

**Barcode Data Structure:**
```
Format: {camp_code}-{compound_code}-{building_code}-{floor_code}-{room_code}
Example: "CAMP1-DANISH-BLDG-A-FL1-RM101"
```

**Required Python Packages:**
* `python-barcode[images]` - Barcode generation
* `Pillow` - Image processing
* `reportlab` - PDF generation for barcode sheets

---

# CSV Import Format Specification

**CSV Template Columns:**
```
Camp_Name, Compound_Name, BLDG_Location, m², Qty_of_rooms, Actual_Sqm_m2, 
Frequency_Per_Day, Frequency_Per_Week, Max_Frequency_Per_Month, Total_m²_Week, 
EoM_Invoicing_max_Sqm_m2, #_Weeks_of_service, Start_Date, End_Date, 
Shift_Code, Time_Window_Start, Time_Window_End
```

**Example Data:**
```
"CAMP1", "DANISH", "Bld. 87, 1 single container (toilet)", 13.16, 1, 13.16, 1, 7, 31, 92.12, 407.96, 14, 1-Oct-25, 31-Dec-25, "MORNING", "08:00", "12:00"
"CAMP1", "DANISH", "Bld. 87, 1 single containers F4", 13.16, 1, 13.16, 1, 3, 15, 39.48, 197.4, 14, 1-Oct-25, 31-Dec-25, "EVENING", "14:00", "18:00"
"CAMP1", "DANISH", "Bld. 87, 1 single containers F5", 13.16, 1, 13.16, 1, 3, 15, 39.48, 197.4, 14, 1-Oct-25, 31-Dec-25, "EVENING", "14:00", "18:00"
```

**Building Location Parsing:**
* Extract building number from "Bld. XX" pattern
* Extract floor/container info from description
* Create room hierarchy: Building → Floor → Room
* Handle special cases (toilets, containers, etc.)

**Date Format:** DD-MMM-YY (e.g., "1-Oct-25", "31-Dec-25")

---

# Middleware & Permissions (Implementation Notes)

**RBACMiddleware**
* On each request, set `request.role` from Django Groups
* If `Authority`, populate `request.scope.compound_ids = list(CompoundAssignment.objects.filter(user=request.user).values_list('compound_id', flat=True))`

**ScopedQuerysetMixin**
* In `get_queryset`, if `Authority`, filter by `compound_id__in`
* Reuse in Admin/Authority views and APIView/DRF ViewSets

**DRF Permissions**
* `IsAdmin` full access
* `IsSupervisor` read/write except user/role admin
* `IsCleaner` scan endpoints only
* `IsAuthorityReadOnly` read-only; deny POST/PUT unless for `RecleanRequest.create`

**Export Guard**
* Central helper `export_queryset()` to enforce scoping + log

---

# Routing to Pages

**Public**
* `/accounts/login/`
* `/accounts/password-reset/`

**Admin Dashboard**
* `/admin/dashboard`
* `/admin/users`
* `/admin/reports`
* `/admin/audit-logs`
* `/admin/import/locations` (bulk upload)
* `/admin/roster-management` (roster generation)
* `/admin/barcode-generator` (barcode generation)

**Contracting Authority**
* `/authority/dashboard`
* `/authority/reclean-requests`
* `/authority/urgent-cleaning-requests`

**Cleaner UI**
* `/scan`

---

# QA Checklist (MVP)

* Authority user assigned to Danish compound sees **only Danish data** across UI and exports
* Attempting to change `compound_id` in query params **does not** bypass scoping
* Exports contain **exactly** what the table shows
* Bulk import: dry-run shows correct diffs; apply commits atomically; all actions audited
* CSRF enforced everywhere; session cookies hardened; lockout on brute force
* All user actions logged in audit trail with proper object references
* Multi-tenant data isolation verified across all views and exports
* **Barcode functionality:**
  * Generated barcodes are unique and properly formatted (Code128)
  * Barcode scanning works on mobile devices with camera
  * Invalid barcodes are handled gracefully
  * Room lookup by barcode is accurate and fast
  * Barcode generation includes proper room identification data
* **CSV Import functionality:**
  * CSV import handles cleaning schedule data correctly
  * Building location parsing extracts hierarchy properly
  * All cleaning frequency fields are imported and validated
  * Date fields are parsed correctly (DD-MMM-YY format)
* **Urgent cleaning requests:**
  * Authority users can create urgent cleaning requests
  * Urgent requests appear with priority in cleaner interface
  * Real-time notifications work for urgent requests
  * Escalation logic triggers for overdue urgent requests
* **Roster & SLA management:**
  * Camp policies configured with timezone and cut-off rules
  * Daily cleaning tasks generated automatically from room frequencies
  * Task lifecycle: PLANNED → IN_PROGRESS → DONE / MISSED / RE_CLEAN_REQUIRED
  * SLA metrics calculated based on camp cut-offs (not calendar periods)
  * Day closing automation marks remaining tasks as MISSED
  * Roster generation is idempotent and includes preview mode
