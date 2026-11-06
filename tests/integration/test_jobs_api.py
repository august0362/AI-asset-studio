"""Full mock jobs through the REST API: lifecycle, artifacts, logs, idempotency, retry, failures, deletion."""

from __future__ import annotations

import json
import re
import uuid

import pytest

from models.adapters.validation import validate_glb_bytes
from tests.conftest import API, i3d_body, request_body

FULL_2D = ["created", "queued", "running", "downloading", "completed"]
FULL_3D = ["created", "uploading", "queued", "running", "downloading", "completed"]


def create(h, body):
    response = h.client.post(f"{API}/jobs", json=body)
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "created"
    return response.json()


def history(job):
    return [entry["status"] for entry in job["status_history"]]


def test_full_text_to_2d_job(harness):
    job = harness.wait(create(harness, request_body())["job_id"])
    assert job["status"] == "completed" and history(job) == FULL_2D and job["error"] is None
    compute = job["compute"]
    assert (compute["profile_id"], compute["accelerator_id"]) == ("default", "cpu")
    plan = compute["resource_plan"]  # the full §7.3 plan, as shown by the frontend's job detail
    assert (plan["fit"], plan["selection"], plan["required_seconds"]) == ("ok", "recommended", 645)
    assert plan["estimate_basis"] == {
        "estimated_runtime_seconds": 30,
        "safety_factor": 1.5,
        "overhead_seconds": 600,
    }
    assert plan["accelerator_id"] == "cpu" and plan["session_limit_seconds"] == 43200
    assert job["request"]["options"] == {"seed": 42, "width": 512, "height": 512, "negative_prompt": None}
    (artifact,) = job["artifacts"]
    assert (artifact["kind"], artifact["format"], artifact["is_primary"]) == ("image", "png", True)
    assert (artifact["width"], artifact["height"]) == (512, 512)
    assert job["preview"] == {"artifact_id": "art_01"}
    assert job["execution"]["backend"] == "mock" and job["execution"]["retry_of"] is None
    content = harness.client.get(artifact["content_url"])
    assert content.status_code == 200 and content.headers["content-type"] == "image/png"
    assert content.content.startswith(b"\x89PNG") and len(content.content) == artifact["size_bytes"]
    status = harness.client.get(f"{API}/jobs/{job['job_id']}/status").json()
    assert status["progress"] == {"stage": "finished", "percent": 100.0, "message": "Outputs written"}


def test_full_image_to_3d_job_with_front_side_back(harness):
    job = harness.wait(create(harness, i3d_body(harness.upload_views()))["job_id"])
    assert job["status"] == "completed" and history(job) == FULL_3D
    assert [(a["artifact_id"], a["kind"], a["is_primary"]) for a in job["artifacts"]] == [
        ("art_01", "model_3d", True),
        ("art_02", "preview", False),
    ]
    assert job["preview"] == {"artifact_id": "art_02"}
    assert [i["role"] for i in job["request"]["inputs"]] == ["front", "side", "back"]
    glb = harness.client.get(f"{job['artifacts'][0]['content_url']}?download=1")
    assert glb.headers["content-type"] == "model/gltf-binary"
    assert glb.headers["content-disposition"] == f'attachment; filename="{job["job_id"]}_art_01.glb"'
    assert validate_glb_bytes(glb.content)["asset"]["version"] == "2.0"
    listed = harness.client.get(f"{API}/jobs/{job['job_id']}/artifacts").json()["artifacts"]
    assert listed == job["artifacts"]
    image = harness.client.get(job["request"]["inputs"][0]["content_url"])
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    # remote_raw/ is removed after collect_outputs succeeds
    assert sorted(p.name for p in (harness.data_dir / "outputs" / job["job_id"]).iterdir()) == [
        "art_01.glb",
        "art_02.png",
    ]


