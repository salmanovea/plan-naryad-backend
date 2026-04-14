# Спецификация: Движок сверки план/факт

## 1. Назначение

Ежедневная автоматическая сверка плановых заданий (work-plans) с фактическим выполнением (work-facts). Запуск: **cron 20:00**. Результат — классифицированные отклонения, сводка дня по объекту, алерты.

---

## 2. Входные данные

### 2.1. План-наряд (из work-plans)

Каждая строка план-наряда содержит:

```
PlanItem {
  plan_id:           UUID
  date:              DATE        // дата план-наряда
  housing_id:        UUID        // корпус
  section_id:        UUID        // секция
  floor_id:          UUID        // этаж
  work_id:           UUID        // вид работ (из эталона)
  contractor_id:     UUID        // подрядчик
  planned_volume:    DECIMAL     // плановый объём
  unit:              STRING      // ед. измерения (м², м³, шт, п.м.)
  rs_confirmed:      BOOL        // подтверждён РС
  rs_confirmed_at:   TIMESTAMP   // время подтверждения
  rs_modified:       BOOL        // РС вносил корректировки
  source:            ENUM        // 'auto' | 'manual' | 'adjusted'
}
```

### 2.2. Факт выполнения (из work-facts)

```
FactItem {
  fact_id:           UUID
  date:              DATE
  housing_id:        UUID
  section_id:        UUID
  floor_id:          UUID
  work_id:           UUID
  contractor_id:     UUID
  actual_volume:     DECIMAL
  unit:              STRING
  submitted_at:      TIMESTAMP   // когда подал факт
  submitted_by:      UUID        // кто подал (подрядчик / РС)
  source:            ENUM        // 'contractor_bot' | 'contractor_web' | 'rs_web'
}
```

---

## 3. Алгоритм сверки

### 3.1. Шаг 1: Загрузка данных

```
plans  = GET /work-plans?date={today}&housing_id={housing_id}
facts  = GET /work-facts?date={today}&housing_id={housing_id}
```

Группировка:
- plans → dict по ключу `(contractor_id, section_id, floor_id, work_id)`
- facts → dict по ключу `(contractor_id, section_id, floor_id, work_id)`

### 3.2. Шаг 2: Сопоставление (matching)

Для каждой строки плана ищем соответствующий факт по ключу `(contractor_id, section_id, floor_id, work_id)`.

**Три множества:**
- `matched` — есть и план, и факт с одинаковым ключом
- `plan_only` — есть план, нет факта
- `fact_only` — есть факт, нет плана (внеплановые работы)

### 3.3. Шаг 3: Классификация

Каждая строка получает один из **6 статусов**:

| Статус | Код | Условие | Цвет |
|--------|-----|---------|------|
| Выполнено полностью | `DONE_FULL` | Факт ≥ 95% плана, совпадение по месту и виду | 🟢 |
| Выполнено частично | `DONE_PARTIAL` | 0 < Факт < 95% плана, совпадение по месту и виду | 🟡 |
| Перевыполнение | `DONE_OVER` | Факт > 105% плана | 🔵 |
| Не выполнено | `NOT_DONE` | План есть, факт = 0 или отсутствует | 🔴 |
| Факт не подан | `NO_REPORT` | План есть, факт отсутствует, submitted_at = null | ⚫ |
| Внеплановая работа | `UNPLANNED` | Факт есть, плана нет | 🟠 |

```python
def classify(plan_item, fact_item):
    if fact_item is None:
        return 'NO_REPORT'
    
    ratio = fact_item.actual_volume / plan_item.planned_volume
    
    if ratio >= 1.05:
        return 'DONE_OVER'
    elif ratio >= 0.95:
        return 'DONE_FULL'
    elif ratio > 0:
        return 'DONE_PARTIAL'
    else:
        return 'NOT_DONE'

# Для fact_only (внеплановые):
# status = 'UNPLANNED'
```

### 3.4. Шаг 4: Детектирование паттернов отклонений

Поверх базовой классификации — анализ паттернов:

