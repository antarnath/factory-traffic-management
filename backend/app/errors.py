"""
Domain exceptions and global FastAPI exception handlers.

Every error response uses the same envelope:

    {"error": {"code": "string", "message": "human readable", "details": {...}}}

This keeps the API uniform and easy to consume from Postman / frontend.
"""
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException


class DomainError(Exception):
    """Base class for application-level errors that map to HTTP responses."""

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class JunctionNotFound(DomainError):
    status_code = 404
    code = "junction_not_found"


class UnsafeTransition(DomainError):
    status_code = 409
    code = "unsafe_transition"


def _envelope(code: str, message: str, status_code: int, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError):
        return _envelope(exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException):
        """Wrap default 4xx/5xx responses in our uniform envelope."""
        code_map = {
            400: "bad_request",
            401: "unauthorized",
            403: "forbidden",
            404: "not_found",
            405: "method_not_allowed",
            409: "conflict",
            422: "unprocessable_entity",
        }
        return _envelope(
            code_map.get(exc.status_code, "http_error"),
            str(exc.detail) if exc.detail else "HTTP error",
            exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError):
        return _envelope(
            "validation_error",
            "Request validation failed.",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"errors": exc.errors()},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_: Request, exc: IntegrityError):
        return _envelope(
            "integrity_error",
            "Database integrity violation.",
            status.HTTP_409_CONFLICT,
            {"raw": str(exc.orig)},
        )

    @app.exception_handler(SQLAlchemyError)
    async def sql_handler(_: Request, exc: SQLAlchemyError):
        return _envelope(
            "database_error",
            "Database operation failed.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"type": type(exc).__name__, "detail": str(exc)[:200]},
        )

    @app.exception_handler(Exception)
    async def fallback_handler(_: Request, exc: Exception):
        return _envelope(
            "internal_error",
            "Unexpected server error.",
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"type": type(exc).__name__},
        )
