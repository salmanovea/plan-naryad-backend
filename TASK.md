# TASK: Plan-Naryad MVP Backend

Build a complete FastAPI + PostgreSQL application for the "План-наряд" (daily work orders) system. 
Read ALL spec files in this repo before starting: ONE-PAGER.md, spec-autogeneration.md, spec-reconciliation.md, spec-alerts.md, spec-telegram-bot.md.

## Architecture

```
plan-naryad-app/
├── docker-compose.yml          # postgres + fastapi + (telegram-bot later)
├── Dockerfile                  # FastAPI app
├── requirements.txt
├── alembic/                    # DB migrations
│   ├── alembic.ini
│   └── versions/
├── app/
│   ├── main.py                 # FastAPI app entry
│   ├── config.py               # Settings (env vars)
│   ├── database.py             # SQLAlchemy engine/session
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── __init__.py
│   │   ├── housing.py          # Object structure (housing, section, floor)
│   │   ├── work.py             # Work types, tech sequence
│   │   ├── contractor.py       # Contractors, assignments
│   │   ├── plan.py             # Plan-naryad items
│   │   ├── fact.py             # Work facts
│   │   ├── reconciliation.py   # Reconciliation results, daily summaries
│   │   └── alert.py            # Alerts
│   ├── schemas/                # Pydantic models
│   │   ├── __init__.py
│   │   ├── housing.py
│   │   ├── work.py
│   │   ├── contractor.py
│   │   ├── plan.py
│   │   ├── fact.py
│   │   ├── reconciliation.py
│   │   └── alert.py
│   ├── api/                    # FastAPI routers
│   │   ├── __init__.py
│   │   ├── housings.py         # GET structure, sections, floors
│   │   ├── works.py            # GET work types, tech sequences
│   │   ├── contractors.py      # GET contractors, assignments
│   │   ├── plans.py            # CRUD plan-naryad + generate endpoint
│   │   ├── facts.py            # CRUD work facts
│   │   ├── reconciliation.py   # GET reconciliation results + run endpoint
│   │   ├── alerts.py           # GET alerts + acknowledge
│   │   └── dashboard.py        # Aggregated analytics for DS/DP
│   ├── services/               # Business logic
│   │   ├── __init__.py
│   │   ├── autogeneration.py   # Full algorithm from spec-autogeneration.md
│   │   ├── reconciliation.py   # Full algorithm from spec-reconciliation.md
│   │   ├── alerts.py           # Alert engine from spec-alerts.md
│   │   └── escalation.py       # Escalation logic
│   └── mock_data/              # Seed data
│       ├── __init__.py
│       └── seed.py             # Creates realistic mock data on startup
└── tests/
    └── test_autogeneration.py
```

## Requirements

### 1. Database Models (PostgreSQL + SQLAlchemy)
All tables from the specs:
- housings, sections, floors (object structure)
- work_types, tech_sequence_items (with dependencies, order, norms)
- contractors, contractor_assignments
- plan_items (daily work orders)
- plan_adjustments (RS corrections tracking)
- work_facts (actual execution)
- reconciliation_results + daily_summaries
- alerts (with escalation tracking)

### 2. Mock Data (seed.py)
Create realistic mock data for ONE construction project:
- Project: "ЖК Солнечный" (housing complex)
- 2 housings (Корпус 1, Корпус 2)
- Each: 2 sections, 10 floors
- Tech sequence: 12 work types (from foundations to finishing) with realistic dependencies
- 3 contractors assigned to different work groups
- Progress: some works done, some in progress, some not started
- Some existing plan-naryads and facts for past 5 days
- Seed runs on app startup if DB is empty

### 3. Core Services

#### autogeneration.py
FULL algorithm from spec-autogeneration.md:
- is_available() — check dependencies
- priority_score() — rank available work
- assign_contractor() — find responsible contractor
- calculate_daily_volume() — daily norm or remaining
- generate_daily_plan() — orchestrator, max 10 items per contractor
- Schedule: manual trigger via API (cron will call it)