def test_logs_endpoint_hides_telemetry_and_paginates(harness):
    job_id = harness.wait(create(harness, i3d_body(harness.upload_views()))["job_id"])["job_id"]
    page = harness.client.get(f"{API}/jobs/{job_id}/logs?limit=1000").json()
    texts = [line["text"] for line in page["lines"]]
    assert page["complete"] and not any(t.startswith("AAS_TELEMETRY") for t in texts)
    assert {line["source"] for line in page["lines"]} == {"backend", "remote"}
    assert [line["n"] for line in page["lines"]] == list(range(len(texts)))
    telemetry = (harness.data_dir / "logs" / f"{job_id}.telemetry.jsonl").read_text().splitlines()
    sample = json.loads(telemetry[0])
    assert [g["index"] for g in sample["gpus"]] == [0, 1]  # T4×2: two independent devices
    first = harness.client.get(f"{API}/jobs/{job_id}/logs?offset=0&limit=2").json()
    assert len(first["lines"]) == 2 and first["next_offset"] == 2 and not first["complete"]
    assert harness.client.get(f"{API}/jobs/{job_id}/logs?limit=0").status_code == 422


def test_idempotent_creation(harness):
    body = request_body()
    first, second = create(harness, body), create(harness, body)
    assert first["job_id"] == second["job_id"]
    assert len(harness.client.get(f"{API}/jobs").json()["jobs"]) == 1
    harness.wait(first["job_id"])


def test_list_filters_and_cursor(harness):
    ids = [harness.wait(create(harness, request_body())["job_id"])["job_id"] for _ in range(3)]
    page = harness.client.get(f"{API}/jobs?limit=2").json()
    assert [j["job_id"] for j in page["jobs"]] == ids[::-1][:2] and page["next_cursor"] == ids[1]
    rest = harness.client.get(f"{API}/jobs?limit=2&cursor={page['next_cursor']}").json()
    assert [j["job_id"] for j in rest["jobs"]] == [ids[0]] and rest["next_cursor"] is None
    summary = page["jobs"][0]
    assert summary["primary_artifact"]["format"] == "png" and summary["error_code"] is None
    assert harness.client.get(f"{API}/jobs?status=failed").json()["jobs"] == []
    assert harness.client.get(f"{API}/jobs?pipeline_type=image_to_3d").json()["jobs"] == []
    assert harness.client.get(f"{API}/jobs?status=done").status_code == 422
    assert harness.client.get(f"{API}/jobs?cursor=job_bad").status_code == 422


@pytest.mark.parametrize(
    "failure,code,failed_in,retryable",
    [
        ("kernel_error", "KAGGLE_KERNEL_ERROR", "running", False),
        ("invalid_artifact", "ARTIFACT_INVALID", "downloading", False),
        ("missing_manifest", "ARTIFACT_INVALID", "downloading", False),
        ("download", "ARTIFACT_DOWNLOAD_FAILED", "downloading", True),
        ("submit", "KAGGLE_SUBMIT_FAILED", "uploading", True),  # image jobs upload before submitting
        ("upload", "KAGGLE_UPLOAD_FAILED", "uploading", True),
    ],
)
def test_controlled_failures(harness_factory, failure, code, failed_in, retryable):
    h = harness_factory(failure=failure)
    job = h.wait(create(h, i3d_body(h.upload_views()))["job_id"])
    assert job["status"] == "failed" and job["artifacts"] == [] and job["preview"] is None
    assert (job["error"]["code"], job["error"]["details"]["failed_in_status"], job["error"]["retryable"]) == (
        code,
        failed_in,
        retryable,
    )
    assert job["execution"]["finished_at"] is not None
    logs = [
        line["text"] for line in h.client.get(f"{API}/jobs/{job['job_id']}/logs?limit=1000").json()["lines"]
    ]
    assert any(code in text for text in logs)
    if failure == "kernel_error":
        assert any("Simulated kernel failure" in text for text in logs)  # readable remote logs
    if failure == "download":
        assert job["execution"]["transient_retries"] == 3  # bounded: at most 3 in-job retries
    if failed_in == "downloading" and failure != "download":
        assert (h.data_dir / "outputs" / job["job_id"] / "remote_raw").is_dir()  # kept on failure
    assert (h.data_dir / "inputs" / job["job_id"]).is_dir()  # inputs kept on failure


