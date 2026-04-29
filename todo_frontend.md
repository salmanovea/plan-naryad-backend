# Frontend Migration Guide — Workforce `work_type` refactor

All workforce endpoints that previously accepted or returned a free-text `work_type` string now use structured work type references.

**Request bodies** accept `work_type_id: UUID`.
**GET responses** return `work_type: { id: UUID, name: string }` (a named entity object).

---

## Changed request bodies

| Endpoint | Old field | New field |
|----------|-----------|-----------|
| `POST /api/v1/workforce/norms` | `work_type: string` | `work_type_id: UUID` |
| `POST /api/v1/workforce/headcount/facts` | `work_type: string` | `work_type_id: UUID` |
| `POST /api/v1/workforce/headcount/plans` | `work_type: string` | `work_type_id: UUID` |
| `POST /api/v1/workforce/challenges` — `items[]` | `work_type: string` | `work_type_id: UUID` |
| `POST /api/v1/workforce/violations` | `work_type: string` | `work_type_id: UUID` |
| `POST /api/v1/workforce/article-mappings` | `work_type: string` | `work_type_id: UUID` |
| `POST /api/v1/workforce/article-mappings/bulk` — `items[]` | `work_type: string` | `work_type_id: UUID` |

---

## Changed response schemas

All `work_type` fields in GET responses are now named entity objects instead of plain strings or UUIDs.

**New shape:**
```json
"work_type": {
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "Монолитные работы"
}
```

| Schema / endpoint | Old field | New field |
|-------------------|-----------|-----------|
| `WfWorkforceNormSchema` — `GET /api/v1/workforce/norms` | `work_type_id: UUID` | `work_type: { id, name }` |
| `WfHeadcountFactSchema` — `GET /api/v1/workforce/headcount/facts` | `work_type_id: UUID` | `work_type: { id, name }` |
| `WfHeadcountPlanSchema` — `GET /api/v1/workforce/headcount/plans` | `work_type_id: UUID` | `work_type: { id, name }` |
| `ChallengeItemSchema` — `GET /api/v1/workforce/challenges` | `work_type_id: UUID` | `work_type: { id, name }` |
| `ArticleMappingSchema` — `GET /api/v1/workforce/article-mappings` | `work_type_id: UUID` | `work_type: { id, name }` |
| `ViolationOut` — `GET /api/v1/workforce/violations` | `work_type_id: UUID` | `work_type: { id, name }` |
| `WorkTypeRow` — nested in project detail & dashboard responses | `work_type_id: UUID` | `work_type: { id, name }` |
| `ForecastRow` — `GET /api/v1/workforce/projects/{id}/forecast` | `work_type_id: UUID` | `work_type: { id, name }` |
| `ContractorHeadcountRow` — `GET /api/v1/workforce/objects/{id}/contractors` | `work_type_id: UUID` | `work_type: { id, name }` |
| `SystemProblemRow` — `GET /api/v1/workforce/system-problems` | `work_type_id: UUID` | `work_type: { id, name }` |

---

## `top_problem` field

`ObjectDashboardItem.top_problem` and `ProjectRow.top_problem` (returned by dashboard and project-detail endpoints) contain the **name** of the most problematic work type (human-readable string). No UUID resolution needed.

---

## Checklist

- [ ] Replace `work_type: string` with `work_type_id: UUID` in all workforce POST/PUT request payloads
- [ ] Update response parsing: read `work_type.id` and `work_type.name` instead of a flat `work_type_id` UUID
- [ ] Remove any client-side `id → name` lookup maps built from a separate `GET /api/v1/works/types` call — the name is now included inline in every response
