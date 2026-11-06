"""Validation and job routes (docs/CONTRACTS.md §5)."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

from models.contracts import CONTRACT_VERSION, JOB_STATUSES, PIPELINE_TYPES, TERMINAL_STATUSES

from ..errors import api_error
from ..orchestrator.records import artifact_view, to_result, to_summary
from ..schemas import ArtifactList, JobList, JobStatusView, LogLine, LogPage
from .common import file_response, flag_query, int_query, json_body, require_id, respond, service

router = APIRouter()


@router.post("/validate")
async def validate(request: Request):
    body = await json_body(request)
    return respond(service(request).validate(body).report)


@router.post("/jobs")
async def create_job(request: Request):
    body = await json_body(request)
    record, _ = service(request).create_job(body)
    return respond(to_result(record), 201)


@router.get("/jobs")
def list_jobs(request: Request):
    status = request.query_params.get("status") or None
    pipeline = request.query_params.get("pipeline_type") or None
    if status is not None and status not in JOB_STATUSES:
        raise api_error(422, "REQUEST_FIELD_INVALID", "status", f"Unknown job status '{status}'.")
    if pipeline is not None and pipeline not in PIPELINE_TYPES:
        raise api_error(422, "PIPELINE_UNKNOWN", "pipeline_type", f"Unknown pipeline '{pipeline}'.")
    limit = int_query(request, "limit", 50, 1, 200)
    records, next_cursor = service(request).list_jobs(
        status, pipeline, limit, request.query_params.get("cursor")
    )
    return respond(
        JobList(
            contract_version=CONTRACT_VERSION, jobs=[to_summary(r) for r in records], next_cursor=next_cursor
        )
    )


def _job(request: Request, job_id: str):
    require_id("job_id", job_id)
    return service(request).require(job_id)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    return respond(to_result(_job(request, job_id)))


@router.get("/jobs/{job_id}/status")
def get_status(job_id: str, request: Request):
    record = _job(request, job_id)
    return respond(
        JobStatusView(
            contract_version=CONTRACT_VERSION,
            job_id=record.job_id,
            status=record.status,
            updated_at=record.updated_at,
            progress=record.internal.progress,
        )
    )


@router.get("/jobs/{job_id}/logs")
def get_logs(job_id: str, request: Request):
    record = _job(request, job_id)
    offset = int_query(request, "offset", 0, 0, 10**9)
    limit = int_query(request, "limit", 500, 1, 1000)
    rows, next_offset, total = service(request).logs.read(job_id, offset, limit)
    lines = [LogLine.model_validate(row) for row in rows]
    complete = record.status in TERMINAL_STATUSES and next_offset >= total
    return respond(
        LogPage(contract_version=CONTRACT_VERSION, lines=lines, next_offset=next_offset, complete=complete)
    )


@router.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str, request: Request):
    require_id("job_id", job_id)
    body = await json_body(request)
    record, _ = service(request).retry(job_id, body)
    return respond(to_result(record), 201)


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str, request: Request):
    require_id("job_id", job_id)
    service(request).delete_job(job_id)
    return Response(status_code=204)


@router.get("/jobs/{job_id}/inputs/{input_id}/content")
def get_input(job_id: str, input_id: str, request: Request):
    require_id("input_id", input_id)
    record = _job(request, job_id)
    item = next((i for i in record.request.inputs if i.input_id == input_id), None)
    if item is None:
        raise api_error(404, "ARTIFACT_NOT_FOUND", None, "Input not found.")
    ext = item.path.rsplit(".", 1)[-1]
    return file_response(
        service(request), item.path, item.mime_type, f"{job_id}_{input_id}.{ext}", download=False
    )


@router.get("/jobs/{job_id}/artifacts")
def list_artifacts(job_id: str, request: Request):
    record = _job(request, job_id)
    return respond(
        ArtifactList(
            contract_version=CONTRACT_VERSION, artifacts=[artifact_view(job_id, a) for a in record.artifacts]
        )
    )


@router.get("/jobs/{job_id}/artifacts/{artifact_id}/content")
def get_artifact(job_id: str, artifact_id: str, request: Request):
    require_id("artifact_id", artifact_id)
    record = _job(request, job_id)
    download = flag_query(request, "download")
    artifact = next((a for a in record.artifacts if a.artifact_id == artifact_id), None)
    if artifact is None:
        raise api_error(404, "ARTIFACT_NOT_FOUND", None, "Artifact not found.")
    return file_response(
        service(request),
        artifact.path,
        artifact.mime_type,
        f"{job_id}_{artifact_id}.{artifact.format}",
        download=download,
    )
