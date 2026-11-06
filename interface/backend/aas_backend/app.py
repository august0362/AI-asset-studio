"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from kaggle_connector.client import ComputeClient, KaggleCliClient, MockKaggleClient
from models.contracts import utc_now
from models.registry import ModelRegistry, registry_for

from .api import router
from .characters.service import CharacterService
from .errors import install_error_handlers
from .orchestrator.service import JobService
from .profiles import environment, load_profiles
from .settings import Settings
from .storage.logs import RedactingFilter

log = logging.getLogger("aas_backend")


def allowed_origins(origin: str) -> list[str]:
    """The configured frontend origin, plus its other loopback spelling (localhost <-> 127.0.0.1, same port).

    Vite runs with ``--host 127.0.0.1`` while browsers and docs often say ``localhost``; both are this machine.
    """
    parts = urlsplit(origin)
    aliases = {"localhost": "127.0.0.1", "127.0.0.1": "localhost"}
    if parts.hostname not in aliases:
        return [origin]
    netloc = aliases[parts.hostname] + (f":{parts.port}" if parts.port else "")
    return [origin, urlunsplit((parts.scheme, netloc, "", "", ""))]


def build_client(settings: Settings, env: Mapping[str, str] | None = None) -> ComputeClient:
    if settings.compute_mode == "kaggle":
        profiles = load_profiles(settings, environment() if env is None else env)
        return KaggleCliClient(
            profiles, executable=settings.kaggle_cli, test_failure=settings.kaggle_test_failure
        )
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
    registry = registry or registry_for(settings.compute_mode)
    service = JobService(settings, registry=registry, client=compute, clock=clock)

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
    app.state.characters = CharacterService(service)
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins(settings.frontend_origin),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )
    app.include_router(router)
    return app
