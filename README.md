# План-наряд API

FastAPI backend для системы управления план-нарядами строительных работ.

## Описание

Система автоматизирует процесс планирования и контроля выполнения строительных работ:
- **Автогенерация план-наряда** на основе технологической последовательности
- **Сверка план/факт** с классификацией статусов выполнения
- **Алертинг** для руководителей и подрядчиков
- **Дашборды** с аналитикой по выполнению работ

## Технологический стек

- **FastAPI** — веб-фреймворк
- **SQLAlchemy 2.0** — ORM с async поддержкой
- **PostgreSQL** — база данных
- **asyncpg** — асинхронный драйвер PostgreSQL
- **Pydantic** — валидация данных
- **Docker & Docker Compose** — контейнеризация

## Структура проекта

```
app/
├── api/                    # API роутеры
│   ├── housings.py         # Корпуса и структура
│   ├── works.py            # Виды работ и техпоследовательность
│   ├── contractors.py      # Подрядчики и привязки
│   ├── plans.py            # План-наряды
│   ├── facts.py            # Факты выполнения
│   ├── reconciliation.py   # Сверка план/факт
│   ├── alerts.py           # Алерты
│   └── dashboard.py        # Дашборды
├── models/                 # SQLAlchemy модели
│   ├── housing.py          # Housing, Section, Floor
│   ├── work.py             # WorkGroup, WorkType, TechSequenceItem
│   ├── contractor.py       # Contractor, ContractorAssignment
│   ├── plan.py             # PlanItem, PlanAdjustment
│   ├── fact.py             # WorkFact
│   ├── reconciliation.py   # ReconciliationResult, DailySummary
│   └── alert.py            # Alert
├── schemas/                # Pydantic схемы
├── services/               # Бизнес-логика
│   ├── autogeneration.py   # Автогенерация план-наряда
│   ├── reconciliation.py   # Алгоритм сверки
│   └── alerts.py           # Генерация алертов
├── mock_data/              # Тестовые данные
│   └── seed.py             # Заполнение БД моками
├── config.py               # Конфигурация
├── database.py             # Подключение к БД
└── main.py                 # Точка входа

```

## Запуск

### Через Docker Compose (рекомендуется)

```bash
# Запуск
docker compose up -d --build

# Проверка логов
docker compose logs -f api

# Остановка
docker compose down
```

API будет доступно по адресу: `http://localhost:8090`

### Локально (для разработки)

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск PostgreSQL (если нужен)
docker run -d \
  -e POSTGRES_DB=plan_naryad \
  -e POSTGRES_USER=pn_user \
  -e POSTGRES_PASSWORD=pn_secret \
  -p 5433:5432 \
  postgres:16

# Переменные окружения
export DATABASE_URL="postgresql+asyncpg://pn_user:pn_secret@localhost:5433/plan_naryad"

# Запуск приложения
uvicorn app.main:app --reload --port 8090
```

## API Endpoints

### Документация

- **Swagger UI**: http://localhost:8090/docs
- **ReDoc**: http://localhost:8090/redoc

### Основные эндпоинты

#### Корпуса
- `GET /housings` — список корпусов
- `GET /housings/{id}/structure` — структура корпуса (секции, этажи)

#### Виды работ
- `GET /works` — группы и виды работ
- `GET /works/tech-sequence/{housing_id}` — технологическая последовательность

#### Подрядчики
- `GET /contractors` — список подрядчиков
- `GET /contractors/assignments/{housing_id}` — привязки подрядчиков к работам

#### План-наряды
- `POST /plan-naryad/generate` — сгенерировать план-наряд на дату
- `GET /plan-naryad` — получить план-наряды (с фильтрами)
- `GET /plan-naryad/contractor/{id}` — план-наряды подрядчика
- `PATCH /plan-naryad/{id}/confirm` — подтвердить план (РС)
- `PATCH /plan-naryad/{id}/adjust` — скорректировать объём
- `GET /plan-naryad/rs-stats` — статистика работы РС

#### Факты выполнения
- `POST /work-facts` — подать факт выполнения
- `GET /work-facts` — получить факты (с фильтрами)

#### Сверка план/факт
- `POST /reconciliation/run` — запустить сверку
- `GET /reconciliation` — результаты сверки
- `GET /reconciliation/summary` — сводки по дням
- `GET /reconciliation/contractor/{id}` — статистика подрядчика

#### Алерты
- `GET /alerts` — получить алерты (с фильтрами)
- `PATCH /alerts/{id}/acknowledge` — подтвердить получение алерта
- `GET /alerts/summary` — статистика алертов

#### Дашборды
- `GET /dashboard/overview` — общая сводка
- `GET /dashboard/contractors` — дашборд по подрядчикам
- `GET /dashboard/rs-performance` — производительность РС

## Тестовые данные

При первом запуске база автоматически заполняется тестовыми данными:

- **ЖК "Солнечный"**
- 2 корпуса
- 4 секции (по 2 на корпус)
- 40 этажей (по 10 на секцию)
- 12 видов работ (от фундамента до отделки)
- 3 подрядчика с привязками к работам
- История план-нарядов и фактов за последние 25 рабочих дней

## Основные алгоритмы

### Автогенерация план-наряда

1. Проверяет технологическую доступность работ (зависимости выполнены)
2. Ранжирует по приоритетам:
   - Продолжение начатых = 1000
   - Просрочка = 500
   - Дедлайн = 300
3. Назначает подрядчика по привязкам
4. Рассчитывает дневной объём (min дневной нормы и остатка)
5. Ограничивает 10 items per contractor

### Сверка план/факт

1. Сопоставляет планы и факты по ключу `(contractor, section, floor, work)`
2. Классифицирует статусы:
   - `DONE_FULL` ≥ 95%
   - `DONE_PARTIAL` 0-95%
   - `DONE_OVER` > 105%
   - `NOT_DONE` факт = 0
   - `NO_REPORT` факт не подан
   - `UNPLANNED` план отсутствует
3. Определяет паттерны ошибок (WRONG_LOCATION, WRONG_WORK_TYPE)
4. Строит сводку дня с метриками

### Генерация алертов

- **Операционные** (ежедневные): не подан факт, критическое отклонение
- **Аналитические** (трендовые): хроническое невыполнение, отказ от отчётов
- **Сводки** дня с общими показателями

## Разработка

### Миграции (Alembic)

```bash
# Создать миграцию
alembic revision --autogenerate -m "Description"

# Применить миграции
alembic upgrade head

# Откатить миграцию
alembic downgrade -1
```

### Линтинг и форматирование

```bash
# Black
black app/

# isort
isort app/

# flake8
flake8 app/
```

### Тесты

```bash
pytest tests/
```

## Production

Для продакшена рекомендуется:

1. Использовать PostgreSQL кластер (master-replica)
2. Настроить nginx как reverse proxy
3. Использовать gunicorn с несколькими workers
4. Настроить мониторинг (Prometheus + Grafana)
5. Логирование в ELK/Loki
6. Бэкапы базы данных
7. CI/CD pipeline (GitHub Actions / GitLab CI)

## Лицензия

Proprietary

## Контакты

При возникновении вопросов обращайтесь к команде разработки.
