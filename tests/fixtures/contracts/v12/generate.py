"""Regenerate the contract v1.2 fixtures (CONTRACTS §14) from a real mock-mode run.

    .venv/Scripts/python.exe tests/fixtures/contracts/v12/generate.py

Writes the run-control, run-group, bulk-delete and error payloads exactly as the backend serves them in mock mode.
Nothing here contacts Kaggle. Rerun it after a §14 contract change; the IDs and timestamps change on every run.
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "interface" / "backend")]

from fastapi.testclient import TestClient  # noqa: E402

from aas_backend.app import create_app  # noqa: E402
from aas_backend.settings import Settings  # noqa: E402
from kaggle_connector.client import mock as mock_module  # noqa: E402
from models.contracts import CreateJobRequest, ModelCapabilities  # noqa: E402
from models.registry import MOCK_CAPABILITIES, ModelRegistry, full_registry  # noqa: E402

API = "/api/v1"
GROUPABLE = "mock-t2d-group"


def registry() -> ModelRegistry:
    base = MOCK_CAPABILITIES[0].model_dump()
    record = {**base, "model_id": GROUPABLE, "display_name": "Mock groupable Text→2D"}
    record["runtime"] = {**base["runtime"], "minimum_gpu_vram_bytes": 8 * 2**30}
    return ModelRegistry([*MOCK_CAPABILITIES, ModelCapabilities.model_validate(record)])


def body(**overrides) -> dict:
    payload = {
        "contract_version": "1.0",
        "client_request_id": str(uuid.uuid4()),
        "pipeline_type": "text_to_2d",
        "asset_category": "character",
        "model_id": GROUPABLE,
        "prompt": "A knight in silver armor, full body",
        "inputs": [],
        "options": {"seed": 42, "width": 512, "height": 512},
        "output_format": "png",
        "compute": {"profile_id": "default", "accelerator_id": "gpu_t4x2"},
    }
    payload.update(overrides)
    return payload


def wait(client, job_id, done=("completed", "failed"), timeout=60.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"{API}/jobs/{job_id}").json()
        if job["status"] in done:
            return job
        time.sleep(0.05)
    raise RuntimeError(f"{job_id} did not finish")


def write(name: str, payload) -> None:
    (HERE / f"{name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="aas-v12-") as tmp:
        tmp = Path(tmp)
        compute = mock_module.MockKaggleClient(
            queue_seconds=0.05, run_seconds=2.0, remote_root=tmp / "remote"
        )
        settings = Settings(_env_file=None, data_dir=tmp / "data", poll_seconds=0.05, mock_queue_seconds=0.05)
        with TestClient(create_app(settings, client=compute, registry=registry())) as client:
            blocker = client.post(f"{API}/jobs", json=body()).json()["job_id"]
            wait(client, blocker, done=("queued", "running"))
            waiting = client.post(f"{API}/jobs", json=body()).json()["job_id"]
            write("job_waiting", client.get(f"{API}/jobs/{waiting}").json())
            held = client.post(f"{API}/jobs", json=body(auto_run=False)).json()
            write("job_held", held)
            write("job_list", client.get(f"{API}/jobs").json())
            started = client.patch(f"{API}/jobs/{blocker}", json={"auto_run": False})
            write("error_job_already_started", started.json())

            a = client.post(f"{API}/jobs", json=body(auto_run=False)).json()["job_id"]
            b = client.post(
                f"{API}/jobs", json=body(auto_run=False, options={"seed": 7, "width": 512, "height": 512})
            )
            b = b.json()["job_id"]
            invalid = client.post(f"{API}/jobs/groups", json={"job_ids": [a, waiting]})
            write("error_job_group_invalid", invalid.json())
            group = client.post(f"{API}/jobs/groups", json={"job_ids": [a, b]})
            write("run_group", group.json())
            write("job_grouped", wait(client, a))
            wait(client, b)
            wait(client, blocker)
            wait(client, waiting)
            write(
                "bulk_delete",
                client.post(
                    f"{API}/jobs/delete",
                    json={"job_ids": [blocker, held["job_id"], "job_20261106T101500Z_a1b2c3"]},
                ).json(),
            )
        compute.close()

        coded = (
            "class PromptTooLong(Exception):\n"
            "    aas_code = 'MODEL_PROMPT_TOO_LONG'\n"
            "    aas_details = {'tokens': 2300, 'max_tokens': 2048}\n"
            "def main(arguments, input_dir, output_dir, progress):\n"
            "    raise PromptTooLong('The prompt has 2300 tokens; this model reads at most 2048.')\n"
        )
        mock_module._KERNEL_ERROR_ENTRY = coded
        compute = mock_module.MockKaggleClient(
            queue_seconds=0.05, run_seconds=0.0, failure="kernel_error", remote_root=tmp / "remote2"
        )
        settings = Settings(
            _env_file=None, data_dir=tmp / "data2", poll_seconds=0.05, mock_queue_seconds=0.05
        )
        with TestClient(create_app(settings, client=compute, registry=registry())) as client:
            job = client.post(f"{API}/jobs", json=body()).json()["job_id"]
            write("job_failed_prompt_too_long", wait(client, job))
        compute.close()

    klein = full_registry().adapter("flux2-klein-4b")
    request = CreateJobRequest.model_validate(
        body(model_id="flux2-klein-4b", inputs=[{"upload_id": "upl_" + "0" * 32, "role": "style_reference"}])
    )
    write(
        "warning_runtime_exceeds_estimate", klein.validate_model_specific(request)[0].model_dump(mode="json")
    )
    print("v1.2 fixtures written to", HERE)


if __name__ == "__main__":
    main()
