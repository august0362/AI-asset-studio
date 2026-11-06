"""Compute profile and resource snapshot routes (docs/CONTRACTS.md §6). Never return credentials."""

from __future__ import annotations

from fastapi import APIRouter, Request

from models.contracts import CONTRACT_VERSION

from ..errors import api_error
from ..schemas import ProfileList
from .common import flag_query, respond, service

router = APIRouter()


@router.get("/compute/profiles")
def list_profiles(request: Request):
    return respond(
        ProfileList(contract_version=CONTRACT_VERSION, profiles=service(request).client.profiles())
    )


@router.get("/compute/profiles/{profile_id}/snapshot")
def get_snapshot(profile_id: str, request: Request):
    refresh = flag_query(request, "refresh")
    client = service(request).client
    if profile_id not in {p.profile_id for p in client.profiles() if p.enabled}:
        raise api_error(
            404, "COMPUTE_PROFILE_NOT_FOUND", "profile_id", "Compute profile not found or not enabled."
        )
    return respond(client.snapshot(profile_id, refresh=refresh))
