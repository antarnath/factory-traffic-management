# Factory Traffic Management — Backend

FastAPI + SQLAlchemy + (PostgreSQL/MySQL/SQLite) backend for the
factory traffic-management assessment.

The whole project lives in `../`. This README covers only the backend.

## Project layout

```
backend/
├── app/
│   ├── main.py                # FastAPI app, exception handlers, router registration
│   ├── config.py              # pydantic-settings (reads .env)
│   ├── db.py                  # SQLAlchemy engine + get_db dependency
│   ├── errors.py              # Domain exceptions + global handlers
│   ├── models/                # SQLAlchemy ORM (junction, signal, queue_entry, ...)
│   ├── schemas/               # Pydantic v2 request/response models
│   ├── controllers/           # Controller adapter pattern (REST sim, MQTT later)
│   │   ├── base.py            # Abstract ControllerAdapter interface
│   │   └── rest_simulator.py  # In-process simulator (singleton)
│   ├── services/              # Domain logic + glue
│   │   ├── safety.py          # Pure-Python: GREEN/RED/YELLOW invariants
│   │   ├── transitions.py     # Pure-Python: GREEN→YELLOW→ALL_RED→GREEN planner
│   │   ├── scheduler.py       # Pure-Python: weighted priority + starvation bonus
│   │   ├── state_machine.py   # Pure-Python: AUTOMATIC/MANUAL/EMERGENCY/DEGRADED
│   │   ├── queue.py           # DirectionQueue aggregation
│   │   ├── concurrency.py     # Per-junction SELECT FOR UPDATE
│   │   ├── events.py          # Vehicle / device / controller event handlers
│   │   ├── manual.py          # MANUAL_GREEN_REQUEST, RETURN_TO_AUTOMATIC
│   │   ├── timeouts.py        # Manual override expiry + controller ACK timeouts
│   │   ├── reconcile.py       # Desired/actual drift detection
│   │   ├── status.py          # Read-only status snapshot for the dashboard
│   │   └── orchestrator.py    # The single place that wires domain→DB→controller
│   └── api/                   # FastAPI routers
│       ├── junctions.py       # /api/junctions  (list/get/create/step/status)
│       ├── sensor_events.py   # /api/sensor-events, /api/device-events
│       ├── controller_events.py # /api/controller-events, manual commands
│       ├── history.py         # /api/junctions/{id}/history
│       └── maintenance.py     # /api/maintenance/tick
├── alembic/                   # Migrations
├── scripts/
│   ├── seed_junction_a.py     # Idempotent default junction A + 4 signal heads
│   └── recover_startup.py     # One-shot startup recovery (force RED, expire overrides)
├── tests/                     # pytest
├── postman/                   # Postman collection for manual API exploration
├── .env                       # not committed
├── .env.example               # committed
├── requirements.txt
└── README.md                  # this file
```

## Quick start

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env             # then edit DB_URL
alembic upgrade head             # create the tables
python -m scripts.seed_junction_a
python -m scripts.recover_startup   # optional: clear stale state from a previous run
uvicorn app.main:app --reload --port 8000
```

Open <http://127.0.0.1:8000/docs> for the auto-generated Swagger UI.

## Choosing a database

The default `.env.example` uses SQLite so you can run everything
without installing a database server:

```
DB_URL=sqlite:///./factory_traffic.db
```

For a production-like setup, switch to PostgreSQL:

```bash
# Install PostgreSQL (Ubuntu/Debian)
sudo apt install postgresql
sudo -u postgres createuser traffic_user -P
sudo -u postgres createdb factory_traffic_db -O traffic_user

# Update .env
DB_URL=postgresql+psycopg://traffic_user:your_password@127.0.0.1:5432/factory_traffic_db

# Re-run migrations
alembic upgrade head
```

(MySQL is also supported via `mysql+pymysql://...`.)

## REST endpoints (spec §10)

| Method | Path                                  | Purpose                              |
| ------ | ------------------------------------- | ------------------------------------ |
| GET    | `/api/junctions`                      | List junctions                       |
| GET    | `/api/junctions/{id}`                 | Get one junction                     |
| POST   | `/api/junctions`                      | Create a junction (idempotent)       |
| GET    | `/api/junctions/{id}/status`          | Full status snapshot (dashboard)     |
| POST   | `/api/junctions/{id}/step`            | Force one decision cycle             |
| GET    | `/api/junctions/{id}/history`         | Paginated audit log                  |
| POST   | `/api/sensor-events`                  | Ingest VEHICLE_ARRIVED / CLEARED     |
| POST   | `/api/device-events`                  | Ingest device status changes         |
| POST   | `/api/controller-events`              | Ingest ACK / NACK / TIMEOUT          |
| POST   | `/api/junctions/{id}/commands`        | Manual override                      |
| POST   | `/api/junctions/{id}/simulate-controller` | Dev-only: controller online/offline |
| POST   | `/api/maintenance/tick`               | One maintenance tick                 |
| GET    | `/health`                             | Liveness                             |

