"""Health, catalog and model routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from models.contracts import ASSET_CATEGORIES, CONTRACT_VERSION, PIPELINE_TYPES
from models.registry import build_catalog

from ..errors import api_error
from ..schemas import Health, ModelList
from .common import respond, service

router = APIRouter()


@router.get("/health")
def health(request: Request):
    return respond(
        Health(status="ok", contract_version=CONTRACT_VERSION, compute_mode=service(request).client.mode)
    )


@router.get("/catalog")
def catalog():
    return respond(build_catalog())


@router.get("/models")
def list_models(request: Request):
    pipeline = request.query_params.get("pipeline_type") or None
    category = request.query_params.get("asset_category") or None
    if pipeline is not None and pipeline not in PIPELINE_TYPES:
        raise api_error(422, "PIPELINE_UNKNOWN", "pipeline_type", f"Unknown pipeline '{pipeline}'.")
    if category is not None and category not in ASSET_CATEGORIES:
        raise api_error(
            422, "ASSET_CATEGORY_UNKNOWN", "asset_category", f"Unknown asset category '{category}'."
        )
    models = service(request).registry.list(pipeline, category)
    return respond(ModelList(contract_version=CONTRACT_VERSION, models=models))


@router.get("/models/{model_id}")
def get_model(model_id: str, request: Request):
    record = service(request).registry.get(model_id)
    if record is None:
        raise api_error(404, "MODEL_NOT_FOUND", "model_id", f"Model '{model_id[:64]}' does not exist.")
    return respond(record)
