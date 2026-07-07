# Corporate Language Glossary

The product started as a NATO-camp cleaning tracker. It has been re-targeted for
civilian municipal operations (Gjakova). To keep the codebase stable, **database
model names are unchanged**; only the **user-facing language** is rebranded.

Use these terms in all UI copy (templates, labels, buttons, page titles, nav,
help text, admin `verbose_name`s). Do NOT rename Django model classes, fields,
context variables, URL names, or ids.

| Legacy term (code)      | Corporate term (UI)  | Notes |
|-------------------------|----------------------|-------|
| Camp (`Camp`)           | **Site**             | Top-level operational area (e.g. "Gjakova"). |
| Camp Manager            | **Field Manager**    | The `manager` role. Role key stays `manager`. |
| Compound (`Compound`)   | **Zone**             | Collection zone / neighbourhood. |
| Building (`Building`)   | **Street**           | Carries the road geometry (`geo_polyline`). |
| Floor (`Floor`)         | **Street Segment**   | Rarely surfaced. |
| Room (`Room`)           | **Service Point**    | A dumpster (collection) or public area (cleaning). |
| Route (`Route`)         | **Route**            | A team's daily plan of streets. Unchanged. |
| Team (`Team`)           | **Team**             | Unchanged. |
| Shift (`Shift`)         | **Shift**            | Unchanged. |
| DailyCleaningTask       | **Task**             | Backend, one per dumpster, for reporting/tracking. |
| CollectionClient        | **Client**           | Anonymized billing client. Unchanged. |

## Route / task model (corporate)

- A **Team** gets a **daily Route** (one route per weekday).
- A **Route** contains N **Streets**; each street carries its geolocated dumpsters
  (**Service Points**).
- **Tasks** are generated per dumpster in the backend for reporting and tracking.
- Tasks are generated automatically every **Sunday 00:01**, on a **weekly** or
  **bi-weekly** cadence chosen by management (`PlanGenerationConfig`).
