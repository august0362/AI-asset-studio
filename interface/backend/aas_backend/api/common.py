"""Shared helpers for route modules."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from ..errors import api_error, path_invalid
from ..orchestrator.service import JobService
from ..storage.paths import PathInvalid, is_valid_id, safe_path


def service(request: Request) -> JobService:
    return request.app.state.service


def respond(model: BaseModel, status: int = 200) -> JSONResponse:
    return JSONResponse(model.model_dump(mode="json"), status_code=status)


def require_id(kind: str, value: str) -> str:
    if not is_valid_id(kind, value):
        raise path_invalid(kind, value)
    return value


async def json_body(request: Request) -> object:
    raw = await request.body()
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise api_error(400, "REQUEST_FIELD_INVALID", None, "The request body is not valid JSON.") from exc


def int_query(request: Request, name: str, default: int, minimum: int, maximum: int) -> int:
    value = request.query_params.get(name)
    if value is None:
        return default
    try:
        number = int(value)
    except ValueError:
        number = None
    if number is None or not minimum <= number <= maximum:
        raise api_error(
            422, "REQUEST_FIELD_INVALID", name, f"'{name}' must be an integer from {minimum} to {maximum}."
        )
    return number


def flag_query(request: Request, name: str) -> bool:
    value = request.query_params.get(name, "0")
    if value not in ("0", "1"):
        raise api_error(422, "REQUEST_FIELD_INVALID", name, f"'{name}' must be 0 or 1.")
    return value == "1"


def file_response(
    svc: JobService, relative: str, media_type: str, filename: str, download: bool
) -> FileResponse:
    try:
        path: Path = safe_path(svc.data_root, relative)
    except PathInvalid as exc:
        raise path_invalid("path", relative) from exc
    if not path.is_file():
        raise api_error(404, "ARTIFACT_NOT_FOUND", None, "The file is missing.")
    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type="attachment" if download else "inline",
    )
