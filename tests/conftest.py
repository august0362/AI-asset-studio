"""Shared fixtures. Every test runs in mock compute mode in a temporary data directory (no Kaggle, no GPU)."""

from __future__ import annotations

import io
import os
import time
import uuid
import warnings
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

warnings.filterwarnings("ignore", message=".*httpx2.*")

from fastapi.testclient import TestClient  # noqa: E402

from aas_backend.app import create_app  # noqa: E402
from aas_backend.settings import Settings  # noqa: E402
from kaggle_connector.client import MockKaggleClient  # noqa: E402
from models.registry import ModelRegistry, default_registry  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
API = "/api/v1"


def image_bytes(width: int, height: int, fmt: str = "PNG", color=(180, 60, 60), **save) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format=fmt, **save)
    return buffer.getvalue()


def noise_png(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.frombytes("RGB", (width, height), os.urandom(width * height * 3)).save(
        buffer, format="PNG", compress_level=0
    )
    return buffer.getvalue()


def request_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract_version": "1.0",
        "client_request_id": str(uuid.uuid4()),
        "pipeline_type": "text_to_2d",
        "asset_category": "weapon",
        "model_id": "mock-t2d-basic",
        "prompt": "Ornate frost greatsword, crystalline blade, game concept art",
        "inputs": [],
        "options": {"seed": 42, "width": 512, "height": 512},
        "output_format": "png",
        "compute": {"profile_id": "default", "accelerator_id": None},
    }
    body.update(overrides)
    return body


def i3d_body(inputs: list[dict[str, str]], **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "pipeline_type": "image_to_3d",
        "asset_category": "character",
        "model_id": "mock-i3d-multiview",
        "prompt": None,
        "inputs": inputs,
        "options": {},
        "output_format": "glb",
        "compute": {"profile_id": "default", "accelerator_id": "gpu_t4x2"},
    }
    return request_body(**{**values, **overrides})


def codes(items: list[dict[str, Any]]) -> list[str]:
    return [item["code"] for item in items]


@dataclass
class Harness:
    client: TestClient
    compute: MockKaggleClient
    data_dir: Path
    settings: Settings
    closed: bool = False

    def close(self) -> None:
        """Stop the app (lifespan shutdown) without closing the mock compute client."""
        if not self.closed:
            self.client.__exit__(None, None, None)
            self.closed = True

    def upload(self, data: bytes, name: str = "image.png", mime: str = "image/png") -> dict[str, Any]:
        response = self.client.post(f"{API}/uploads", files={"file": (name, data, mime)})
        assert response.status_code == 201, response.text
        return response.json()

    def upload_views(self, roles=("front", "side", "back"), width=1024, height=1536) -> list[dict[str, str]]:
        return [
            {
                "upload_id": self.upload(image_bytes(width, height, color=(40 * i, 90, 160)), f"{r}.png")[
                    "upload_id"
                ],
                "role": r,
            }
            for i, r in enumerate(roles)
        ]

    def wait(
        self, job_id: str, timeout: float = 30.0, until: Callable[[str], bool] | None = None
    ) -> dict[str, Any]:
        done = until or (lambda status: status in ("completed", "failed"))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            status = self.client.get(f"{API}/jobs/{job_id}/status").json()["status"]
            if done(status):
                return self.client.get(f"{API}/jobs/{job_id}").json()
            time.sleep(0.05)
        raise AssertionError(f"job {job_id} did not reach the expected state in {timeout} s")


def make_settings(data_dir: Path, **overrides: Any) -> Settings:
    values = {
        "data_dir": data_dir,
        "mock_queue_seconds": 0.05,
        "mock_run_seconds": 0.0,
        "poll_seconds": 0.05,
        "retry_delays_seconds": (0.0, 0.0, 0.0),
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def harness_factory(tmp_path: Path) -> Iterator[Callable[..., Harness]]:
    opened: list[Harness] = []

    def factory(
        *,
        scenario: str = "fresh",
        failure: str = "none",
        run_seconds: float = 0.0,
        queue_seconds: float = 0.05,
        registry: ModelRegistry | None = None,
        compute: MockKaggleClient | None = None,
        data_dir: Path | None = None,
        **settings: Any,
    ) -> Harness:
        data = data_dir or tmp_path / "data"
        mock = compute or MockKaggleClient(
            scenario=scenario,
            failure=failure,
            queue_seconds=queue_seconds,
            run_seconds=run_seconds,
            remote_root=tmp_path / "remote",
        )
        config = make_settings(data, **settings)
        client = TestClient(create_app(config, client=mock, registry=registry or default_registry()))
        client.__enter__()
        harness = Harness(client=client, compute=mock, data_dir=data, settings=config)
        opened.append(harness)
        return harness

    yield factory
    for harness in reversed(opened):
        harness.close()
    for harness in opened:
        harness.compute.close()


@pytest.fixture
def harness(harness_factory) -> Harness:
    return harness_factory()
