# Frontend Migration Guide

API changes after backend refactoring (branch `report-refactor`).
Every endpoint is now under `/api/v1/` — that prefix is unchanged.

---

## 1. Universal changes (ALL endpoints)

### 1.1 Response envelope

Every successful response is now wrapped:

```json
// Single object
{ "code": "200", "message": "OK", "data": { ... } }

// List
{
  "code": "200",
  "message": "OK",
  "data": [ ... ],
  "pagination": { "page": 1, "per_page": 20, "total": 100, "pages": 5 }
}
```

Frontend must unwrap `.data` before using the payload.

### 1.2 Error format

```json
// Old
{ "detail": "Корпус не найден" }

// New
{ "code": "404", "message": "Корпус не найден" }
```

All error handlers must read `.message` instead of `.detail`.

### 1.3 Pagination query params

| Old | New |
|-----|-----|
| `limit` | `per_page` |
| `offset` | `page` (1-based) |
| `skip` | `page` |

---

## 2. Housings — `/api/v1/housings`

No URL changes. All responses now wrapped (see §1.1).

**Inline names removed from list response.** Old `GET /` returned objects with enriched relations; new returns only DB fields.

**`DELETE /{id}`** — no longer returns `{"message": "..."}`, response is `{"code": "200", "data": null}`.

---

## 3. Works — `/api/v1/works`

### URL changes

| Old | New |
|-----|-----|
| `GET /api/v1/works/` | `GET /api/v1/works/types` |
| `GET /api/v1/works/{id}` | `GET /api/v1/works/types/{id}` |
| `POST /api/v1/works/` | `POST /api/v1/works/types` |

`/groups` and `/tech-sequence` URLs are unchanged.

---

## 4. Contractors — `/api/v1/contractors`

### URL change

| Old | New |
|-----|-----|
| `GET /api/v1/contractors/assignments/{housing_id}` | `GET /api/v1/contractors/{housing_id}/assignments` |

All other URLs unchanged. Responses wrapped (§1.1).

---

## 5. Plan-naryad — `/api/v1/plan-naryad`

### URL changes

| Old | New |
|-----|-----|
| `GET /api/v1/plan-naryad/?date=X&housing_id=Y` | `GET /api/v1/plan-naryad/daily?target_date=X&housing_id=Y` |
| `GET /api/v1/plan-naryad/contractor/{id}?date=X` | `GET /api/v1/plan-naryad/contractor?target_date=X&contractor_id=Y` |
| `POST /api/v1/plan-naryad/manual` | `POST /api/v1/plan-naryad/` |
| `PATCH /api/v1/plan-naryad/{id}/confirm` | `POST /api/v1/plan-naryad/{id}/confirm` |
| `PATCH /api/v1/plan-naryad/{id}/adjust` | `POST /api/v1/plan-naryad/{id}/adjust` |

### Removed endpoint

`GET /api/v1/plan-naryad/rs-stats` — removed, no replacement.

---

## 6. Work-facts — `/api/v1/work-facts`

### Query param changes

| Old | New |
|-----|-----|
| `start_date` | `date_from` |
| `end_date` | `date_to` |
| `limit` + `offset` | `page` + `per_page` |

### Response schema change

Old `GET /` returned objects with inline enriched fields:
`housing_name`, `section_name`, `floor_name`, `work_type_name`, `contractor_name`.

New response contains only IDs — these names are no longer included.
Frontend must either fetch names separately or display IDs until the schema is extended.

---

## 7. Reconciliation — `/api/v1/reconciliation`

### URL changes

| Old | New |
|-----|-----|
| `GET /api/v1/reconciliation/` | `GET /api/v1/reconciliation/results` |
| `GET /api/v1/reconciliation/summary` | `GET /api/v1/reconciliation/summaries` |

### Removed endpoints

- `GET /api/v1/reconciliation/contractor/{id}` — removed.
- `GET /api/v1/reconciliation/patterns` — removed.

### Response schema change

Old `GET /` returned results with inline names (`housing_name`, `section_name`, etc.).
New `GET /results` contains only IDs.

`POST /run` response is now wrapped: `{"code":"200","data":{"message":"...","date":"..."}}` instead of a plain object.

---

## 8. Alerts — `/api/v1/alerts`

### Method change

| Old | New |
|-----|-----|
| `PATCH /api/v1/alerts/{id}/acknowledge` | `POST /api/v1/alerts/{id}/acknowledge` |

### Removed endpoint

`GET /api/v1/alerts/summary` — removed. No direct replacement (use dashboard overview).

### Response schema change

Old `GET /` returned alerts with inline `housing_name`, `contractor_name`.
New response contains only IDs.

### New endpoints

- `GET /api/v1/alerts/{id}` — get single alert.
- `POST /api/v1/alerts/generate` — trigger alert generation for a date/housing.
  Body: `{"housing_id": "uuid|null", "alert_date": "YYYY-MM-DD"}`.
