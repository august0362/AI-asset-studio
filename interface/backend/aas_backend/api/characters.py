"""Character Production routes 1-19 (docs/CONTRACTS.md §13.6). HTTP mapping only; the rules live in ``characters``."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool

from ..characters.contracts import STAGE_IDS
from ..characters.service import CharacterService
from ..errors import api_error, path_invalid
from .common import file_response, flag_query, int_query, json_body, require_id, respond, service

router = APIRouter()
EDITORIAL_STATUSES = ("not_started", "draft", "in_review", "approved", "needs_revision", "blocked")


def characters(request: Request) -> CharacterService:
    return request.app.state.characters


def _character(character_id: str) -> str:
    return require_id("character_id", character_id)


def _stage(stage_id: str) -> str:
    return require_id("stage_id", stage_id)


@router.get("/characters")
async def list_characters(request: Request):
    stage = request.query_params.get("stage") or None
    status = request.query_params.get("status") or None
    if stage is not None and stage not in STAGE_IDS:
        raise api_error(422, "REQUEST_FIELD_INVALID", "stage", f"Unknown stage '{stage}'.")
    if status is not None and status not in EDITORIAL_STATUSES:
        raise api_error(422, "REQUEST_FIELD_INVALID", "status", f"Unknown status '{status}'.")
    limit = int_query(request, "limit", 50, 1, 100)
    q = (request.query_params.get("q") or "").strip() or None
    cursor = request.query_params.get("cursor") or None
    page = await run_in_threadpool(characters(request).list_characters, q, stage, status, limit, cursor)
    return respond(page)


@router.post("/characters")
async def create_character(request: Request):
    body = await json_body(request)
    return respond(await run_in_threadpool(characters(request).create_character, body), 201)


@router.get("/characters/{character_id}")
async def get_character(character_id: str, request: Request):
    _character(character_id)
    return respond(await run_in_threadpool(characters(request).workflow, character_id))


@router.patch("/characters/{character_id}")
async def update_character(character_id: str, request: Request):
    _character(character_id)
    body = await json_body(request)
    return respond(await run_in_threadpool(characters(request).update_character, character_id, body))


@router.delete("/characters/{character_id}")
async def delete_character(character_id: str, request: Request):
    _character(character_id)
    await run_in_threadpool(characters(request).delete_character, character_id)
    return Response(status_code=204)


@router.get("/characters/{character_id}/stages/{stage_id}")
async def get_stage(character_id: str, stage_id: str, request: Request):
    _character(character_id)
    _stage(stage_id)
    return respond(await run_in_threadpool(characters(request).stage_detail, character_id, stage_id))


@router.put("/characters/{character_id}/stages/{stage_id}/draft")
async def save_draft(character_id: str, stage_id: str, request: Request):
    _character(character_id)
    _stage(stage_id)
    body = await json_body(request)
    return respond(await run_in_threadpool(characters(request).save_draft, character_id, stage_id, body))


@router.post("/characters/{character_id}/stages/{stage_id}/decisions")
async def decide(character_id: str, stage_id: str, request: Request):
    _character(character_id)
    _stage(stage_id)
    body = await json_body(request)
    return respond(await run_in_threadpool(characters(request).decide, character_id, stage_id, body))


@router.get("/characters/{character_id}/stages/{stage_id}/revisions/{revision}")
async def get_revision(character_id: str, stage_id: str, revision: str, request: Request):
    _character(character_id)
    _stage(stage_id)
    if not revision.isdigit() or int(revision) < 1 or len(revision) > 6:
        raise path_invalid("revision", revision)
    return respond(
        await run_in_threadpool(characters(request).revision, character_id, stage_id, int(revision))
    )


@router.get("/characters/{character_id}/history")
async def history(character_id: str, request: Request):
    _character(character_id)
    limit = int_query(request, "limit", 100, 1, 500)
    cursor = request.query_params.get("cursor") or None
    return respond(await run_in_threadpool(characters(request).history, character_id, limit, cursor))


@router.post("/characters/{character_id}/references")
async def create_reference(character_id: str, request: Request):
    _character(character_id)
    body = await json_body(request)
    return respond(await run_in_threadpool(characters(request).create_reference, character_id, body), 201)


@router.get("/characters/{character_id}/references/{reference_id}/content")
async def reference_content(character_id: str, reference_id: str, request: Request):
    _character(character_id)
    require_id("reference_id", reference_id)
    relative, mime, filename = await run_in_threadpool(
        characters(request).reference_content, character_id, reference_id
    )
    return file_response(service(request), relative, mime, filename, download=False)


@router.delete("/characters/{character_id}/references/{reference_id}")
async def delete_reference(character_id: str, reference_id: str, request: Request):
    _character(character_id)
    require_id("reference_id", reference_id)
    await run_in_threadpool(characters(request).delete_reference, character_id, reference_id)
    return Response(status_code=204)


@router.get("/characters/{character_id}/outputs")
async def outputs(character_id: str, request: Request):
    _character(character_id)
    return respond(await run_in_threadpool(characters(request).outputs, character_id))


@router.get("/characters/{character_id}/assets/{asset_id}/content")
async def asset_content(character_id: str, asset_id: str, request: Request):
    _character(character_id)
    require_id("asset_id", asset_id)
    download = flag_query(request, "download")
    relative, filename = await run_in_threadpool(characters(request).asset_content, character_id, asset_id)
    return file_response(service(request), relative, "image/png", filename, download=download)


@router.post("/characters/{character_id}/batches")
async def create_batch(character_id: str, request: Request):
    _character(character_id)
    body = await json_body(request)
    manifest = await run_in_threadpool(characters(request).create_preview_batch, character_id, body)
    return respond(manifest.public(), 201)


@router.get("/characters/{character_id}/batches/{manifest_id}")
async def get_batch(character_id: str, manifest_id: str, request: Request):
    _character(character_id)
    require_id("manifest_id", manifest_id)
    manifest = await run_in_threadpool(characters(request).batch, character_id, manifest_id)
    return respond(manifest.public())


@router.post("/characters/{character_id}/batches/{manifest_id}/submit")
async def submit_batch(character_id: str, manifest_id: str, request: Request):
    _character(character_id)
    require_id("manifest_id", manifest_id)
    body = await json_body(request)
    manifest = await run_in_threadpool(characters(request).submit_batch, character_id, manifest_id, body)
    return respond(manifest.public())


@router.post("/characters/{character_id}/batches/{manifest_id}/retry")
async def retry_batch(character_id: str, manifest_id: str, request: Request):
    _character(character_id)
    require_id("manifest_id", manifest_id)
    body = await json_body(request)
    manifest = await run_in_threadpool(characters(request).retry_batch, character_id, manifest_id, body)
    return respond(manifest.public())
