# Factory Traffic Management System

A small event-driven control system for traffic signals at internal
factory-road intersections. Receives vehicle-detection events, manages
queues per direction, controls traffic signals safely, allows manual
admin overrides, handles emergency vehicles, and survives device failures.

## Status

All four implementation milestones are complete and **67 tests pass**:

- **Milestone 1** — Project setup, DB models, Pydantic schemas, error envelope,
  smoke tests, Alembic migrations, seed script.
- **Milestone 2** — Pure-Python traffic domain logic: safety invariants,
  safe transitions, scheduler, state machine. 31 unit tests.
- **Milestone 3** — REST endpoints, sensor ingestion, controller adapter,
  orchestrator, status, manual override, timeouts, reconciliation,
  recovery. 15 integration tests covering all 9 spec scenarios.
- **Milestone 4** — Maintenance tick, recovery script, postman collection,
  README, per-test isolation, end-to-end demo.

Run `cd backend && pytest -q` to verify.

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

The work is split into 4 milestones — see `phases/`:

1. **Milestone 1** — Project setup, DB models, Pydantic schemas, error envelope,
   smoke tests, Alembic migrations, seed script.
2. **Milestone 2** — Pure-Python traffic domain logic: safety invariants,
   safe transitions, scheduler, state machine.
3. **Milestone 3** — REST endpoints, sensor ingestion, controller adapter.
4. **Milestone 4** — Manual overrides, audit, recovery, concurrency tests, README.

## Frontend

The `frontend/` folder is intentionally blank during the assessment.
The dashboard will be added later — see `frontend/README.md` for what
will go there.

**Hard rule:** the frontend must never decide traffic sequencing on its
own. Every signal change comes from the backend; the UI only reflects
backend state.

## Assumptions / decisions

| # | Topic | Decision | Why |
|---|-------|----------|-----|
| 1 | Conflicting traffic | Forbidden by invariant check; rejected at transition time. | Spec §3 rule 1. |
| 2 | Max waiting time | 60 s default, then starves to green (10,000 bonus). | Spec §5 starvation requirement. |
| 3 | VEHICLE_CLEARED without arrival | Removes oldest un-cleared entry; logs `CLEARED_WITHOUT_ARRIVAL`. | Reasonable recovery. |
| 4 | Out-of-order events | Ignored if `sequence_no` < last seen for that direction. | Spec §4. |
| 5 | Duplicate `event_id` | Idempotent no-op with audit event. | Spec §4 + §10.2. |
| 6 | Manual override timeout | 60 s default, then auto-revert. | Not specified. |
| 7 | Two admins, simultaneous | Second command wins; first is logged via audit. | First-writer-lost acceptable. |
| 8 | Emergency vs manual | Emergency always wins (state-machine priority 1). | Spec §7 emergency priority. |
| 9 | Controller ACK timeout | 5 s; then DEGRADED (no automatic retry — see timeouts.py). | Reasonable for IoT latency. |
| 10 | Restart during transition | On boot, set actual=RED, clear MANUAL/EMERGENCY, time out stale PENDING. | Spec §12 last paragraph. |
| 11 | Two simultaneous emergencies from conflicting directions | First-arrival wins; second waits. | Spec §17 ambiguity. |
| 12 | Vehicle type unknown | Reject with 422 by Pydantic. | Safer than silent default. |
| 13 | Timestamp authority | Sensor timestamp used for queue ordering; server timestamp used for audit. | Server time is only for our records. |
| 14 | MySQL vs PostgreSQL | Configurable via `DB_URL`; default SQLite for local dev. | Both support `SELECT ... FOR UPDATE`. |
| 15 | Django vs FastAPI | FastAPI chosen; Pydantic v2, native async, free Swagger. | User preference. |
| 16 | Transition application | Only the *first* step of the plan is applied per event; next event advances. | Avoids wall-clock sleeps. |
| 17 | Locking strategy | Per-junction `SELECT FOR UPDATE` (no-op on SQLite, real on PG/MySQL). | Allows independent junctions to run in parallel. |
| 18 | Test isolation | File-based SQLite with per-test table truncation. | In-memory `:memory:` gave connection-per-DB problems. |

## AI Tool Usage

- AI tools were used for: architectural design, code generation, refactoring, and test writing.
- Every code block was read, understood, and tested by the developer.
