"""ErrorResponse handling (docs/CONTRACTS.md §5.2). Never returns stack traces."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from models.contracts import CONTRACT_VERSION, ErrorItem, error

log = logging.getLogger("aas_backend")


class ApiError(Exception):
    def __init__(self, status: int, errors: Iterable[ErrorItem], warnings: Iterable[ErrorItem] = ()) -> None:
        self.status = status
        self.errors = list(errors)
        self.warnings = list(warnings)
        super().__init__(", ".join(e.code for e in self.errors))


def api_error(
    status: int,
    code: str,
    field: str | None,
    message: str,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> ApiError:
    return ApiError(status, [error(code, field, message, details, retryable)])


def path_invalid(kind: str, value: str) -> ApiError:
    log.warning("security: rejected invalid %s in request path: %r", kind, value[:80])
    return api_error(400, "PATH_INVALID", None, f"Invalid {kind}.")


def error_response(
    status: int, errors: Iterable[ErrorItem], warnings: Iterable[ErrorItem] = ()
) -> JSONResponse:
    body = {
        "contract_version": CONTRACT_VERSION,
        "warnings": [w.model_dump(mode="json") for w in warnings],
        "errors": [e.model_dump(mode="json") for e in errors],
    }
    return JSONResponse(body, status_code=status)


def _location(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in ("query", "path", "body")]
    return ".".join(parts) or None


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.errors, exc.warnings)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        items = [
            error(
                "REQUEST_FIELD_INVALID", _location(tuple(e.get("loc", ()))), f"Invalid value: {e.get('msg')}."
            )
            for e in exc.errors()
        ]
        return error_response(422, items)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if exc.status_code == 404:
            return error_response(404, [error("PATH_INVALID", None, "No such endpoint.")])
        if exc.status_code == 405:
            return error_response(405, [error("REQUEST_FIELD_INVALID", None, "Method not allowed.")])
        return error_response(exc.status_code, [error("REQUEST_FIELD_INVALID", None, str(exc.detail))])

    @app.middleware("http")
    async def _internal_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            log.exception("internal error on %s %s", request.method, request.url.path)
            return error_response(
                500, [error("INTERNAL_ERROR", None, "Internal error. Details are in the local log.")]
            )
