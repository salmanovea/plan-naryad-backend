# Спецификация: Автогенерация план-наряда

## 1. Назначение

Ежедневная автоматическая генерация план-нарядов для подрядчиков на основе эталонной техпоследовательности, текущего прогресса и структуры объекта. Запуск: **cron 06:00**. Результат — набор work-plan записей, готовых к валидации РС.

---

## 2. Концепция

```
Техпоследовательность (эталон)
        ↓
  Что МОЖНО делать сегодня?         ← зависимости между работами
        ↓
  Что НУЖНО делать сегодня?         ← приоритеты, календарный план
        ↓
  КТО будет делать?                 ← привязка подрядчиков к видам работ
        ↓
  ГДЕ будет делать?                 ← секция × этаж (фронт работ)
        ↓
  СКОЛЬКО?                          ← объём на день (из норм или остатка)
        ↓
  Plan-наряд на день
```

---

## 3. Входные данные

### 3.1. Эталонная техпоследовательность

Источник: `plan-templates` API (существующий).

```
TechSequenceItem {
  work_id:           UUID        // вид работ
  work_name:         STRING      // название
  work_group_id:     UUID        // группа работ
  order:             INT         // порядок в последовательности
  depends_on:        [UUID]      // предшествующие работы (work_id)
  dependency_type:   ENUM        // 'finish_to_start' | 'start_to_start'
  lag_days:          INT         // задержка после предшествующей (0 = сразу)
  estimated_days:    INT         // нормативная длительность (на 1 секцию × 1 этаж)
  daily_norm_volume: DECIMAL     // норма выработки за день (на бригаду)
  unit:              STRING      // ед. измерения
}
```

### 3.2. Текущий прогресс

Источник: `work-facts` API + `reconciliation_results` (из движка сверки).

```
ProgressItem {
  housing_id:     UUID
  section_id:     UUID
  floor_id:       UUID
  work_id:        UUID
  total_volume:   DECIMAL       // общий объём по ВОР
  done_volume:    DECIMAL       // выполненный объём (Σ фактов)
  remaining:      DECIMAL       // total - done
  completion_pct: DECIMAL       // done / total × 100
  last_fact_date: DATE          // дата последнего факта
  status:         ENUM          // 'not_started' | 'in_progress' | 'done'
}
```

### 3.3. Привязка подрядчиков

Источник: `contractor-works` API (существующий).

```
ContractorAssignment {
  contractor_id:   UUID
  housing_id:      UUID
  section_id:      UUID?        // null = все секции
  work_group_id:   UUID         // группа работ
  work_ids:        [UUID]       // конкретные виды работ
}
```

### 3.4. Структура объекта

Источник: `housings/{id}/structure` API (существующий).

```
ObjectStructure {
  housing_id:     UUID
  sections: [
    {
      section_id:  UUID
      section_name: STRING
      floors: [
        { floor_id: UUID, floor_number: INT }
      ]
    }
  ]
}
```

### 3.5. Календарный план (опционально)

Источник: `calendar-plans` API (существующий).

```
CalendarPlanItem {
  work_id:       UUID
  section_id:    UUID
  planned_start: DATE
  planned_end:   DATE
  planned_volume: DECIMAL
}
```

---

## 4. Алгоритм генерации

### 4.1. Шаг 1: Определение доступного фронта работ

Для каждой ячейки `(section_id, floor_id, work_id)` определяем: **можно ли работать сегодня?**

```python
def is_available(section_id, floor_id, work_id, tech_sequence, progress):
    """
    Работа доступна, если:
    1. Все предшествующие работы (depends_on) завершены на данном этаже
    2. Работа ещё не завершена (remaining > 0)
    3. Нет блокирующих условий
    """
    item = tech_sequence[work_id]
    
    for dep_work_id in item.depends_on:
        dep_progress = progress.get((section_id, floor_id, dep_work_id))
        
        if dep_progress is None or dep_progress.status != 'done':
            # Предшествующая работа не завершена
            if item.dependency_type == 'finish_to_start':
                return False
            elif item.dependency_type == 'start_to_start':
                # Достаточно, чтобы предшествующая была начата
                if dep_progress is None or dep_progress.status == 'not_started':
                    return False
        
        # Проверяем lag
        if item.lag_days > 0 and dep_progress:
            if dep_progress.last_fact_date:
                days_since = (today - dep_progress.last_fact_date).days
                if days_since < item.lag_days:
                    return False
    
    # Проверяем остаток
    own_progress = progress.get((section_id, floor_id, work_id))
    if own_progress and own_progress.status == 'done':
        return False
    
    return True
```

