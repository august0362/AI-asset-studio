"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kaggle_connector.client import ComputeClient, MockKaggleClient
from models.contracts import utc_now
from models.registry import ModelRegistry, default_registry

from .api import router
from .errors import install_error_handlers
from .orchestrator.service import JobService
from .settings import Settings
from .storage.logs import RedactingFilter

log = logging.getLogger("aas_backend")


def build_client(settings: Settings) -> ComputeClient:
    if settings.compute_mode == "kaggle":
        raise RuntimeError("AAS_COMPUTE_MODE=kaggle is implemented in M3. Use AAS_COMPUTE_MODE=mock.")
    return MockKaggleClient(
        scenario=settings.mock_scenario,
        failure=settings.mock_failure,
        queue_seconds=settings.mock_queue_seconds,
        run_seconds=settings.mock_run_seconds,
    )


def create_app(
    settings: Settings | None = None,
    *,
    client: ComputeClient | None = None,
    registry: ModelRegistry | None = None,
    clock: Callable[[], datetime] = utc_now,
) -> FastAPI:
    settings = settings or Settings()
    owns_client = client is None
    compute = client or build_client(settings)
    service = JobService(settings, registry=registry or default_registry(), client=compute, clock=clock)

    handler = logging.FileHandler(service.data_root / "logs" / "backend.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.addFilter(RedactingFilter(service.redact))

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        log.addHandler(handler)
        log.setLevel(logging.INFO)
        service.start()
        log.info("backend started (compute_mode=%s)", compute.mode)
        try:
            yield
        finally:
            service.stop()
            if owns_client:
                compute.close()
            log.removeHandler(handler)
            handler.close()

    app = FastAPI(title="AI Asset Studio", version="1.0", lifespan=lifespan)
    app.state.service = service
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    app.include_router(router)
    return app
