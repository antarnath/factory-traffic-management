# Factory Traffic Management System

A small event-driven control system for traffic signals at internal
factory-road intersections. Receives vehicle-detection events, manages
queues per direction, controls traffic signals safely, allows manual
admin overrides, handles emergency vehicles, and survives device failures.

## Repository layout

```
Factory-Traffic-Management/
├── backend/                  # FastAPI + SQLAlchemy + MySQL/PostgreSQL/SQLite
│   ├── app/                  # FastAPI app, models, schemas, services
│   ├── alembic/              # Migrations
│   ├── scripts/              # Seed, recovery, etc.
│   ├── tests/                # pytest
│   ├── README.md             # backend-specific docs
│   ├── .env.example          # environment template
│   └── requirements.txt
├── frontend/                 # Dashboard — currently empty
│   ├── README.md             # describes what goes here
│   └── .gitkeep
├── phases/                   # Step-by-step implementation plan
│   ├── phase-1-project-setup.md
│   ├── phase-2-traffic-domain-logic.md
│   ├── phase-3-apis-sensors-controllers.md
│   └── phase-4-manual-audit-recovery.md
└── Factory_Traffic_Management_Backend_Developer_Intern_Assessment_V2.pdf
```

## Quickstart (backend)

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # edit DB_URL if needed
alembic upgrade head
python -m scripts.seed_junction_a
uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000/docs> for the auto-generated Swagger UI.

See `backend/README.md` for the full backend reference.

## Implementation plan

The work is split into 4 phases — see `phases/`:

1. **Phase 1** — Project setup, DB models, Pydantic schemas, error envelope,
   smoke tests, Alembic migrations, seed script.
2. **Phase 2** — Pure-Python traffic domain logic: safety invariants,
   safe transitions, scheduler, state machine.
3. **Phase 3** — REST endpoints, sensor ingestion, controller adapter.
4. **Phase 4** — Manual overrides, audit, recovery, concurrency tests, README.

## Frontend

The `frontend/` folder is intentionally blank during the assessment.
The dashboard will be added later — see `frontend/README.md` for what
will go there.

**Hard rule:** the frontend must never decide traffic sequencing on its
own. Every signal change comes from the backend; the UI only reflects
backend state.
