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


CHARACTER_ROUTES = "/api/v1/characters"


def version_for(request: Request | None) -> str:
    """Character Production routes (§13) answer with contract 1.1 envelopes; every v1 route keeps 1.0."""
    return (
        "1.1" if request is not None and request.url.path.startswith(CHARACTER_ROUTES) else CONTRACT_VERSION
    )


def error_response(
    status: int,
    errors: Iterable[ErrorItem],
    warnings: Iterable[ErrorItem] = (),
    version: str = CONTRACT_VERSION,
) -> JSONResponse:
    body = {
        "contract_version": version,
        "warnings": [w.model_dump(mode="json") for w in warnings],
        "errors": [e.model_dump(mode="json") for e in errors],
    }
    return JSONResponse(body, status_code=status)


def _location(loc: tuple[Any, ...]) -> str | None:
    parts = [str(p) for p in loc if p not in ("query", "path", "body")]
    return ".".join(parts) or None


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> JSONResponse:
        return error_response(exc.status, exc.errors, exc.warnings, version_for(request))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        items = [
            error(
                "REQUEST_FIELD_INVALID", _location(tuple(e.get("loc", ()))), f"Invalid value: {e.get('msg')}."
            )
            for e in exc.errors()
        ]
        return error_response(422, items, version=version_for(request))

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        version = version_for(request)
        if exc.status_code == 404:
            return error_response(404, [error("PATH_INVALID", None, "No such endpoint.")], version=version)
        if exc.status_code == 405:
            return error_response(
                405, [error("REQUEST_FIELD_INVALID", None, "Method not allowed.")], version=version
            )
        return error_response(
            exc.status_code, [error("REQUEST_FIELD_INVALID", None, str(exc.detail))], version=version
        )

    @app.middleware("http")
    async def _internal_errors(request: Request, call_next):
        try:
            return await call_next(request)
        except Exception:
            log.exception("internal error on %s %s", request.method, request.url.path)
            return error_response(
                500,
                [error("INTERNAL_ERROR", None, "Internal error. Details are in the local log.")],
                version=version_for(request),
            )