| Паттерн | Условие | Флаг |
|---------|---------|------|
| Работа не там | План: секция 1, этаж 3. Факт: секция 1, этаж 5 (тот же вид работ, другой этаж) | `WRONG_LOCATION` |
| Работа не та | План: штукатурка. Факт: электрика (та же локация, другой вид работ) | `WRONG_WORK_TYPE` |
| Систематический невыход | Подрядчик 3+ дня подряд: NO_REPORT | `CHRONIC_NO_REPORT` |
| Систематическое невыполнение | Подрядчик 3+ дня подряд: NOT_DONE или DONE_PARTIAL < 50% | `CHRONIC_UNDERPERFORM` |

**Алгоритм обнаружения `WRONG_LOCATION`:**
```python
for fact in fact_only:
    # Ищем план того же подрядчика на тот же вид работ, но другую локацию
    matching_plans = [p for p in plan_only 
                      if p.contractor_id == fact.contractor_id 
                      and p.work_id == fact.work_id]
    if matching_plans:
        # Подрядчик сделал работу не там, где было запланировано
        fact.pattern = 'WRONG_LOCATION'
        fact.expected_location = matching_plans[0]  # где должен был
```

---

## 4. Выходные данные

### 4.1. Результат сверки по строке

```
ReconciliationItem {
  recon_id:          UUID
  date:              DATE
  housing_id:        UUID
  section_id:        UUID
  floor_id:          UUID
  work_id:           UUID
  contractor_id:     UUID
  
  planned_volume:    DECIMAL     // из плана (0 если UNPLANNED)
  actual_volume:     DECIMAL     // из факта (0 если NO_REPORT)
  completion_ratio:  DECIMAL     // actual / planned (0–N)
  
  status:            ENUM        // DONE_FULL | DONE_PARTIAL | DONE_OVER | NOT_DONE | NO_REPORT | UNPLANNED
  pattern:           ENUM?       // WRONG_LOCATION | WRONG_WORK_TYPE | null
  
  plan_id:           UUID?
  fact_id:           UUID?
  
  fact_submitted_at: TIMESTAMP?
  fact_is_late:      BOOL        // submitted_at > 20:00
}
```

### 4.2. Сводка дня по корпусу

```
DailySummary {
  date:              DATE
  housing_id:        UUID
  
  // Итого строк
  total_planned:     INT         // кол-во строк в план-наряде
  total_done_full:   INT
  total_done_partial: INT
  total_done_over:   INT
  total_not_done:    INT
  total_no_report:   INT
  total_unplanned:   INT
  
  // Процент выполнения
  completion_rate:   DECIMAL     // (done_full + done_over) / total_planned × 100
  weighted_completion: DECIMAL   // Σ(min(actual, planned)) / Σ(planned) × 100
  
  // По подрядчикам
  contractors: [
    {
      contractor_id:   UUID
      contractor_name: STRING
      planned_items:   INT
      completion_rate: DECIMAL
      fact_submitted:  BOOL       // подал ли факт вообще
      submitted_at:    TIMESTAMP?
      issues: [                   // список проблем
        { type: STRING, description: STRING }
      ]
    }
  ]
  
  // Критические алерты
  alerts: [
    { level: 'critical' | 'warning' | 'info', message: STRING, target_role: STRING }
  ]
}
```

### 4.3. Формулы

**Процент выполнения (простой):**
```
completion_rate = count(status IN ['DONE_FULL', 'DONE_OVER']) / count(all planned items) × 100
```

**Процент выполнения (взвешенный по объёму):**
```
weighted_completion = Σ min(actual_volume, planned_volume) / Σ planned_volume × 100
```
_Взвешенный учитывает объёмы: 50% от крупной работы весит больше, чем 100% от мелкой._

**Дисциплина подачи факта:**
```
submission_rate = count(contractors who submitted fact) / count(contractors with plans) × 100
on_time_rate = count(submitted_at ≤ 20:00) / count(all submissions) × 100
```

---

## 5. Хранение результатов

### 5.1. Таблица `reconciliation_results`

