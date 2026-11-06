"""Storage: path safety, symlinks, atomic writes, upload validation and expiry, redaction."""

from __future__ import annotations

import io
import json
import os
from datetime import timedelta
from pathlib import Path

import pytest

from aas_backend.errors import ApiError
from aas_backend.storage import files
from aas_backend.storage.files import atomic_write_json, read_json
from aas_backend.storage.logs import JobLogs, Redactor
from aas_backend.storage.paths import PathInvalid, check_id, safe_path
from aas_backend.storage.uploads import UploadStore, sniff_mime
from models.contracts import utc_now
from tests.conftest import image_bytes


@pytest.mark.parametrize(
    "relative",
    [
        "../secret.txt",
        "jobs/../../x",
        "/etc/passwd",
        "C:/Windows/win.ini",
        "jobs\\..\\x",
        "",
        "jobs//x",
        "./jobs",
        "jobs/x\x00.json",
    ],
)
def test_safe_path_rejects_traversal_and_absolute_paths(tmp_path, relative):
    with pytest.raises(PathInvalid):
        safe_path(tmp_path, relative)


def test_safe_path_accepts_normal_relative_paths(tmp_path):
    assert safe_path(tmp_path, "jobs/job_x.json") == tmp_path / "jobs" / "job_x.json"


def test_safe_path_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "data"
    root.mkdir()
    try:
        os.symlink(outside, root / "outputs", target_is_directory=True)
    except (OSError, NotImplementedError):
        try:  # Windows without symlink privilege: an NTFS junction is the same escape vector
            import _winapi

            _winapi.CreateJunction(str(outside), str(root / "outputs"))
        except (ImportError, OSError):
            pytest.skip("cannot create a symlink or junction on this machine")
    with pytest.raises(PathInvalid):
        safe_path(root, "outputs/job_x/art_01.png")


@pytest.mark.parametrize(
    "kind,value",
    [
        ("job_id", "job_20261106T101500Z_a1b2c"),
        ("job_id", "../job"),
        ("upload_id", "upl_XYZ"),
        ("artifact_id", "art_1"),
        ("input_id", "in_001"),
    ],
)
def test_identifiers_are_checked_before_any_path_use(kind, value):
    with pytest.raises(PathInvalid):
        check_id(kind, value)


def test_atomic_write_replaces_and_leaves_no_temp_files(tmp_path):
    target = tmp_path / "jobs" / "job.json"
    atomic_write_json(target, {"v": 1})
    atomic_write_json(target, {"v": 2})
    assert read_json(target) == {"v": 2}
    assert [p.name for p in target.parent.iterdir()] == ["job.json"]


def test_failed_atomic_write_keeps_the_previous_file(tmp_path, monkeypatch):
    target = tmp_path / "job.json"
    atomic_write_json(target, {"v": 1})

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(files.os, "replace", broken_replace)
    with pytest.raises(OSError):
        atomic_write_json(target, {"v": 2})
    assert json.loads(target.read_text()) == {"v": 1}
    assert [p.name for p in tmp_path.iterdir()] == ["job.json"]


@pytest.mark.parametrize(
    "data,mime",
    [
        (image_bytes(4, 4, "PNG"), "image/png"),
        (image_bytes(4, 4, "JPEG"), "image/jpeg"),
        (image_bytes(4, 4, "WEBP"), "image/webp"),
        (b"GIF89a....", None),
        (b"", None),
        (b"hello", None),
    ],
)
def test_mime_is_detected_from_bytes(data, mime):
    assert sniff_mime(data[:16]) == mime


class Clock:
    def __init__(self):
        self.now = utc_now()

    def __call__(self):
        return self.now


def test_upload_validation_and_expiry_sweep(tmp_path):
    clock = Clock()
    store = UploadStore(tmp_path, timedelta(hours=24), clock)
    kept = store.save(io.BytesIO(image_bytes(64, 32)), "C:\\fakepath\\../hero front.png")
    referenced = store.save(io.BytesIO(image_bytes(64, 32)), "b.png")
    assert kept.filename == "hero front.png" and (kept.width, kept.height) == (64, 32)
    assert store.get(kept.upload_id).path.name == "file.png"

    clock.now += timedelta(hours=24, seconds=1)
    assert store.get(kept.upload_id) is None  # expired uploads are no longer usable
    assert store.sweep({referenced.upload_id}) == 1
    assert not (tmp_path / "inputs" / "staging" / kept.upload_id).exists()
    assert (tmp_path / "inputs" / "staging" / referenced.upload_id).exists()


@pytest.mark.parametrize(
    "data,status,code",
    [
        (b"plain text", 415, "UPLOAD_UNSUPPORTED_TYPE"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 64, 422, "UPLOAD_CORRUPT"),
    ],
)
def test_bad_uploads_are_rejected_and_cleaned_up(tmp_path, data, status, code):
    store = UploadStore(tmp_path, timedelta(hours=24), Clock())
    with pytest.raises(ApiError) as caught:
        store.save(io.BytesIO(data), "x.png")
    assert caught.value.status == status and caught.value.errors[0].code == code
    assert list((tmp_path / "inputs" / "staging").iterdir()) == []


def test_malformed_upload_metadata_is_ignored(tmp_path):
    store = UploadStore(tmp_path, timedelta(hours=24), Clock())
    record = store.save(io.BytesIO(image_bytes(8, 8)), "a.png")
    (tmp_path / "inputs" / "staging" / record.upload_id / "upload.json").write_text("{not json")
    assert store.get(record.upload_id) is None


def test_redaction_of_tokens_and_local_paths(tmp_path):
    redact = Redactor(secrets=["s3cret-value"], paths=[tmp_path])
    text = (
        f"KAGGLE_API_TOKEN=KGAT_abc123 KAGGLE_KEY: xyz token KGAT_deadbeef s3cret-value "
        f"file {tmp_path / 'inputs' / 'a.png'}"
    )
    cleaned = redact(text)
    for leaked in ("KGAT_abc123", "xyz", "KGAT_deadbeef", "s3cret-value", str(tmp_path)):
        assert leaked not in cleaned
    assert "<data>" in cleaned


def test_job_logs_paginate_and_redact(tmp_path):
    logs = JobLogs(tmp_path, Redactor(), utc_now)
    logs.append("job_a", "remote", [f"line {i}" for i in range(5)] + ["KAGGLE_KEY=abcd"])
    lines, next_offset, total = logs.read("job_a", 2, 3)
    assert [line["n"] for line in lines] == [2, 3, 4] and next_offset == 5 and total == 6
    assert logs.read("job_a", 5, 10)[0][0]["text"] == "KAGGLE_KEY=[REDACTED]"
    assert logs.read("job_a", 50, 10)[1] == 6
    assert logs.read("missing", 0, 10) == ([], 0, 0)


def test_paths_are_stored_as_posix(tmp_path: Path):
    from aas_backend.storage.paths import to_relative

    assert to_relative(tmp_path, tmp_path / "outputs" / "job" / "art_01.png") == "outputs/job/art_01.png"
