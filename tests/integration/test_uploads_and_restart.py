"""Upload endpoints, startup reconciliation after a restart, and malformed metadata."""

from __future__ import annotations

import json

from kaggle_connector.client import MockKaggleClient
from tests.conftest import API, i3d_body, image_bytes, request_body


def test_upload_roundtrip_and_type_detection(harness):
    png_named_jpg = image_bytes(640, 480)
    record = harness.upload(png_named_jpg, "hero.jpg", "image/jpeg")
    assert record["mime_type"] == "image/png"  # detected from bytes, not name or header
    assert (record["width"], record["height"], record["size_bytes"]) == (640, 480, len(png_named_jpg))
    assert record["filename"] == "hero.jpg" and set(record) == {
        "contract_version",
        "upload_id",
        "filename",
        "mime_type",
        "size_bytes",
        "width",
        "height",
        "sha256",
        "created_at",
        "expires_at",
    }
    assert harness.client.get(f"{API}/uploads/{record['upload_id']}").json() == record
    content = harness.client.get(f"{API}/uploads/{record['upload_id']}/content")
    assert content.content == png_named_jpg and content.headers["content-type"] == "image/png"
    assert harness.client.delete(f"{API}/uploads/{record['upload_id']}").status_code == 204
    assert harness.client.get(f"{API}/uploads/{record['upload_id']}").status_code == 404


def post_file(h, data, name="x.png", mime="image/png"):
    return h.client.post(f"{API}/uploads", files={"file": (name, data, mime)})


def test_upload_rejections(harness):
    assert post_file(harness, b"just text", "a.png").json()["errors"][0]["code"] == "UPLOAD_UNSUPPORTED_TYPE"
    assert post_file(harness, b"just text").status_code == 415
    corrupt = post_file(harness, b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert corrupt.status_code == 422 and corrupt.json()["errors"][0]["code"] == "UPLOAD_CORRUPT"
    too_big = post_file(harness, b"\x89PNG\r\n\x1a\n" + b"\x00" * (52428800 - 7))
    assert too_big.status_code == 413 and too_big.json()["errors"][0]["code"] == "UPLOAD_TOO_LARGE"
    missing = harness.client.post(
        f"{API}/uploads", files={"image": ("x.png", image_bytes(4, 4), "image/png")}
    )
    assert missing.status_code == 400
    two = harness.client.post(
        f"{API}/uploads",
        files=[
            ("file", ("a.png", image_bytes(4, 4), "image/png")),
            ("file", ("b.png", image_bytes(4, 4), "image/png")),
        ],
    )
    assert two.status_code == 400
    assert harness.client.post(f"{API}/uploads", json={"file": "x"}).status_code == 400
    assert list((harness.data_dir / "inputs" / "staging").iterdir()) == []  # nothing half-written


def test_upload_in_use_cannot_be_deleted(harness):
    views = harness.upload_views()
    harness.wait(harness.client.post(f"{API}/jobs", json=i3d_body(views)).json()["job_id"])
    response = harness.client.delete(f"{API}/uploads/{views[0]['upload_id']}")
    assert response.status_code == 409 and response.json()["errors"][0]["code"] == "UPLOAD_IN_USE"


def test_restart_resumes_jobs_with_a_remote_reference(harness_factory, tmp_path):
    compute = MockKaggleClient(queue_seconds=0.05, run_seconds=1.5, remote_root=tmp_path / "remote")
    first = harness_factory(compute=compute)
    job_id = first.client.post(f"{API}/jobs", json=request_body()).json()["job_id"]
    first.wait(job_id, until=lambda status: status == "running")
    first.close()  # backend stops mid-run; the mock remote keeps running
    on_disk = json.loads((first.data_dir / "jobs" / f"{job_id}.json").read_text(encoding="utf-8"))
    assert on_disk["status"] == "running" and on_disk["execution"]["remote_ref"]

    second = harness_factory(compute=compute)
    job = second.wait(job_id)
    assert job["status"] == "completed"
    assert [h["status"] for h in job["status_history"]] == [
        "created",
        "queued",
        "running",
        "downloading",
        "completed",
    ]


def test_restart_fails_jobs_that_cannot_resume(harness_factory, tmp_path):
    first = harness_factory(run_seconds=2)
    job_id = first.client.post(f"{API}/jobs", json=request_body()).json()["job_id"]
    first.wait(job_id, until=lambda status: status in ("queued", "running"))
    done_id = None
    first.close()

    # A job that never got a remote reference fails with BACKEND_RESTARTED (retryable).
    created = json.loads((first.data_dir / "jobs" / f"{job_id}.json").read_text(encoding="utf-8"))
    created.update(status="created", status_history=created["status_history"][:1])
    created["execution"]["remote_ref"] = None
    done_id = job_id.replace(job_id[-6:], "abcdef")
    created["job_id"] = done_id
    created["internal"]["client_request_id"] = "other"
    (first.data_dir / "jobs" / f"{done_id}.json").write_text(json.dumps(created), encoding="utf-8")
    (first.data_dir / "jobs" / "job_20261106T000000Z_000000.json").write_text("{broken", encoding="utf-8")

    # A fresh mock client does not know the old remote reference (the mock remote did not survive).
    second = harness_factory(compute=MockKaggleClient(remote_root=tmp_path / "remote2"))
    never_submitted = second.wait(done_id)
    assert never_submitted["error"]["code"] == "BACKEND_RESTARTED" and never_submitted["error"]["retryable"]
    assert never_submitted["error"]["details"]["failed_in_status"] == "created"
    lost = second.wait(job_id)
    assert lost["error"]["code"] == "BACKEND_RESTARTED"
    ids = [j["job_id"] for j in second.client.get(f"{API}/jobs").json()["jobs"]]
    assert "job_20261106T000000Z_000000" not in ids  # malformed metadata is skipped, not fatal
