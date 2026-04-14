# План-наряд API — Список всех endpoints

## 🏢 Housings (Корпуса)

### GET /housings
Получить список всех корпусов
```json
Response: [
  {
    "id": "uuid",
    "name": "Корпус 1",
    "complex_name": "ЖК Солнечный",
    "description": "..."
  }
]
```

### GET /housings/{housing_id}/structure
Получить полную структуру корпуса (секции + этажи)
```json
Response: {
  "id": "uuid",
  "name": "Корпус 1",
  "complex_name": "ЖК Солнечный",
  "structure": [
    {
      "id": "uuid",
      "name": "Секция 1",
      "section_number": 1,
      "floors": [
        {"id": "uuid", "floor_number": 1, "name": "1-й этаж"}
      ]
    }
  ]
}
```

---

## 🔧 Works (Виды работ)

### GET /works
Получить список всех групп работ и видов работ
```json
Response: [
  {
    "id": "uuid",
    "name": "СМР",
    "code": "SMR",
    "order": 1,
    "work_types": [
      {
        "id": "uuid",
        "name": "Устройство фундамента",
        "code": "FUND",
        "unit": "м³"
      }
    ]
  }
]
```

### GET /works/tech-sequence/{housing_id}
Получить технологическую последовательность для корпуса
```json
Response: {
  "housing_id": "uuid",
  "housing_name": "Корпус 1",
  "sequence": [
    {
      "id": "uuid",
      "order": 1,
      "work_type": {...},
      "depends_on": [],
      "dependency_type": "finish_to_start",
      "lag_days": 0,
      "estimated_days": 5,
      "daily_norm_volume": "50.0000",
      "total_volume": "200.0000"
    }
  ]
}
```

---

## 👷 Contractors (Подрядчики)

### GET /contractors
Получить список всех подрядчиков
```json
Response: [
  {
    "id": "uuid",
    "name": "ООО СтройМастер",
    "short_name": "СтройМастер",
    "inn": "7701234567",
    "contact_person": "Иванов И.И.",
    "phone": "+7 (495) 123-45-67",
    "email": "info@stroymaster.ru"
  }
]
```

### GET /contractors/assignments/{housing_id}
Получить привязки подрядчиков к работам на объекте

Query params: `section_id`, `work_type_id`

```json
Response: [
  {
    "id": "uuid",
    "contractor": {...},
    "housing": {...},
    "section": {...},
    "work_group": {...},
    "work_types": [...]
  }
]
```

---

## 📋 Plans (План-наряды)

### POST /plan-naryad/generate
Сгенерировать план-наряд на указанную дату

Request:
```json
{
  "housing_id": "uuid",
  "target_date": "2024-03-25"
}
```

Response: массив `PlanWithDetails`

### GET /plan-naryad
Получить план-наряды с фильтрами

Query params: `start_date`, `end_date`, `housing_id`, `contractor_id`, `confirmed_only`, `limit`, `offset`

### GET /plan-naryad/contractor/{contractor_id}
Получить план-наряд для конкретного подрядчика

Query params: `start_date`, `end_date`, `limit`, `offset`

### PATCH /plan-naryad/{plan_id}/confirm
Подтвердить строку план-наряда (РС)

Request:
```json
{
  "is_confirmed": true
}
```

### PATCH /plan-naryad/{plan_id}/adjust
Скорректировать объём в строке план-наряда

Request:
```json
{
  "adjusted_volume": "120.50",
  "adjustment_reason": "Увеличен объём из-за дополнительных работ"
}
```

### GET /plan-naryad/rs-stats
Получить статистику по работе РС (подтверждения, корректировки)

Query params: `start_date`, `end_date`, `housing_id`

```json
Response: {
  "period": {...},
  "total_items": 100,
  "confirmed_items": 95,
  "adjusted_items": 5,
  "confirmation_rate": 0.95,
  "adjustment_rate": 0.05,
  "daily_stats": {...}
}
```

---

## ✅ Facts (Факты выполнения)

### POST /work-facts
Создать запись о фактическом выполнении работ

Request:
```json
{
  "date": "2024-03-24",
  "housing_id": "uuid",
  "section_id": "uuid",
  "floor_id": "uuid",
  "work_id": "uuid",
  "contractor_id": "uuid",
  "actual_volume": "95.50",
  "unit": "м²",
  "rs_user_id": null,
  "photos": [],
  "notes": "Работы выполнены в полном объёме"
}
```

### GET /work-facts
Получить факты выполнения работ с фильтрами

Query params: `start_date`, `end_date`, `housing_id`, `contractor_id`, `work_type_id`, `limit`, `offset`

---

## 🔄 Reconciliation (Сверка план/факт)

### POST /reconciliation/run
Запустить сверку план/факт для указанной даты

Request:
```json
{
  "date": "2024-03-24",
  "housing_id": "uuid"  // optional
}
```

Response:
```json
{
  "message": "Сверка запущена в фоновом режиме",
  "date": "2024-03-24",
  "housing_id": "uuid"
}
```

### GET /reconciliation
Получить результаты сверки с фильтрами

Query params: `date_from`, `date_to`, `housing_id`, `contractor_id`, `status`, `limit`, `offset`

```json
Response: [
  {
    "id": "uuid",
    "date": "2024-03-24",
    "housing_id": "uuid",
    "section_id": "uuid",
    "floor_id": "uuid",
    "work_id": "uuid",
    "contractor_id": "uuid",
    "planned_volume": "100.0000",
    "actual_volume": "98.0000",
    "completion_ratio": "0.9800",
    "status": "DONE_FULL",
    "pattern": null,
    "fact_is_late": false
  }
]
```