- `POST /api/v1/alerts/escalation/run` — run escalation check.

---

## 9. Dashboard — `/api/v1/dashboard`

### URL `GET /overview` — response schema changed

Old response was a large flat object:
```json
{
  "period": {"from": "...", "to": "..."},
  "housing_id": "...",
  "housing_name": "...",
  "totals": { "plans": 0, "confirmed_plans": 0, "facts": 0, "reconciliations": 0, "alerts": 0 },
  "reconciliation": { "completed_works": 0, "completion_rate": 0, "by_status": {} },
  "alerts": { "critical": 0, "warning": 0, "info": 0 },
  "metrics": { "plan_confirmation_rate": 0, "fact_submission_rate": 0, "avg_completion_rate": 0, "avg_submission_rate": 0 },
  "recent_summaries": [...]
}
```

New response is wrapped in `{"code":"200","data":{...}}` and the inner schema is `DashboardOverviewSchema` (field names may differ — verify against `/docs`).

### Removed endpoints

- `GET /api/v1/dashboard/contractors` — removed.
- `GET /api/v1/dashboard/rs-performance` — removed.

---

## 10. Workforce — `/api/v1/workforce`

### URL changes

| Old | New |
|-----|-----|
| `GET /api/v1/workforce/project/{id}` | `GET /api/v1/workforce/projects/{id}/detail` |
| `GET /api/v1/workforce/project/{id}/forecast` | `GET /api/v1/workforce/projects/{id}/forecast` |
| `GET /api/v1/workforce/analytics/system-problems` | `GET /api/v1/workforce/system-problems` |
| `GET /api/v1/workforce/analytics/contractor-rating` | `GET /api/v1/workforce/contractor-rating` |

### Removed endpoints

The `wf-contractors` sub-resource is removed — contractors are now unified under `/api/v1/contractors`.

| Removed | Use instead |
|---------|-------------|
| `GET /api/v1/workforce/wf-contractors` | `GET /api/v1/contractors` |
| `POST /api/v1/workforce/wf-contractors` | `POST /api/v1/contractors` |
| `DELETE /api/v1/workforce/wf-contractors/{id}` | `DELETE /api/v1/contractors/{id}` |

All other workforce URLs are unchanged. All responses are now wrapped (§1.1).

---

## 11. Sync — `/api/v1/sync` *(new)*

Three new endpoints trigger synchronisation with the Raport system. All require the Raport/Keycloak credentials to be configured server-side.

| Method | URL | Description |
|--------|-----|-------------|
| `POST` | `/api/v1/sync/objects` | Sync project hierarchy: WfProject → ConstructionObject → Housing → Section → Floor |
| `POST` | `/api/v1/sync/work-catalog` | Sync work catalog: WorkGroup → WorkType |
| `POST` | `/api/v1/sync/contractors` | Sync contractor list |

Response: `{"code":"200","data":{"<entity>": <count>, ...}}` with counts of upserted records.

`POST /api/v1/sync/objects` accepts an optional `project_raport_id` query param to limit sync to one project.

---

## 12. New fields on existing models *(additive, non-breaking)*

These fields are now present in API responses but do not require immediate frontend changes.

| Model | New fields |
|-------|-----------|
| `Housing` | `raport_id`, `construction_object_id` |
| `Section` | `raport_id` |
| `Floor` | `raport_id` |
| `Contractor` | `raport_id`, `description` |
| `WorkGroup` | `raport_id` |
| `WorkType` | `raport_id` |
| `WfProject` | `raport_id` |
| `WfProjectObject` | `raport_id` |

---

## Quick checklist

- [ ] Central axios/fetch wrapper unwraps `.data` from the envelope
- [ ] Error handler reads `.message` instead of `.detail`
- [ ] Pagination switches from `limit`/`offset`/`skip` to `page`/`per_page`
- [ ] Updated URLs for plan-naryad daily list and contractor list
- [ ] Updated method for `acknowledge` alert (PATCH → POST)
- [ ] Updated URL for contractor assignments (`.../assignments/{housing_id}` → `.../{housing_id}/assignments`)
- [ ] Updated URL for workforce project detail and analytics
- [ ] Updated work-facts filter params (`start_date`/`end_date` → `date_from`/`date_to`)
- [ ] Updated reconciliation list URL (`/` → `/results`) and summary URL (`/summary` → `/summaries`)
- [ ] Removed references to deleted endpoints: `rs-stats`, `reconciliation/contractor/{id}`, `reconciliation/patterns`, `alerts/summary`, `dashboard/contractors`, `dashboard/rs-performance`, `workforce/wf-contractors`
- [ ] Work-facts and reconciliation results: adapt UI to work without inline names (fetch separately or display IDs)
