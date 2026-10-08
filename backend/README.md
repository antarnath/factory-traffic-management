# Factory Traffic Management — Backend

FastAPI + SQLAlchemy + MySQL/PostgreSQL/SQLite backend for the
factory traffic-management assessment.

The whole project lives in `../`. This README covers only the backend.

## Project layout

```
backend/
├── app/
│   ├── main.py                # FastAPI app
│   ├── config.py              # pydantic-settings (reads .env)
│   ├── db.py                  # SQLAlchemy engine + get_db dependency
│   ├── errors.py              # Domain exceptions + global handlers
│   ├── models/                # SQLAlchemy ORM (junction, signal, queue_entry, ...)
│   ├── schemas/               # Pydantic v2 request/response models
│   ├── services/              # Domain logic (filled in Phase 2)
│   ├── controllers/           # Controller adapter pattern (filled in Phase 3)
│   └── api/                   # FastAPI routers (filled in Phase 3)
├── alembic/                   # Migrations
├── scripts/                   # Standalone scripts (seed, recover, ...)
├── tests/                     # pytest
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

## Running tests

```bash
cd backend
source venv/bin/activate
pytest -q
```

Tests use an in-memory SQLite database (see `tests/conftest.py`),
so no separate DB setup is needed.

## Phase status

- [x] **Phase 1** — Project setup, DB models, Pydantic schemas, error handling,
      smoke tests, Alembic migrations, seed script.
- [ ] **Phase 2** — Pure-Python traffic domain logic (safety, transitions, scheduler, state machine).
- [ ] **Phase 3** — REST endpoints, sensor ingestion, controller adapter.
- [ ] **Phase 4** — Manual overrides, audit, recovery, concurrency tests, README.

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