### GET /reconciliation/summary
Получить сводки сверки по дням

Query params: `date_from`, `date_to`, `housing_id`, `limit`, `offset`

```json
Response: [
  {
    "id": "uuid",
    "date": "2024-03-24",
    "housing_id": "uuid",
    "total_planned": 50,
    "total_done_full": 40,
    "total_done_partial": 5,
    "total_done_over": 2,
    "total_not_done": 2,
    "total_no_report": 1,
    "total_unplanned": 3,
    "completion_rate": "84.00",
    "weighted_completion": "86.50",
    "submission_rate": "98.00"
  }
]
```

### GET /reconciliation/contractor/{contractor_id}
Получить статистику сверки для конкретного подрядчика

Query params: `start_date`, `end_date`

```json
Response: {
  "start_date": "2024-03-01",
  "end_date": "2024-03-24",
  "total_results": 100,
  "by_status": {
    "DONE_FULL": 70,
    "DONE_PARTIAL": 15,
    "NOT_DONE": 5,
    "NO_REPORT": 10
  },
  "completion_rate": "85.00",
  "submission_rate": "90.00"
}
```

### GET /reconciliation/patterns
Анализ паттернов в результатах сверки

Query params: `date_from`, `date_to`, `housing_id`, `contractor_id`

---

## 🔔 Alerts (Алерты)

### GET /alerts
Получить алерты с фильтрами

Query params: `date_from`, `date_to`, `housing_id`, `contractor_id`, `alert_type`, `level`, `acknowledged`, `recipient_id`, `recipient_role`, `limit`, `offset`

```json
Response: [
  {
    "id": "uuid",
    "alert_type": "A05",
    "level": "warning",
    "date": "2024-03-24",
    "housing_id": "uuid",
    "contractor_id": "uuid",
    "message": "Подрядчик не подал факт по 2 работам",
    "channels_sent": [],
    "acknowledged": false,
    "escalation_level": 1
  }
]
```

### PATCH /alerts/{alert_id}/acknowledge
Подтвердить получение алерта

Request:
```json
{
  "acknowledged": true,
  "acknowledged_by": "uuid"
}
```

### GET /alerts/summary
Статистика алертов за период

Query params: `date_from`, `date_to`, `housing_id`

```json
Response: {
  "period": {...},
  "total_alerts": 50,
  "acknowledged_alerts": 45,
  "acknowledgment_rate": 0.9,
  "by_level": {
    "critical": 5,
    "warning": 20,
    "info": 25
  },
  "by_type": {...},
  "by_housing": {...}
}
```

---

## 📊 Dashboard (Дашборды)

### GET /dashboard/overview
Сводная информация для дашборда

Query params: `date_from`, `date_to`, `housing_id`

```json
Response: {
  "period": {...},
  "housing_id": "uuid",
  "totals": {
    "plans": 250,
    "confirmed_plans": 240,
    "facts": 235,
    "reconciliations": 245,
    "alerts": 15
  },
  "reconciliation": {
    "completed_works": 200,
    "completion_rate": 81.63,
    "by_status": {...}
  },
  "alerts": {
    "critical": 2,
    "warning": 8,
    "info": 5
  },
  "metrics": {
    "plan_confirmation_rate": 96.0,
    "fact_submission_rate": 94.0,
    "avg_completion_rate": 85.5,
    "avg_submission_rate": 95.0
  }
}
```

### GET /dashboard/contractors
Дашборд по подрядчикам

Query params: `date_from`, `date_to`, `housing_id`, `limit`

```json
Response: {
  "period": {...},
  "contractors": [
    {
      "id": "uuid",
      "name": "СтройМастер",
      "stats": {
        "total_plans": 80,
        "total_planned_volume": 5000.00,
        "total_facts": 75,
        "total_actual_volume": 4800.00,
        "completion_rate": 93.75,
        "reconciliation_stats": {...}
      }
    }
  ]
}
```

### GET /dashboard/rs-performance
Производительность РС (руководителей строительства)

Query params: `date_from`, `date_to`, `housing_id`

```json
Response: {
  "period": {...},
  "overall_stats": {
    "total_plans": 250,
    "confirmed_plans": 240,
    "confirmation_rate": 96.0,
    "avg_confirmation_time_hours": 24,
    "plans_per_day": 10.0
  },
  "daily_plans": [
    {
      "date": "2024-03-24",
      "total_plans": 12,
      "total_volume": 850.00
    }
  ]
}
```

---

## 🏥 System (Системные)

### GET /
Корневой endpoint
```json
Response: {
  "message": "План-наряд API",
  "version": "1.0.0",
  "docs": "/docs",
  "redoc": "/redoc"
}
```

### GET /health
Проверка здоровья приложения
```json
Response: {
  "status": "healthy",
  "database": "connected"
}
```

---

## 📝 Коды статусов

### Reconciliation Status
- `DONE_FULL` — Выполнено полностью (≥95%)
- `DONE_PARTIAL` — Выполнено частично (0-95%)
- `DONE_OVER` — Перевыполнение (>105%)
- `NOT_DONE` — Не выполнено (факт = 0)
- `NO_REPORT` — Факт не подан
- `UNPLANNED` — Внеплановая работа

### Alert Levels
- `critical` — Критический
- `warning` — Предупреждение
- `info` — Информация

### Alert Types
- `A01-A09` — Операционные
- `A10-A19` — Аналитические
- `A20-A23` — Системные

---

**Итого: 25+ endpoints**

Полная документация доступна в Swagger UI: http://localhost:8090/docs
