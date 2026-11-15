"""Standardized error responses shared by every endpoint.

Shape: {"error": {"code": <int>, "message": <str>, "details": <any>, "correlation_id": <str>}}
"""
import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.logging_config import correlation_id_var

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Raise from a route to return a standard error with optional structured details."""

    def __init__(self, status_code: int, message: str, details=None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details


def error_body(code: int, message: str, details=None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "correlation_id": correlation_id_var.get(),
        }
    }


def not_implemented() -> HTTPException:
    """Placeholder for endpoints defined in the API contract but not built yet."""
    return HTTPException(status_code=status.HTTP_501_NOT_IMPLEMENTED, detail="Not implemented yet")


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        body = error_body(exc.status_code, exc.message, exc.details)
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(status_code=exc.status_code, content=error_body(exc.status_code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [
            {"field": ".".join(str(p) for p in err["loc"]), "message": err["msg"]} for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_body(422, "Request validation failed", details),
        )

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_: Request, exc: SQLAlchemyError):
        # The engine uses hide_parameters=True, so this never logs query values.
        logger.error("Database error", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=error_body(503, "Database temporarily unavailable"),
        )
