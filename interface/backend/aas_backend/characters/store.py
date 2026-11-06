"""Character files under ``data/characters/<character_id>/`` (docs/v2/ARCHITECTURE.md §4).

Every path is built from validated IDs and fixed names (``safe_path``). JSON files are written atomically; revision
files are created exclusively (a second write of the same revision fails); ``history.jsonl`` is append-only and a
torn last line is ignored on read. One lock per character serializes its writes.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import secrets
import tempfile
import threading
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from models.contracts import ContractModel

from ..storage.files import atomic_write_bytes, atomic_write_json, read_json, remove_tree
from ..storage.paths import is_valid_id, safe_path
from .contracts import (
    ArtifactReference,
    Character,
    LastDecision,
    ReferenceAsset,
    StageDraft,
    StageHistory,
    StageRevision,
    StoredManifest,
)

log = logging.getLogger("aas_backend")
M = TypeVar("M", bound=BaseModel)
DELETED_PREFIX = ".deleted-"  # never a valid character_id, so character_ids() skips it


class StageRecord(ContractModel):
    """``stages/<stage_id>/state.json``: the stored part of StageState (everything else is derived on read)."""

    latest_revision: int | None = None
    pending_revision: int | None = None
    approved_revision: int | None = None
    last_decision: LastDecision | None = None
    submitted_draft_version: int | None = None  # the draft version the latest submit froze


class RevisionExists(Exception):
    pass


class CharacterStore:
    def __init__(self, data_root: Path) -> None:
        self.root = data_root
        self.base = data_root / "characters"
        self.base.mkdir(parents=True, exist_ok=True)
        self._guard = threading.Lock()
        self._locks: dict[str, threading.RLock] = {}

    # --- locking and paths --------------------------------------------------------------------------------------

    def lock(self, character_id: str) -> threading.RLock:
        with self._guard:
            return self._locks.setdefault(character_id, threading.RLock())

    def path(self, character_id: str, *parts: str) -> Path:
        return safe_path(self.root, "/".join(("characters", character_id, *parts)))

    def relative(self, character_id: str, *parts: str) -> str:
        return "/".join(("characters", character_id, *parts))

    def character_ids(self) -> list[str]:
        ids = []
        for entry in self.base.iterdir():
            if entry.is_dir() and not entry.is_symlink() and is_valid_id("character_id", entry.name):
                ids.append(entry.name)
        return sorted(ids)

    def delete_character(self, character_id: str) -> None:
        """Rename the folder out of the way first (one atomic step), then remove it (route 19, D-038)."""
        folder = self.path(character_id)
        trash = self.base / f"{DELETED_PREFIX}{character_id}-{secrets.token_hex(4)}"
        for attempt in range(5):
            try:
                folder.rename(trash)
                break
            except PermissionError:  # Windows: a reader still holds a file open
                if attempt == 4:
                    raise
                time.sleep(0.1)
        remove_tree(trash)

    def sweep_deleted(self) -> int:
        """Remove folders a crash left behind between the rename and the removal of a delete."""
        removed = 0
        for entry in self.base.glob(f"{DELETED_PREFIX}*"):
            if entry.is_dir() and not entry.is_symlink():
                with contextlib.suppress(OSError):
                    remove_tree(entry)
                    removed += 1
        return removed

    def sweep_temp(self) -> int:
        """Interrupted atomic writes leave ``.<name>.*.tmp`` files; nothing else is ever partial."""
        removed = 0
        for temp in self.base.rglob(".*.tmp"):
            if temp.is_file() and not temp.is_symlink():
                with contextlib.suppress(OSError):
                    temp.unlink()
                    removed += 1
        return removed

    # --- generic JSON -------------------------------------------------------------------------------------------

    def _read(self, path: Path, model: type[M]) -> M | None:
        if not path.is_file() or path.is_symlink():
            return None
        try:
            return model.model_validate(read_json(path))
        except (ValueError, ValidationError):
            log.error("ignoring malformed character file %s", path.name)
            return None

    def _write(self, path: Path, value: BaseModel) -> None:
        atomic_write_json(path, value.model_dump(mode="json"))

    # --- character ----------------------------------------------------------------------------------------------

    def read_character(self, character_id: str) -> Character | None:
        return self._read(self.path(character_id, "character.json"), Character)

    def write_character(self, character: Character) -> None:
        self._write(self.path(character.character_id, "character.json"), character)

    def read_requests(self, character_id: str) -> dict[str, dict[str, str]]:
        path = self.path(character_id, "requests.json")
        try:
            data = read_json(path) if path.is_file() else {}
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def write_requests(self, character_id: str, data: dict[str, dict[str, str]]) -> None:
        atomic_write_json(self.path(character_id, "requests.json"), data)

    # --- stages -------------------------------------------------------------------------------------------------

    def read_draft(self, character_id: str, stage_id: str) -> StageDraft | None:
        return self._read(self.path(character_id, "stages", stage_id, "draft.json"), StageDraft)

    def write_draft(self, draft: StageDraft) -> None:
        self._write(self.path(draft.character_id, "stages", draft.stage_id, "draft.json"), draft)

    def read_stage(self, character_id: str, stage_id: str) -> StageRecord:
        return (
            self._read(self.path(character_id, "stages", stage_id, "state.json"), StageRecord)
            or StageRecord()
        )

    def write_stage(self, character_id: str, stage_id: str, record: StageRecord) -> None:
        self._write(self.path(character_id, "stages", stage_id, "state.json"), record)

    def _revision_path(self, character_id: str, stage_id: str, revision: int) -> Path:
        return self.path(character_id, "stages", stage_id, "revisions", f"{revision:04d}.json")

    def read_revision(self, character_id: str, stage_id: str, revision: int) -> StageRevision | None:
        return self._read(self._revision_path(character_id, stage_id, revision), StageRevision)

    def create_revision(self, revision: StageRevision) -> None:
        """Exclusive create: write a temp file, then hard-link it to the final name (fails if it exists)."""
        path = self._revision_path(revision.character_id, revision.stage_id, revision.revision)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(revision.model_dump(mode="json"), indent=2, ensure_ascii=False).encode("utf-8")
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temp = Path(temp_name)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp, path)
            except FileExistsError as exc:
                raise RevisionExists(path.name) from exc
        finally:
            with contextlib.suppress(FileNotFoundError):
                temp.unlink()

    def update_revision(self, revision: StageRevision) -> None:
        """Decision fields only, while the revision is pending (the service enforces that)."""
        self._write(
            self._revision_path(revision.character_id, revision.stage_id, revision.revision), revision
        )

    # --- references, assets, batches ----------------------------------------------------------------------------

    def read_reference(self, character_id: str, reference_id: str) -> ReferenceAsset | None:
        return self._read(self.path(character_id, "references", f"{reference_id}.json"), ReferenceAsset)

    def write_reference(self, reference: ReferenceAsset) -> None:
        self._write(
            self.path(reference.character_id, "references", f"{reference.reference_id}.json"), reference
        )

    def list_references(self, character_id: str) -> list[ReferenceAsset]:
        return self._list(character_id, "references", "ref_", ReferenceAsset)

    def delete_reference(self, character_id: str, reference: ReferenceAsset, extension: str | None) -> None:
        if extension:
            remove_tree(self.path(character_id, "references", f"{reference.reference_id}.{extension}"))
        remove_tree(self.path(character_id, "references", f"{reference.reference_id}.json"))

    def read_asset(self, character_id: str, asset_id: str) -> ArtifactReference | None:
        return self._read(self.path(character_id, "assets", f"{asset_id}.json"), ArtifactReference)

    def write_asset(self, character_id: str, asset: ArtifactReference, data: bytes) -> None:
        atomic_write_bytes(self.path(character_id, "assets", f"{asset.asset_id}.png"), data)
        self._write(self.path(character_id, "assets", f"{asset.asset_id}.json"), asset)

    def remove_asset(self, character_id: str, asset_id: str) -> None:
        """Only used to undo a freeze that failed before its approval was written."""
        remove_tree(self.path(character_id, "assets", f"{asset_id}.png"))
        remove_tree(self.path(character_id, "assets", f"{asset_id}.json"))

    def read_manifest(self, character_id: str, manifest_id: str) -> StoredManifest | None:
        return self._read(self.path(character_id, "batches", f"{manifest_id}.json"), StoredManifest)

    def write_manifest(self, manifest: StoredManifest) -> None:
        self._write(self.path(manifest.character_id, "batches", f"{manifest.manifest_id}.json"), manifest)

    def list_manifests(self, character_id: str) -> list[StoredManifest]:
        return self._list(character_id, "batches", "bat_", StoredManifest)

    def _list(self, character_id: str, folder: str, prefix: str, model: type[M]) -> list[M]:
        directory = self.path(character_id, folder)
        if not directory.is_dir():
            return []
        items = []
        for path in sorted(directory.glob(f"{prefix}*.json")):
            item = self._read(path, model)
            if item is not None:
                items.append(item)
        return items

    # --- history ------------------------------------------------------------------------------------------------

    def read_history(self, character_id: str) -> list[StageHistory]:
        path = self.path(character_id, "history.jsonl")
        if not path.is_file():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                events.append(StageHistory.model_validate(json.loads(line)))
            except (ValueError, ValidationError):
                log.warning("ignoring a torn or malformed history line of %s", character_id)
        return events

    def append_history(self, character_id: str, event: StageHistory) -> None:
        path = self.path(character_id, "history.jsonl")
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False) + "\n"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