@pytest.mark.parametrize("failure", ["status_transient", "download_transient"])
def test_transient_errors_are_retried_without_resubmitting(harness_factory, failure):
    h = harness_factory(failure=failure)
    job = h.wait(create(h, request_body())["job_id"])
    assert job["status"] == "completed" and job["execution"]["transient_retries"] == 2
    assert len(h.compute._runs) == 1  # never resubmitted


def test_timeout_rule(harness_factory):
    h = harness_factory(run_seconds=5, job_deadline_factor=0.0005)  # deadline ≈ 0.3 s
    job = h.wait(create(h, request_body())["job_id"])
    assert job["error"]["code"] == "KAGGLE_TIMEOUT" and job["error"]["retryable"]


def test_retry_creates_a_new_revalidated_job(harness_factory):
    h = harness_factory(failure="submit")
    failed = h.wait(create(h, i3d_body(h.upload_views()))["job_id"])
    assert failed["error"]["code"] == "KAGGLE_SUBMIT_FAILED"
    h.compute.failure = "none"
    # The staged uploads may expire; the retry falls back to the failed job's own copied inputs.
    for staged in (h.data_dir / "inputs" / "staging").iterdir():
        for f in staged.iterdir():
            f.unlink()
        staged.rmdir()
    body = {"client_request_id": str(uuid.uuid4())}
    response = h.client.post(f"{API}/jobs/{failed['job_id']}/retry", json=body)
    assert response.status_code == 201, response.text
    retried = h.wait(response.json()["job_id"])
    assert retried["status"] == "completed" and retried["execution"]["retry_of"] == failed["job_id"]
    assert (
        h.client.post(f"{API}/jobs/{failed['job_id']}/retry", json=body).json()["job_id"] == retried["job_id"]
    )
    original = h.client.get(f"{API}/jobs/{failed['job_id']}").json()
    assert original["status"] == "failed"  # the failed job stays auditable


def test_retry_is_refused_for_non_retryable_or_completed_jobs(harness_factory):
    h = harness_factory(failure="kernel_error")
    failed = h.wait(create(h, request_body())["job_id"])
    body = {"client_request_id": str(uuid.uuid4())}
    response = h.client.post(f"{API}/jobs/{failed['job_id']}/retry", json=body)
    assert response.status_code == 409 and response.json()["errors"][0]["code"] == "JOB_NOT_RETRYABLE"
    h.compute.failure = "none"
    done = h.wait(create(h, request_body())["job_id"])
    assert h.client.post(f"{API}/jobs/{done['job_id']}/retry", json=body).status_code == 409
    assert h.client.post(f"{API}/jobs/{done['job_id']}/retry", json={}).status_code == 422


def test_delete_terminal_job_removes_everything(harness):
    job = harness.wait(create(harness, i3d_body(harness.upload_views()))["job_id"])
    job_id = job["job_id"]
    assert harness.client.delete(f"{API}/jobs/{job_id}").status_code == 204
    assert harness.client.get(f"{API}/jobs/{job_id}").status_code == 404
    for path in (
        f"jobs/{job_id}.json",
        f"inputs/{job_id}",
        f"outputs/{job_id}",
        f"logs/{job_id}.log",
        f"logs/{job_id}.telemetry.jsonl",
    ):
        assert not (harness.data_dir / path).exists(), path


def test_delete_non_terminal_job_is_refused(harness_factory):
    h = harness_factory(run_seconds=3)
    job_id = create(h, request_body())["job_id"]
    response = h.client.delete(f"{API}/jobs/{job_id}")
    assert response.status_code == 409 and response.json()["errors"][0]["code"] == "JOB_NOT_TERMINAL"
    h.wait(job_id)


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/jobs/..%5C..%5Cwindows", 400, "PATH_INVALID"),
        ("/jobs/job_bad", 400, "PATH_INVALID"),
        ("/jobs/job_20261106T101500Z_a1b2c3", 404, "JOB_NOT_FOUND"),
        ("/jobs/job_20261106T101500Z_a1b2c3/artifacts/art_1/content", 400, "PATH_INVALID"),
        ("/uploads/upl_..%2F..%2Fx", 404, "PATH_INVALID"),  # decoded "/" matches no route
        ("/uploads/" + "upl_" + "0" * 32, 404, "UPLOAD_NOT_FOUND"),
        ("/models/nope", 404, "MODEL_NOT_FOUND"),
        ("/compute/profiles/alice/snapshot", 404, "COMPUTE_PROFILE_NOT_FOUND"),
        ("/no/such/route", 404, "PATH_INVALID"),
    ],
)
def test_invalid_ids_and_paths(harness, path, status, code):
    response = harness.client.get(API + path)
    assert response.status_code == status
    body = response.json()
    assert body["contract_version"] == "1.0" and body["errors"][0]["code"] == code


