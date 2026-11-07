"""D-040/D-041: FIFO session slots across profiles and v1/V2 jobs, using only the offline fake CLI."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient

from aas_backend.app import create_app
from aas_backend.errors import ApiError
from aas_backend.schemas import BatchRef
from kaggle_connector.client import KaggleCliClient
from models.registry import default_registry
from tests.conftest import API, Harness, make_settings, request_body
from tests.kaggle_fake import FakeKaggleCli
from tests.unit.test_kaggle_multi_profiles import IDS, configs


@dataclass
class MultiHarness:
    harness: Harness
    compute: KaggleCliClient
    fakes: dict[str, FakeKaggleCli]
    entered: threading.Event
    release: threading.Event

    def create(self, pid, kind="v1"):
        compute = {"profile_id": pid, "accelerator_id": "cpu"}
        if kind == "v1":
            response = self.harness.client.post(f"{API}/jobs", json=request_body(compute=compute))
            assert response.status_code == 201, response.text
            return response.json()["job_id"]
        service = self.harness.client.app.state.service
        record, created = service.create_batch_job(
            client_request_id=str(uuid.uuid4()),
            model_id="mock-t2d-basic",
            asset_category="character",
            tasks=[("front_01", "A ranger front view", {"width": 512, "height": 512, "seed": 42})],
            compute=compute,
            batch=BatchRef(
                character_id="chr_111111111111",
                manifest_id="bat_111111111111",
                group_id="grp_01",
                attempt=1,
                task_ids=["front_01"],
            ),
        )
        assert created
        return record.job_id


@pytest.fixture
def multi(tmp_path, request):
    sessions = getattr(request, "param", 1)
    entered, release = threading.Event(), threading.Event()

    class GatedCli(FakeKaggleCli):
        def run(self, args, *, timeout):
            if self.owner == "fake-owner-alpha" and args[:2] == ["kernels", "status"]:
                entered.set()
                assert release.wait(10)
            return super().run(args, timeout=timeout)

    fakes = {
        p.profile_id: GatedCli(
            tmp_path / "fake" / p.profile_id, owner=p.username, denied_status_calls=0, queued_status_calls=0
        )
        for p in configs()
        if p.enabled
    }
    compute = KaggleCliClient(
        configs(),
        cli_factory=lambda p, r: fakes[p.profile_id],
        background_refresh=False,
        work_root=tmp_path / "work",
    )
    for pid in IDS:
        compute.refresh(pid)
    settings = make_settings(tmp_path / "data", compute_mode="kaggle", max_parallel_sessions=sessions)
    try:
        with TestClient(create_app(settings, client=compute, registry=default_registry())) as client:
            h = Harness(client, compute, tmp_path / "data", settings)
            yield MultiHarness(h, compute, fakes, entered, release)
            release.set()
    finally:
        release.set()
        compute.close()


@pytest.mark.parametrize(
    "first_kind,second_kind", [("v1", "v1"), ("v1", "batch"), ("batch", "v1"), ("batch", "batch")]
)
def test_one_slot_fifo_keeps_other_profiles_created_until_terminal(multi, first_kind, second_kind):
    a = multi.create("alpha", first_kind)
    assert multi.entered.wait(5)
    b = multi.create("beta", second_kind)
    c = multi.create("gamma")
    client = multi.harness.client
    for job_id in (b, c):
        waiting = client.get(f"{API}/jobs/{job_id}").json()
        assert waiting["status"] == "created"
        assert waiting["execution"]["submitted_at"] is None
        assert waiting["execution"]["remote_ref"] is None
    assert not multi.fakes["beta"].kernels and not multi.fakes["gamma"].kernels
    multi.release.set()
    done = [multi.harness.wait(job_id) for job_id in (a, b, c)]
    assert all(job["status"] == "completed" for job in done)
    for pid, job in zip(IDS, done, strict=True):
        assert job["compute"]["profile_id"] == pid
        assert job["execution"]["remote_ref"].startswith(f"{pid}/")
        assert len(multi.fakes[pid].kernels) == 1
    for previous, following in pairwise(done):
        assert previous["updated_at"] <= following["execution"]["submitted_at"]
    assert (done[0]["request"]["batch"] is not None) == (first_kind == "batch")
    assert (done[1]["request"]["batch"] is not None) == (second_kind == "batch")


@pytest.mark.parametrize("failure", ["submit", "kernel_error"])
def test_failed_job_is_never_resubmitted_or_moved_to_another_profile(multi, failure):
    multi.release.set()
    fake = multi.fakes["alpha"]
    if failure == "submit":
        fake.fail_push = "deliberate fake submission failure"
    else:
        fake.break_entry = True
    a = multi.create("alpha")
    failed = multi.harness.wait(a)
    assert failed["status"] == "failed" and failed["compute"]["profile_id"] == "alpha"
    for pid in ("beta", "gamma"):
        assert not any(call[:2] == ["kernels", "push"] for call in multi.fakes[pid].calls)
    assert len(multi.harness.client.get(f"{API}/jobs").json()["jobs"]) == 1
    b = multi.create("beta")  # a separate explicit request, never a retry/failover of A
    succeeded = multi.harness.wait(b)
    assert succeeded["status"] == "completed" and succeeded["execution"]["retry_of"] is None
    assert succeeded["compute"]["profile_id"] == "beta"
    assert sum(call[:2] == ["kernels", "push"] for call in fake.calls) == 1
    assert multi.harness.client.get(f"{API}/jobs/{a}").json()["status"] == "failed"


def test_all_profile_tokens_are_absent_from_logs_payloads_data_and_packages(multi, caplog):
    multi.release.set()
    secrets = [p.token for p in configs() if p.enabled]
    users = [p.username for p in configs() if p.enabled]
    for fake in multi.fakes.values():
        fake.secret_echo = " ".join(secrets + users)
    bodies = []
    for pid in IDS:
        job = multi.harness.wait(multi.create(pid))
        assert job["status"] == "completed"
        for route in (
            f"/jobs/{job['job_id']}",
            f"/jobs/{job['job_id']}/logs",
            f"/compute/profiles/{pid}/snapshot",
        ):
            bodies.append(multi.harness.client.get(API + route).text)
    for route in ("/jobs", "/compute/profiles"):
        bodies.append(multi.harness.client.get(API + route).text)
    stored = [
        p.read_bytes().decode("utf-8", "replace") for p in multi.harness.data_dir.rglob("*") if p.is_file()
    ]
    packages = [source for fake in multi.fakes.values() for source in fake.pushed_sources]
    for text in [*bodies, *stored, *packages, caplog.text]:
        assert not any(secret in text for secret in secrets)
    # Private kernel metadata needs its remote owner's name, but persisted local
    # data, API responses and logs must use only the profile ID.
    for text in [*bodies, *stored, caplog.text]:
        assert not any(user in text for user in users)
    assert any("[REDACTED]" in text for text in stored)


@pytest.mark.parametrize("multi", [2], indirect=True)
def test_parallel_sessions_use_one_profile_at_a_time(multi):
    """Two slots: a second alpha job starts beside the first; a beta job waits until no alpha session runs."""
    a = multi.create("alpha")
    assert multi.entered.wait(5)
    b = multi.create("alpha")
    c = multi.create("beta")
    client = multi.harness.client
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and not client.get(f"{API}/jobs/{b}").json()["execution"]["remote_ref"]:
        time.sleep(0.02)
    assert client.get(f"{API}/jobs/{b}").json()["execution"]["remote_ref"].startswith("alpha/")
    waiting = client.get(f"{API}/jobs/{c}").json()
    assert waiting["status"] == "created" and waiting["scheduling"]["queue_state"] == "waiting"
    assert not multi.fakes["beta"].kernels
    multi.release.set()
    done = {job_id: multi.harness.wait(job_id) for job_id in (a, b, c)}
    assert all(job["status"] == "completed" for job in done.values())
    assert done[c]["execution"]["submitted_at"] >= max(done[a]["updated_at"], done[b]["updated_at"])


def test_a_run_group_needs_one_profile(multi):
    service = multi.harness.client.app.state.service
    ids = []
    for pid in ("alpha", "beta"):
        body = request_body(compute={"profile_id": pid, "accelerator_id": "gpu_t4x2"}, auto_run=False)
        response = multi.harness.client.post(f"{API}/jobs", json=body)
        assert response.status_code == 201, response.text
        ids.append(response.json()["job_id"])
    with pytest.raises(ApiError) as caught:
        service.create_group({"job_ids": ids})
    assert caught.value.errors[0].details["reason"] == "profile"
