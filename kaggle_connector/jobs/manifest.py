"""Output manifest checks (docs/CONTRACTS.md §6.4)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from ..resources.contracts import OutputManifest


class ManifestInvalid(Exception):
    code = "ARTIFACT_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def read_manifest(output_dir: Path) -> OutputManifest:
    path = output_dir / "manifest.json"
    if not path.is_file():
        raise ManifestInvalid("The run produced no output manifest.")
    try:
        return OutputManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ManifestInvalid("The output manifest is malformed.") from exc


def verify_outputs(manifest: OutputManifest, output_dir: Path, job_id: str) -> None:
    """Every listed output exists with the declared size and hash."""
    if manifest.job_id != job_id:
        raise ManifestInvalid("The output manifest belongs to a different job.")
    for entry in manifest.outputs:
        if "/" in entry.name or "\\" in entry.name or entry.name in ("", ".", ".."):
            raise ManifestInvalid("The output manifest lists an invalid file name.")
        path = output_dir / entry.name
        if not path.is_file() or path.is_symlink():
            raise ManifestInvalid(f"The output '{entry.name}' listed in the manifest is missing.")
        data = path.read_bytes()
        if len(data) != entry.size_bytes or hashlib.sha256(data).hexdigest() != entry.sha256:
            raise ManifestInvalid(f"The output '{entry.name}' does not match its manifest entry.")
