"""Two-phase upload routes (docs/CONTRACTS.md §3.1)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from models.contracts import MAX_UPLOAD_BYTES

from ..errors import api_error
from .common import file_response, require_id, respond, service

router = APIRouter()
_MULTIPART_OVERHEAD = 1 << 20


class _BodyTooLarge(Exception):
    pass


def _too_large():
    return api_error(
        413,
        "UPLOAD_TOO_LARGE",
        "file",
        f"The file is larger than the {MAX_UPLOAD_BYTES}-byte limit.",
        {"max_upload_bytes": MAX_UPLOAD_BYTES},
    )


def _limited(request: Request, limit: int) -> Request:
    """The same request, but reading stops as soon as the body passes ``limit`` bytes.

    This also covers bodies without a Content-Length header (chunked transfer), so an oversized file is never
    read to the end or spooled to disk in full.
    """
    received = 0

    async def receive():
        nonlocal received
        message = await request.receive()
        if message["type"] == "http.request":
            received += len(message.get("body", b""))
            if received > limit:
                raise _BodyTooLarge
        return message

    return Request(request.scope, receive)


@router.post("/uploads")
async def create_upload(request: Request):
    if not request.headers.get("content-type", "").startswith("multipart/form-data"):
        raise api_error(
            400, "REQUEST_FIELD_INVALID", "file", "Send the image as multipart/form-data field 'file'."
        )
    limit = MAX_UPLOAD_BYTES + _MULTIPART_OVERHEAD
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > limit:
        raise _too_large()
    try:
        form = await _limited(request, limit).form(max_files=1, max_fields=4)
    except _BodyTooLarge:
        raise _too_large() from None
    except Exception as exc:
        raise api_error(
            400, "REQUEST_FIELD_INVALID", "file", "Malformed multipart body (send exactly one file)."
        ) from exc
    try:
        files = form.getlist("file")
        if len(files) != 1 or not isinstance(files[0], UploadFile) or set(form.keys()) != {"file"}:
            raise api_error(
                400, "REQUEST_FIELD_INVALID", "file", "Send exactly one multipart field named 'file'."
            )
        upload: UploadFile = files[0]
        record = await run_in_threadpool(service(request).uploads.save, upload.file, upload.filename)
    finally:
        await form.close()
    return respond(record, 201)


def _staged(request: Request, upload_id: str):
    require_id("upload_id", upload_id)
    staged = service(request).uploads.get(upload_id)
    if staged is None:
        raise api_error(404, "UPLOAD_NOT_FOUND", "upload_id", "Upload not found or expired.")
    return staged


@router.get("/uploads/{upload_id}")
def get_upload(upload_id: str, request: Request):
    return respond(_staged(request, upload_id).record)


@router.get("/uploads/{upload_id}/content")
def get_upload_content(upload_id: str, request: Request):
    staged = _staged(request, upload_id)
    svc = service(request)
    relative = staged.path.resolve().relative_to(svc.data_root).as_posix()
    ext = staged.path.suffix.lstrip(".")
    return file_response(svc, relative, staged.record.mime_type, f"{upload_id}.{ext}", download=False)


@router.delete("/uploads/{upload_id}")
def delete_upload(upload_id: str, request: Request):
    require_id("upload_id", upload_id)
    service(request).delete_upload(upload_id)
    return Response(status_code=204)