## Running tests

```bash
cd backend
source venv/bin/activate
pytest -q
```

Tests use a file-based SQLite database (see `tests/conftest.py`),
so no separate DB setup is needed. The conftest wipes the tables
between tests for isolation.

## Postman

`postman/Factory_Traffic.postman_collection.json` is a ready-made
collection with one request per endpoint and a few scripted scenarios
(emergency preemption, manual override, recovery). Import it into
Postman, set the `base_url` variable to `http://127.0.0.1:8000`, and
run "Run collection" against a running backend.

## Milestone status

- [x] **Milestone 1** — Project setup, DB models, Pydantic schemas, error handling,
      smoke tests, Alembic migrations, seed script.
- [x] **Milestone 2** — Pure-Python traffic domain logic (safety, transitions,
      scheduler, state machine). 31 unit tests.
- [x] **Milestone 3** — REST endpoints, sensor ingestion, controller adapter,
      orchestrator, status, manual override, timeouts, reconciliation, recovery.
      15 integration tests covering all 9 spec scenarios.
- [x] **Milestone 4** — Maintenance tick, recovery script, postman collection,
      README, updated conftest with per-test isolation.

## Error envelope

Every error response uses the same shape:

```json
{
  "error": {
    "code": "string",
    "message": "human readable",
    "details": { ... }
  }
}
```

`code` values: `validation_error`, `not_found`, `junction_not_found`,
`unsafe_transition`, `integrity_error`, `database_error`, `internal_error`.

## Architecture notes

- **Domain services are pure Python.** `safety.py`, `transitions.py`,
  `scheduler.py`, `state_machine.py` and `queue.py` have no imports
  from `fastapi`, `sqlalchemy`, or `app.db`. They take plain
  dataclasses and return plain dataclasses. This means the entire
  safety story can be unit-tested without spinning up a database.

- **The orchestrator is the only place that mixes domain and DB.**
  `step_junction` builds a `JunctionSnapshot`, calls `next_action`,
  then mutates `Signal` / `Junction` / `PendingCommand` rows and
  sends controller commands. Every other service is a leaf.

- **Per-junction locking.** `junction_lock(db, junction_id)` opens a
  transaction and does `SELECT ... FOR UPDATE` on the junction row
  (a no-op on SQLite; real on PostgreSQL/MySQL). All event handlers
  acquire this lock before touching junction-scoped data.

- **Idempotency is enforced at the DB level.** `QueueEntry.event_id`
  has a UNIQUE constraint; the second insert fails with
  `IntegrityError` and is reported as `already_processed`.

- **Transitions are step-by-step.** The orchestrator applies only
  the *first* step of `plan_transition` (YELLOW or ALL_RED), and
  the next event / ACK advances it. This keeps the system consistent
  when many events arrive close together.

## End-to-end demo script

```bash
# Terminal 1: backend
cd backend
source venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2: drive the API with curl
J='http://127.0.0.1:8000'

# 1. Create junction A
curl -sX POST $J/api/junctions -H 'Content-Type: application/json' \
     -d '{"id": "A", "name": "Main"}'

# 2. Send a vehicle event
curl -sX POST $J/api/sensor-events -H 'Content-Type: application/json' \
     -d '{"event_id": "e1", "junction_id": "A", "direction": "NORTH",
          "event_type": "VEHICLE_ARRIVED", "vehicle_id": "v1",
          "vehicle_type": "TRUCK", "sequence_no": 1,
          "timestamp": "2026-10-08T12:00:00+00:00"}'

# 3. Watch the dashboard
curl -s $J/api/junctions/A/status | jq

# 4. Manually force WEST green
curl -sX POST $J/api/junctions/A/commands -H 'Content-Type: application/json' \
     -d '{"command": "MANUAL_GREEN_REQUEST", "direction": "WEST"}'

# 5. Send an emergency — it preempts everything
curl -sX POST $J/api/sensor-events -H 'Content-Type: application/json' \
     -d '{"event_id": "e2", "junction_id": "A", "direction": "EAST",
          "event_type": "VEHICLE_ARRIVED", "vehicle_id": "amb",
          "vehicle_type": "EMERGENCY", "sequence_no": 2,
          "timestamp": "2026-10-08T12:00:01+00:00"}'

# 6. Inspect audit log
curl -s "$J/api/junctions/A/history?limit=20" | jq

# 7. Run one maintenance tick
curl -sX POST $J/api/maintenance/tick | jq
```
