"""
FastAPI application entry point.

Run locally:
    cd backend
    source venv/bin/activate
    uvicorn app.main:app --reload --port 8000

Open http://127.0.0.1:8000/ for the dashboard, or
http://127.0.0.1:8000/docs for the auto-generated Swagger UI.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import register_routers
from app.config import settings
from app.errors import register_exception_handlers

# Project root is two levels up from app/main.py (app/main.py → app/ → backend/).
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Factory Traffic Management API",
        version="1.0.0",
        description="Backend for the factory traffic-management assessment.",
        debug=settings.debug,
    )

    register_exception_handlers(app)
    register_routers(app)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok", "app": settings.app_name}

    # Serve the frontend dashboard from /. API routes are registered first
    # so they win on any path collision.
    if FRONTEND_DIR.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(FRONTEND_DIR), html=True),
            name="frontend",
        )

    return app


# uvicorn looks for a module-level `app` object.
app = create_app()
