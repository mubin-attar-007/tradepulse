"""Domain exception hierarchy + RFC 9457 (problem+json) error handlers.

Domain code raises :class:`AppError` subclasses; handlers render a stable
``application/problem+json`` body. Unhandled exceptions are logged and return
a generic 500 (never leak internals).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_var
from app.core.logging import get_logger

logger = get_logger("errors")
PROBLEM_JSON = "application/problem+json"


class AppError(Exception):
    status_code: int = 500
    title: str = "Internal Server Error"
    code: str = "internal_error"

    def __init__(self, detail: str | None = None, *, extra: dict[str, Any] | None = None) -> None:
        self.detail = detail or self.title
        self.extra = extra or {}
        super().__init__(self.detail)


class BadRequestError(AppError):
    status_code, title, code = 400, "Bad Request", "bad_request"


class AuthenticationError(AppError):
    status_code, title, code = 401, "Authentication Required", "unauthenticated"


class PermissionDeniedError(AppError):
    status_code, title, code = 403, "Permission Denied", "forbidden"


class NotFoundError(AppError):
    status_code, title, code = 404, "Not Found", "not_found"


class ConflictError(AppError):
    status_code, title, code = 409, "Conflict", "conflict"


class RateLimitedError(AppError):
    status_code, title, code = 429, "Too Many Requests", "rate_limited"


def _problem(
    status: int,
    title: str,
    code: str,
    detail: str,
    request: Request,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": f"about:blank#{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    if (rid := request_id_var.get()) is not None:
        body["request_id"] = rid
    if extra:
        body.update(extra)
    return JSONResponse(status_code=status, content=jsonable_encoder(body), media_type=PROBLEM_JSON)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _problem(exc.status_code, exc.title, exc.code, exc.detail, request, exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        title = exc.detail if isinstance(exc.detail, str) else "HTTP Error"
        return _problem(exc.status_code, title, f"http_{exc.status_code}", title, request)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _problem(
            422,
            "Validation Error",
            "validation_error",
            "Request validation failed.",
            request,
            {"errors": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_exception", error=str(exc), path=request.url.path)
        return _problem(
            500, "Internal Server Error", "internal_error", "An unexpected error occurred.", request
        )