### 4.2. Шаг 2: Приоритизация

Доступные работы ранжируются:

```python
def priority_score(section_id, floor_id, work_id, context):
    score = 0
    
    # 1. Продолжение начатых работ (наивысший приоритет)
    progress = context.progress.get((section_id, floor_id, work_id))
    if progress and progress.status == 'in_progress':
        score += 1000
    
    # 2. Критический путь (из календарного плана)
    cal_item = context.calendar_plan.get((section_id, work_id))
    if cal_item:
        days_to_deadline = (cal_item.planned_end - today).days
        if days_to_deadline <= 0:
            score += 500  # Просрочка!
        elif days_to_deadline <= 3:
            score += 300  # Скоро дедлайн
        elif days_to_deadline <= 7:
            score += 100
    
    # 3. Порядок в техпоследовательности (чем раньше — тем приоритетнее)
    tech_item = context.tech_sequence[work_id]
    score += (1000 - tech_item.order)  # инвертируем порядок
    
    # 4. Этажность (снизу вверх для СМР, сверху вниз для отделки)
    floor = context.floors[floor_id]
    if tech_item.work_group_id in BOTTOM_UP_GROUPS:
        score += floor.floor_number
    else:
        score += (max_floor - floor.floor_number)
    
    return score
```

### 4.3. Шаг 3: Распределение по подрядчикам

```python
def assign_contractor(section_id, floor_id, work_id, assignments):
    """
    Находим подрядчика, привязанного к данному виду работ на данной секции.
    """
    for assignment in assignments:
        if work_id in assignment.work_ids:
            if assignment.section_id is None or assignment.section_id == section_id:
                return assignment.contractor_id
    
    return None  # Нет привязанного подрядчика → пропускаем
```

### 4.4. Шаг 4: Расчёт объёма на день

```python
def calculate_daily_volume(section_id, floor_id, work_id, context):
    """
    Объём = min(дневная норма, оставшийся объём)
    """
    progress = context.progress.get((section_id, floor_id, work_id))
    tech_item = context.tech_sequence[work_id]
    
    remaining = progress.remaining if progress else tech_item.total_volume
    daily_norm = tech_item.daily_norm_volume
    
    return min(daily_norm, remaining)
```

### 4.5. Шаг 5: Формирование план-наряда

```python
def generate_daily_plan(housing_id, date):
    # Загрузка данных
    structure = get_structure(housing_id)
    tech_seq = get_tech_sequence(housing_id)
    progress = get_progress(housing_id)
    assignments = get_contractor_assignments(housing_id)
    calendar = get_calendar_plan(housing_id)
    
    context = Context(structure, tech_seq, progress, assignments, calendar)
    plan_items = []
    
    for section in structure.sections:
        for floor in section.floors:
            for work in tech_seq.items:
                # Шаг 1: Доступность
                if not is_available(section.id, floor.id, work.id, tech_seq, progress):
                    continue
                
                # Шаг 3: Подрядчик
                contractor_id = assign_contractor(section.id, floor.id, work.id, assignments)
                if not contractor_id:
                    continue
                
                # Шаг 4: Объём
                volume = calculate_daily_volume(section.id, floor.id, work.id, context)
                if volume <= 0:
                    continue
                
                plan_items.append(PlanItem(
                    date=date,
                    housing_id=housing_id,
                    section_id=section.id,
                    floor_id=floor.id,
                    work_id=work.id,
                    contractor_id=contractor_id,
                    planned_volume=volume,
                    unit=work.unit,
                    rs_confirmed=False,
                    source='auto'
                ))
    
    # Шаг 2: Приоритизация (сортировка)
    plan_items.sort(key=lambda x: priority_score(x.section_id, x.floor_id, x.work_id, context), reverse=True)
    
    # Ограничение: не больше N заданий на подрядчика (предотвращаем перегрузку)
    MAX_ITEMS_PER_CONTRACTOR = 10
    contractor_counts = {}
    filtered = []
    for item in plan_items:
        count = contractor_counts.get(item.contractor_id, 0)
        if count < MAX_ITEMS_PER_CONTRACTOR:
            filtered.append(item)
            contractor_counts[item.contractor_id] = count + 1
    
    # Сохранение через API
    POST /work-plans  body: filtered
    
    return filtered
```

