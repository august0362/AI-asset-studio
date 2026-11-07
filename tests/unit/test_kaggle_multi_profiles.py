"""D-040: independent account clients, auth/quota caches and subprocess credentials. No network."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

import pytest

from kaggle_connector.client import KaggleCliClient, KaggleProfileConfig
from kaggle_connector.client.cli import KaggleCli
from tests.kaggle_fake import FakeKaggleCli

IDS = ("alpha", "beta", "gamma")


def configs():
    return [
        KaggleProfileConfig(pid, f"fake-owner-{pid}", True, True, token=f"fake-secret-{pid}-012345")
        for pid in IDS
    ] + [KaggleProfileConfig("disabled", "", False, False)]


@pytest.fixture
def accounts(tmp_path):
    fakes = {
        p.profile_id: FakeKaggleCli(tmp_path / p.profile_id, owner=p.username) for p in configs() if p.enabled
    }
    now = [0.0]
    client = KaggleCliClient(
        configs(),
        cli_factory=lambda p, r: fakes[p.profile_id],
        background_refresh=False,
        work_root=tmp_path / "work",
        monotonic=lambda: now[0],
    )
    yield client, fakes, now
    client.close()
    assert all(fake.closed for fake in fakes.values())


def test_auth_and_refresh_rate_limits_are_independent_per_profile(accounts):
    client, fakes, now = accounts
    for pid in IDS:
        assert client.refresh(pid)
        assert client.snapshot(pid).authentication_status == "authenticated"
        assert not client.refresh(pid)
        assert fakes[pid].calls == [["config", "view"], ["quota", "--format", "json"]]
    now[0] = 60
    client.snapshot("alpha", refresh=True)
    assert len(fakes["alpha"].calls) == 4
    assert len(fakes["beta"].calls) == 2
    client.snapshot("beta", refresh=True)
    assert len(fakes["beta"].calls) == 4
    with pytest.raises(KeyError):
        client.snapshot("disabled")
    assert [p.enabled for p in client.profiles()] == [True, True, True, False]


def test_swapped_token_invalidates_only_its_profile(accounts):
    client, fakes, _ = accounts
    fakes["beta"].owner = "different-fake-owner"
    for pid in IDS:
        client.refresh(pid)
    assert client.snapshot("beta").authentication_status == "invalid_credentials"
    assert not any(c[0] == "quota" for c in fakes["beta"].calls)
    for pid in ("alpha", "gamma"):
        assert client.snapshot(pid).authentication_status == "authenticated"
    assert not any(c[:2] == ["kernels", "push"] for f in fakes.values() for c in f.calls)


def test_five_minute_refresh_loops_are_independent_and_stop(tmp_path, monkeypatch):
    import kaggle_connector.client.kaggle_cli as module

    assert module.QUOTA_CACHE_SECONDS == 300
    monkeypatch.setattr(module, "QUOTA_CACHE_SECONDS", 0.02)
    monkeypatch.setattr(module, "REFRESH_MIN_INTERVAL", 0)
    blocked = threading.Event()
    release = threading.Event()
    fakes = {}

    class BlockingCli(FakeKaggleCli):
        def run(self, args, *, timeout):
            if self.owner == "fake-owner-alpha" and args == ["config", "view"]:
                blocked.set()
                assert release.wait(5)
            return super().run(args, timeout=timeout)

    def factory(profile, redact):
        fake = BlockingCli(tmp_path / profile.profile_id, owner=profile.username)
        fakes[profile.profile_id] = fake
        return fake

    client = KaggleCliClient(configs(), cli_factory=factory, work_root=tmp_path / "work")
    try:
        assert blocked.wait(2)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if all(len(fakes[pid].calls) >= 4 for pid in ("beta", "gamma")):
                break
            time.sleep(0.01)
        assert all(len(fakes[pid].calls) >= 4 for pid in ("beta", "gamma"))
        assert not fakes["alpha"].calls
    finally:
        release.set()
        client.close()
    assert all(not thread.is_alive() for thread in client._refreshers)


def test_all_disabled_profiles_need_no_cli_or_credentials(tmp_path):
    def forbidden(*args):
        raise AssertionError("disabled profile constructed a CLI")

    client = KaggleCliClient(
        [KaggleProfileConfig("disabled", "", False, False)],
        cli_factory=forbidden,
        work_root=tmp_path,
        background_refresh=False,
    )
    try:
        assert not client.profiles()[0].enabled and client.redaction_terms() == []
    finally:
        client.close()


def test_three_real_subprocess_envs_and_empty_config_dirs_are_isolated(monkeypatch):
    monkeypatch.setenv("KAGGLE_API_TOKEN", "inherited-secret")
    for profile in configs():
        if profile.enabled:
            monkeypatch.setenv(f"AAS_PROFILE_{profile.profile_id.upper()}_KAGGLE_API_TOKEN", profile.token)
    clients = [
        KaggleCli(token=p.token, username=p.username, executable=sys.executable)
        for p in configs()
        if p.enabled
    ]
    dirs = []
    try:
        for cli, profile in zip(clients, configs(), strict=False):
            result = cli.run(
                [
                    "-c",
                    "import json,os; print(json.dumps({k:v for k,v in os.environ.items() "
                    "if k.startswith(('KAGGLE','AAS_PROFILE'))}))",
                ],
                timeout=10,
            )
            assert result.ok
            env = json.loads(result.stdout)
            assert set(env) == {"KAGGLE_CONFIG_DIR", "KAGGLE_API_TOKEN", "KAGGLE_USERNAME"}
            assert env["KAGGLE_API_TOKEN"] == "[REDACTED]"
            assert env["KAGGLE_USERNAME"] == profile.username
            path = Path(env["KAGGLE_CONFIG_DIR"])
            dirs.append(path)
            assert path.is_dir() and not list(path.iterdir())
        assert len(set(dirs)) == 3
    finally:
        for cli in clients:
            cli.close()
    assert all(not path.exists() for path in dirs)