#### reconciliation.py
FULL algorithm from spec-reconciliation.md:
- load_and_match() — match plans to facts by key
- classify() — 6 statuses (DONE_FULL, DONE_PARTIAL, DONE_OVER, NOT_DONE, NO_REPORT, UNPLANNED)
- detect_patterns() — WRONG_LOCATION, WRONG_WORK_TYPE, CHRONIC_*
- build_summary() — DailySummary with completion rates
- All formulas: completion_rate, weighted_completion, submission_rate

#### alerts.py
From spec-alerts.md:
- Full alert catalog (A01-A23)
- Message templates
- Grouping and deduplication
- Escalation rules (check_escalation)
- For now: just store alerts in DB (delivery channels: later)

### 4. API Endpoints

From the specs:
```
# Plan-naryad
POST /api/v1/plan-naryad/generate          — auto-generate plan
GET  /api/v1/plan-naryad?date=&housing_id= — get daily plan
GET  /api/v1/plan-naryad/contractor/{id}   — plan for specific contractor
PATCH /api/v1/plan-naryad/{id}/confirm     — RS confirms
PATCH /api/v1/plan-naryad/{id}/adjust      — RS adjusts
GET  /api/v1/plan-naryad/rs-stats          — RS deviation analytics

# Facts
POST /api/v1/work-facts                     — submit fact
GET  /api/v1/work-facts?date=&housing_id=   — get facts

# Reconciliation
POST /api/v1/reconciliation/run             — trigger reconciliation
GET  /api/v1/reconciliation?date=&housing_id= — get results
GET  /api/v1/reconciliation/summary         — daily summary
GET  /api/v1/reconciliation/contractor/{id} — contractor stats

# Alerts
GET  /api/v1/alerts?recipient_id=&date=     — get alerts
PATCH /api/v1/alerts/{id}/acknowledge       — acknowledge alert

# Reference data (from mocks)
GET  /api/v1/housings                       — list housings
GET  /api/v1/housings/{id}/structure        — sections + floors
GET  /api/v1/works                          — work types
GET  /api/v1/works/tech-sequence/{housing_id} — tech sequence
GET  /api/v1/contractors                    — contractors
GET  /api/v1/contractors/assignments/{housing_id} — assignments

# Dashboard
GET  /api/v1/dashboard/overview?housing_id= — key metrics
GET  /api/v1/dashboard/contractors?housing_id=&date_from=&date_to= — contractor performance
GET  /api/v1/dashboard/rs-performance?date_from=&date_to= — RS analytics
```

### 5. Docker Compose
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: plan_naryad
      POSTGRES_USER: pn_user
      POSTGRES_PASSWORD: pn_secret
    ports: ["5433:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  
  api:
    build: .
    ports: ["8090:8000"]
    environment:
      DATABASE_URL: postgresql+asyncpg://pn_user:pn_secret@db:5432/plan_naryad
    depends_on: [db]

volumes:
  pgdata:
```

### 6. Dockerfile
Python 3.12 slim, install requirements, run uvicorn.

## Important Notes
- Use async SQLAlchemy (asyncpg)
- Use Alembic for migrations (generate initial migration from models)
- Swagger UI auto-generated by FastAPI at /docs
- All IDs are UUIDs
- Dates in ISO format
- Russian comments in code where it helps clarity
- The app should START and WORK out of the box with `docker compose up`
- Seed data should auto-populate on first run

## What NOT to build yet
- Telegram bot (Phase 2)
- Frontend UI (Phase 2)
- Real ISUP integration (Phase 3)
- Email delivery (Phase 3)

When completely finished, run this command to notify me:
openclaw system event --text "Done: Plan-Naryad MVP backend built — FastAPI + PostgreSQL + auto-generation + reconciliation + alerts + mock data + Docker Compose. Ready to deploy." --mode now
