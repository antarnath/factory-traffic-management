"""
FastAPI application entry point.

Run locally:
    cd backend
    source venv/bin/activate
    uvicorn app.main:app --reload --port 8000

Open http://127.0.0.1:8000/docs for the auto-generated Swagger UI.
"""
from fastapi import FastAPI

from app.config import settings
from app.errors import register_exception_handlers


def create_app() -> FastAPI:
    app = FastAPI(
        title="Factory Traffic Management API",
        version="1.0.0",
        description="Backend for the factory traffic-management assessment.",
        debug=settings.debug,
    )

    register_exception_handlers(app)

    @app.get("/health", tags=["meta"])
    def health():
        return {"status": "ok", "app": settings.app_name}

    return app


# uvicorn looks for a module-level `app` object.
app = create_app()