```sql
CREATE TABLE reconciliation_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    housing_id      UUID NOT NULL,
    section_id      UUID,
    floor_id        UUID,
    work_id         UUID,
    contractor_id   UUID NOT NULL,
    
    planned_volume  DECIMAL(12,4) DEFAULT 0,
    actual_volume   DECIMAL(12,4) DEFAULT 0,
    completion_ratio DECIMAL(8,4) DEFAULT 0,
    
    status          VARCHAR(20) NOT NULL,    -- DONE_FULL, DONE_PARTIAL, etc.
    pattern         VARCHAR(30),             -- WRONG_LOCATION, etc.
    
    plan_id         UUID,
    fact_id         UUID,
    fact_submitted_at TIMESTAMP,
    fact_is_late    BOOLEAN DEFAULT FALSE,
    
    created_at      TIMESTAMP DEFAULT NOW(),
    
    UNIQUE (date, housing_id, contractor_id, section_id, floor_id, work_id)
);

CREATE INDEX idx_recon_date_housing ON reconciliation_results(date, housing_id);
CREATE INDEX idx_recon_contractor ON reconciliation_results(contractor_id, date);
CREATE INDEX idx_recon_status ON reconciliation_results(status, date);
```

### 5.2. Таблица `daily_summaries`

```sql
CREATE TABLE daily_summaries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date            DATE NOT NULL,
    housing_id      UUID NOT NULL,
    
    total_planned   INT DEFAULT 0,
    total_done_full INT DEFAULT 0,
    total_done_partial INT DEFAULT 0,
    total_done_over INT DEFAULT 0,
    total_not_done  INT DEFAULT 0,
    total_no_report INT DEFAULT 0,
    total_unplanned INT DEFAULT 0,
    
    completion_rate DECIMAL(5,2) DEFAULT 0,
    weighted_completion DECIMAL(5,2) DEFAULT 0,
    submission_rate DECIMAL(5,2) DEFAULT 0,
    
    contractor_details JSONB,     -- массив по подрядчикам
    alerts          JSONB,        -- массив алертов
    
    created_at      TIMESTAMP DEFAULT NOW(),
    
    UNIQUE (date, housing_id)
);
```

---

## 6. Обработка граничных случаев

| Случай | Решение |
|--------|---------|
| РС не подтвердил план-наряд (rs_confirmed = false) | Сверка всё равно идёт по автосгенерированному плану. В сводке: флаг «план не подтверждён РС» |
| Подрядчик подал факт после 20:00 | fact_is_late = true. Учитываем в сверке, но фиксируем опоздание |
| Подрядчик подал факт на следующий день | Перезапуск сверки за вчера. Статус обновляется с NO_REPORT на фактический |
| Один подрядчик, несколько видов работ | Каждый вид работ — отдельная строка. Сводка группирует по подрядчику |
| Нет плана на этот день (выходной, нет данных) | Сверка не запускается. Если есть факт без плана — всё идёт в UNPLANNED |
| Объём = 0 в плане | Пропускаем строку (считаем отменённой). Если есть факт — UNPLANNED |
| Подрядчик сделал работу в нескольких местах вместо одного | Каждая локация — отдельный FactItem. Сопоставляем с планом поочерёдно |

---

## 7. Расписание и производительность

- **Запуск:** ежедневно 20:00 (cron)
- **Повторный запуск:** 08:00 следующего дня (пересчёт с учётом поздних фактов)
- **Scope:** один housing_id за запуск → параллелить по корпусам
- **Ожидаемый объём:** ~50–200 строк план/факт на корпус в день
- **Время обработки:** <5 сек на корпус (без учёта I/O)
- **Retention:** reconciliation_results хранить 12 месяцев, далее агрегировать в monthly_stats

---

## 8. API эндпоинты (новые)

```
GET  /api/v1/reconciliation?date={date}&housing_id={id}
     → ReconciliationItem[]

GET  /api/v1/reconciliation/summary?date={date}&housing_id={id}
     → DailySummary

GET  /api/v1/reconciliation/summary?date_from={}&date_to={}&housing_id={id}
     → DailySummary[]  (для трендов)

GET  /api/v1/reconciliation/contractor/{contractor_id}?date_from={}&date_to={}
     → контракторская сводка за период

POST /api/v1/reconciliation/run
     body: { date, housing_id }
     → запуск сверки вручную (для тестирования / пересчёта)
```

---

## 9. Зависимости

| Зависимость | Статус |
|-------------|--------|
| work-plans API (CRUD) | ✅ Есть |
| work-facts API (CRUD) | ✅ Есть |
| Структура объекта (housing → section → floor) | ✅ Есть |
| Справочник подрядчиков | ✅ Есть |
| Справочник видов работ | ✅ Есть |
| Новые таблицы БД | 🔧 Нужно создать |
| Новые API эндпоинты | 🔧 Нужно создать |
| Cron / task scheduler | 🔧 Нужно настроить |
