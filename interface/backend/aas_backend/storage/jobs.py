"""Job metadata files ``jobs/<job_id>.json`` (atomic) and per-job directories."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import ValidationError

from ..orchestrator.records import JobRecord
from .files import atomic_write_json, read_json, remove_tree
from .paths import is_valid_id, safe_path

log = logging.getLogger("aas_backend")


class JobStore:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root
        for sub in ("jobs", "inputs", "outputs", "logs"):
            (data_root / sub).mkdir(parents=True, exist_ok=True)

    def job_file(self, job_id: str) -> Path:
        return safe_path(self.root, f"jobs/{job_id}.json")

    def inputs_dir(self, job_id: str) -> Path:
        return safe_path(self.root, f"inputs/{job_id}")

    def outputs_dir(self, job_id: str) -> Path:
        return safe_path(self.root, f"outputs/{job_id}")

    def save(self, record: JobRecord) -> None:
        atomic_write_json(self.job_file(record.job_id), record.model_dump(mode="json"))

    def load_all(self) -> list[JobRecord]:
        records = []
        for path in sorted((self.root / "jobs").glob("job_*.json")):
            job_id = path.stem
            if not is_valid_id("job_id", job_id) or path.is_symlink():
                log.warning("security: skipping unexpected job file %s", path.name)
                continue
            try:
                record = JobRecord.model_validate(read_json(path))
            except (ValueError, ValidationError):
                log.error("skipping malformed job file %s", path.name)
                continue
            if record.job_id != job_id:
                log.error("skipping job file %s: job_id mismatch", path.name)
                continue
            records.append(record)
        return records

    def delete(self, job_id: str, log_files: list[Path]) -> None:
        remove_tree(self.inputs_dir(job_id))
        remove_tree(self.outputs_dir(job_id))
        for path in log_files:
            remove_tree(path)
        remove_tree(self.job_file(job_id))