def test_artifact_and_input_ids_must_exist(harness):
    job_id = harness.wait(create(harness, request_body())["job_id"])["job_id"]
    assert harness.client.get(f"{API}/jobs/{job_id}/artifacts/art_09/content").status_code == 404
    assert harness.client.get(f"{API}/jobs/{job_id}/inputs/in_01/content").status_code == 404
    assert harness.client.get(f"{API}/jobs/{job_id}/artifacts/art_01/content?download=2").status_code == 422


DRIVE_PATH = re.compile(r"[A-Za-z]:[\\/]")


def test_api_payloads_never_contain_paths_or_secrets(harness_factory, monkeypatch):
    monkeypatch.setenv("AAS_PROFILE_DEFAULT_KAGGLE_API_TOKEN", "KGAT_fake0123456789")
    h = harness_factory()
    job_id = h.wait(create(h, i3d_body(h.upload_views()))["job_id"])["job_id"]
    payloads = [
        h.client.get(API + path).text
        for path in (
            "/health",
            "/catalog",
            "/models",
            "/compute/profiles",
            "/compute/profiles/default/snapshot",
            "/jobs",
            f"/jobs/{job_id}",
            f"/jobs/{job_id}/status",
            f"/jobs/{job_id}/logs?limit=1000",
            f"/jobs/{job_id}/artifacts",
        )
    ]
    data_root = str(h.data_dir.resolve())
    for text in payloads:
        assert data_root not in text and data_root.replace("\\", "\\\\") not in text
        assert not DRIVE_PATH.search(text), text[:300]
        assert '"path"' not in text and "KGAT_" not in text
    for file in h.data_dir.rglob("*"):
        if file.is_file() and file.suffix in (".json", ".log", ".jsonl"):
            assert "KGAT_fake0123456789" not in file.read_text(encoding="utf-8", errors="ignore")


def test_cors_allows_only_the_configured_origin(harness):
    allowed = harness.client.options(
        f"{API}/jobs", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    denied = harness.client.get(f"{API}/health", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_health_catalog_models_profiles(harness):
    assert harness.client.get(f"{API}/health").json() == {
        "status": "ok",
        "contract_version": "1.0",
        "compute_mode": "mock",
    }
    models = harness.client.get(f"{API}/models?pipeline_type=image_to_3d&asset_category=character").json()
    assert [m["model_id"] for m in models["models"]] == ["mock-i3d-single", "mock-i3d-multiview"]
    assert (
        harness.client.get(f"{API}/models?pipeline_type=x").json()["errors"][0]["code"] == "PIPELINE_UNKNOWN"
    )
    assert harness.client.get(f"{API}/models/mock-t3d-basic").json()["availability"] == "planned"
    seed = harness.client.get(f"{API}/models/mock-t2d-basic").json()["options_schema"]["seed"]
    assert seed == {"type": "integer", "minimum": 0, "maximum": 4294967295, "default": None}
    (profile,) = harness.client.get(f"{API}/compute/profiles").json()["profiles"]
    assert (profile["profile_id"], profile["mode"], profile["enabled"]) == ("default", "mock", True)
    assert set(profile) == {
        "contract_version",
        "profile_id",
        "display_name",
        "owner_label",
        "mode",
        "enabled",
        "authorization_confirmed",
        "accelerators",
    }


def test_internal_errors_hide_details(harness, monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("secret internal detail C:\\Users\\x")

    monkeypatch.setattr(harness.client.app.state.service, "validate", boom)
    response = harness.client.post(f"{API}/validate", json=request_body())
    assert response.status_code == 500
    assert response.json()["errors"][0]["code"] == "INTERNAL_ERROR" and "secret" not in response.text
