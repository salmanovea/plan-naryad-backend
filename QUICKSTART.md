# 🚀 План-наряд API — Быстрый старт

## За 3 шага к работающему API

### 1️⃣ Запустить приложение

```bash
cd /tmp/plan-naryad-app
docker compose up -d --build
```

Ждём ~30 секунд пока поднимется PostgreSQL и API.

### 2️⃣ Проверить что работает

```bash
curl http://localhost:8090/health
```

Ответ:
```json
{
  "status": "healthy",
  "database": "connected"
}
```

### 3️⃣ Открыть Swagger UI

Открываем в браузере: **http://localhost:8090/docs**

Готово! 🎉

---

## Что внутри?

База автоматически заполнена тестовыми данными:

- **ЖК "Солнечный"**
- 2 корпуса
- 4 секции
- 40 этажей
- 12 видов работ (от фундамента до отделки)
- 3 подрядчика
- История работ за 25 дней

---

## Сценарии использования

### 🏢 Посмотреть структуру объекта

```bash
curl http://localhost:8090/housings
```

Берём `id` первого корпуса и смотрим структуру:

```bash
curl http://localhost:8090/housings/{id}/structure
```

### 📋 Сгенерировать план-наряд на завтра

```bash
curl -X POST http://localhost:8090/plan-naryad/generate \
  -H "Content-Type: application/json" \
  -d '{
    "housing_id": "HOUSING_UUID",
    "target_date": "2024-03-25"
  }'
```

### ✅ Подать факт выполнения работ

```bash
curl -X POST http://localhost:8090/work-facts \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2024-03-24",
    "housing_id": "...",
    "section_id": "...",
    "floor_id": "...",
    "work_id": "...",
    "contractor_id": "...",
    "actual_volume": "95.50",
    "unit": "м²",
    "notes": "Работы выполнены"
  }'
```

### 🔄 Запустить сверку план/факт

```bash
curl -X POST http://localhost:8090/reconciliation/run \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2024-03-24",
    "housing_id": "HOUSING_UUID"
  }'
```

### 📊 Посмотреть дашборд

```bash
curl "http://localhost:8090/dashboard/overview?date_from=2024-03-01&date_to=2024-03-24"
```

---

## Остановить приложение

```bash
docker compose down
```

Удалить данные (если нужно начать с нуля):

```bash
docker compose down -v
```

---

## Где что?

- **Swagger UI**: http://localhost:8090/docs
- **ReDoc**: http://localhost:8090/redoc
- **API**: http://localhost:8090
- **PostgreSQL**: localhost:5433

---

## Что дальше?

1. Изучить [API_ENDPOINTS.md](./API_ENDPOINTS.md) — список всех endpoint'ов
2. Прочитать [README.md](./README.md) — полная документация
3. Посмотреть [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) — что реализовано

---

## Проблемы?

Проверить логи:

```bash
docker compose logs -f api
```

Проверить базу данных:

```bash
docker compose exec db psql -U pn_user -d plan_naryad
```

---

🦞 **Приятного использования!**
