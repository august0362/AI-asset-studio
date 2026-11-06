"""ComputeClient protocol shared by MockKaggleClient (M2) and KaggleCliClient (M3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from ..resources.contracts import ComputeProfile, KaggleResourceSnapshot

RemoteStatus = Literal["queued", "running", "complete", "error"]


@dataclass(frozen=True)
class OutputSpec:
    name: str
    kind: str
    format: str
    required: bool


@dataclass(frozen=True)
class KaggleJobSpec:
    """Model-agnostic run description built by the backend. In memory only; holds no secrets."""

    job_id: str
    profile_id: str
    accelerator_id: str
    timeout_seconds: int
    entrypoint_file: Path
    arguments: dict[str, Any]
    input_files: list[Path] = field(default_factory=list)
    expected_outputs: list[OutputSpec] = field(default_factory=list)

    @property
    def requires_input_upload(self) -> bool:
        return bool(self.input_files)


class ComputeError(Exception):
    """A remote operation failed. ``code`` is a CONTRACTS §8.2 job-time code."""

    def __init__(self, code: str, message: str, *, transient: bool = False, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.transient = transient
        self.retryable = retryable


class RemoteRefNotFound(ComputeError):
    """The remote reference is unknown to this client (e.g. a mock run lost across a backend restart)."""

    def __init__(self, remote_ref: str) -> None:
        super().__init__("REMOTE_REF_UNKNOWN", f"Unknown remote reference {remote_ref}")


class ComputeClient(Protocol):
    mode: Literal["mock", "kaggle"]

    def profiles(self) -> list[ComputeProfile]: ...

    def snapshot(self, profile_id: str, *, refresh: bool = False) -> KaggleResourceSnapshot: ...

    def upload_inputs(self, spec: KaggleJobSpec) -> None: ...

    def submit(self, spec: KaggleJobSpec) -> str: ...

    def status(self, remote_ref: str) -> RemoteStatus: ...

    def logs(self, remote_ref: str, offset: int) -> tuple[list[str], int]: ...

    def download(self, remote_ref: str, dest_dir: Path) -> None: ...

    def close(self) -> None: ...
