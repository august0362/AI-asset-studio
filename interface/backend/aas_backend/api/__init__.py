"""REST API under ``/api/v1`` (docs/CONTRACTS.md §5)."""

from fastapi import APIRouter

from . import compute, jobs, system, uploads

API_PREFIX = "/api/v1"

router = APIRouter(prefix=API_PREFIX)
for module in (system, uploads, jobs, compute):
    router.include_router(module.router)

__all__ = ["API_PREFIX", "router"]