---

## 5. Обработка корректировок РС

### 5.1. Сценарии

| Действие РС | Обработка |
|-------------|-----------|
| Подтверждает без изменений | `rs_confirmed = true`, `source = 'auto'` |
| Меняет этаж/секцию | `source = 'adjusted'`, сохраняем исходный (для аналитики отклонений от эталона) |
| Удаляет строку | `status = 'cancelled_by_rs'`, причина обязательна |
| Добавляет строку вручную | `source = 'manual'`, не привязана к автогенерации |
| Меняет объём | `source = 'adjusted'`, сохраняем исходный плановый |

### 5.2. Хранение корректировок

```
PlanAdjustment {
  plan_id:         UUID
  original_field:  STRING       // 'floor_id' | 'volume' | 'work_id' ...
  original_value:  STRING
  new_value:       STRING
  reason:          STRING       // обязательный комментарий
  adjusted_by:     UUID         // РС
  adjusted_at:     TIMESTAMP
}
```

### 5.3. Метрика «Отклонение РС от эталона»

```
rs_deviation_rate = count(adjusted + cancelled) / count(all auto-generated) × 100
```

Высокий % (> 30%) → сигнал:
- Либо эталон неактуален → обновить техпоследовательность
- Либо РС работает не по технологии → разбор с ДС

---

## 6. Граничные случаи

| Случай | Решение |
|--------|---------|
| Нет техпоследовательности для корпуса | Генерация не запускается. Алерт администратору |
| Подрядчик не привязан к виду работ | Строка пропускается. В сводке: «Нет подрядчика для [вид работ] на [секция]» |
| Все работы завершены на этаже | Этаж пропускается |
| Все работы завершены на секции | Секция пропускается |
| Нет прогресса (первый день) | Берём первые работы из техпоследовательности (order=1, без зависимостей) |
| Подрядчик перегружен (>10 строк) | Ограничиваем по приоритету. В сводке: «Подрядчику сгенерировано max заданий» |
| Выходной / нерабочий день | Проверяем `system-calendar-plans/non-working-days`. Генерация не запускается |
| Вчерашний план не выполнен | Невыполненные работы учтены в remaining → попадут в сегодняшний план автоматически |

---

## 7. Расписание

| Время | Событие |
|-------|---------|
| 06:00 | Cron: автогенерация план-наряда |
| 06:01 | Push РС: «План-наряд сформирован. Проверьте и подтвердите» |
| 10:00 | Проверка: если РС не подтвердил → алерт ДС/ДП |
| 10:01 | Автоподтверждение: если РС не отреагировал → план считается принятым, отправляется подрядчику |

---

## 8. API эндпоинты (новые)

```
POST /api/v1/plan-naryad/generate
     body: { date, housing_id }
     → генерация план-наряда (ручной запуск)

GET  /api/v1/plan-naryad?date={date}&housing_id={id}
     → план-наряд на день (сгруппированный по подрядчикам)

GET  /api/v1/plan-naryad/contractor/{contractor_id}?date={date}
     → план-наряд конкретного подрядчика (для бота)

PATCH /api/v1/plan-naryad/{plan_id}/confirm
     → подтверждение РС

PATCH /api/v1/plan-naryad/{plan_id}/adjust
     body: { changes: [...], reason: STRING }
     → корректировка РС

GET  /api/v1/plan-naryad/rs-stats?rs_id={id}&date_from={}&date_to={}
     → статистика корректировок РС (для аналитики)
```

---

## 9. Зависимости

| Зависимость | Статус |
|-------------|--------|
| plan-templates API | ✅ Есть |
| work-plans API (CRUD) | ✅ Есть |
| work-facts API (для прогресса) | ✅ Есть |
| calendar-plans API | ✅ Есть |
| contractor-works (привязка) | ✅ Есть |
| Структура объекта | ✅ Есть |
| non-working-days | ✅ Есть |
| Таблица plan_adjustments | 🔧 Нужно создать |
| Cron scheduler | 🔧 Нужно настроить |
| Push-уведомления | 🔧 Нужно интегрировать |
