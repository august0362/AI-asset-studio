"""Backend configuration from the environment and ``.env`` (pydantic-settings).

Kaggle profile credentials (``AAS_PROFILE_*``) are **not** read in mock mode; in kaggle mode only the active
profile's credentials are read (:mod:`aas_backend.profiles`). Unknown ``AAS_*`` keys are ignored.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AAS_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    data_dir: Path = Path("./data")
    compute_mode: Literal["mock", "kaggle"] = "mock"
    backend_host: str = "127.0.0.1"
    backend_port: int = Field(default=8000, ge=1, le=65535)
    frontend_origin: str = "http://localhost:5173"

    # Kaggle compute (AAS_COMPUTE_MODE=kaggle). Exactly one profile is active (D-008, D-025).
    compute_profiles: str = "default"
    active_profile: str | None = None
    kaggle_cli: str | None = None  # path to the kaggle executable; default: found on PATH
    # Test switch (D-031): "kernel_error" makes every Kaggle run fail on purpose inside the real notebook.
    kaggle_test_failure: Literal["kernel_error"] | None = None

    # Mock compute (AAS_COMPUTE_MODE=mock)
    mock_scenario: str = "fresh"
    mock_failure: str = "none"
    mock_queue_seconds: float = Field(default=1.0, ge=0)
    mock_run_seconds: float = Field(default=4.0, ge=0)

    # Orchestration (contract constants; overridable for tests)
    poll_seconds: float | None = Field(default=None, gt=0)  # default: 0.5 s mock, 30 s kaggle
    retry_delays_seconds: tuple[float, float, float] = (5.0, 15.0, 45.0)
    upload_ttl_hours: float = Field(default=24.0, gt=0)
    sweep_interval_seconds: float = Field(default=3600.0, gt=0)
    job_deadline_factor: float = Field(default=1.25, gt=0)

    @field_validator("kaggle_test_failure", mode="before")
    @classmethod
    def _empty_is_off(cls, value: object) -> object:
        return None if value in ("", "none", "off") else value

    @field_validator("backend_host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        if value not in LOOPBACK_HOSTS:
            raise ValueError("the backend binds to loopback only (NFR-1): use 127.0.0.1")
        return value

    @property
    def effective_poll_seconds(self) -> float:
        if self.poll_seconds is not None:
            return self.poll_seconds
        return 0.5 if self.compute_mode == "mock" else 30.0
