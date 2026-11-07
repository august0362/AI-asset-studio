"""D-040 profile configuration: listed and confirmed means enabled; disabled credentials are never read."""

from __future__ import annotations

from pathlib import Path

import pytest

from aas_backend.profiles import ProfileConfigError, environment, load_profiles
from aas_backend.settings import Settings

TOKENS = {
    "SUNNY": "KGAT_sunny_secret_123456",
    "ATUME": "KGAT_atume_secret_123456",
    "DUMA": "KGAT_duma_secret_1234567",
}


def env(**overrides: str) -> dict[str, str]:
    values = {}
    for pid, token in TOKENS.items():
        values[f"AAS_PROFILE_{pid}_KAGGLE_USERNAME"] = f"{pid.lower()}-user"
        values[f"AAS_PROFILE_{pid}_KAGGLE_API_TOKEN"] = token
        values[f"AAS_PROFILE_{pid}_AUTHORIZATION_CONFIRMED"] = "true"
    values.update(overrides)
    return values


def settings(**values) -> Settings:
    return Settings(_env_file=None, compute_mode="kaggle", **values)


def test_three_confirmed_profiles_are_enabled_and_carry_only_their_credentials():
    profiles = load_profiles(settings(compute_profiles="sunny,atume,duma"), env())
    assert [(p.profile_id, p.enabled) for p in profiles] == [("sunny", True), ("atume", True), ("duma", True)]
    for p in profiles:
        assert p.token == TOKENS[p.profile_id.upper()]
        assert not any(t in repr(p) for t in TOKENS.values())
    public = [p.public().model_dump_json() for p in profiles]
    assert not any(t in text for text in public for t in TOKENS.values())
    assert all("-user" not in text for text in public)


def test_unconfirmed_credentials_are_never_read():
    class GuardedEnv(dict):
        def get(self, key, default=None):
            if key in {
                "AAS_PROFILE_ATUME_KAGGLE_USERNAME",
                "AAS_PROFILE_ATUME_KAGGLE_API_TOKEN",
                "AAS_PROFILE_ATUME_KAGGLE_KEY",
            }:
                raise AssertionError(f"disabled credential read: {key}")
            return super().get(key, default)

    profiles = load_profiles(
        settings(compute_profiles="sunny,atume,duma"),
        GuardedEnv(env(AAS_PROFILE_ATUME_AUTHORIZATION_CONFIRMED="false")),
    )
    assert [p.enabled for p in profiles] == [True, False, True]
    assert profiles[1].username == "" and profiles[1].token is None and profiles[1].legacy_key is None


@pytest.mark.parametrize("value", ["", " "])
@pytest.mark.parametrize("name", ["KAGGLE_USERNAME", "KAGGLE_API_TOKEN"])
def test_missing_enabled_credentials_fail_startup_without_printing_values(
    tmp_path, monkeypatch, caplog, name, value
):
    from aas_backend.app import create_app

    variable = f"AAS_PROFILE_ATUME_{name}"
    values = env(**{variable: value})
    monkeypatch.setattr("aas_backend.app.environment", lambda: values)
    data = tmp_path / "not-created"
    with pytest.raises(ProfileConfigError, match=variable) as info:
        create_app(settings(compute_profiles="sunny,atume,duma", data_dir=data))
    assert not data.exists()
    assert not any(t in str(info.value) + caplog.text for t in TOKENS.values())
    assert not any(f"{pid.lower()}-user" in str(info.value) + caplog.text for pid in TOKENS)


@pytest.mark.parametrize("value", [None, "", "unknown-profile"])
def test_active_profile_is_ignored_with_one_safe_notice(caplog, value):
    values = env(AAS_ACTIVE_PROFILE=value or "")
    profiles = load_profiles(settings(compute_profiles="sunny,atume,duma", active_profile=value), values)
    assert all(p.enabled for p in profiles)
    notices = [r.getMessage() for r in caplog.records if "AAS_ACTIVE_PROFILE" in r.getMessage()]
    assert len(notices) == 1 and "ignored" in notices[0]
    assert "unknown-profile" not in notices[0]
    assert not any(t in caplog.text for t in TOKENS.values())


def test_no_confirmed_profiles_is_a_valid_disabled_list():
    profiles = load_profiles(settings(compute_profiles="sunny,atume"), {})
    assert len(profiles) == 2 and not any(p.enabled or p.token or p.username for p in profiles)


@pytest.mark.parametrize("value", ["Sunny!", "a", "sunny,sunny", ""])
def test_invalid_profile_lists(value):
    with pytest.raises(ProfileConfigError):
        load_profiles(settings(compute_profiles=value), env())


def test_environment_overlays_the_env_file(tmp_path: Path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "AAS_PROFILE_X_KAGGLE_USERNAME=from-file\nAAS_PROFILE_Y_KAGGLE_USERNAME=file\n", encoding="utf-8"
    )
    monkeypatch.setenv("AAS_PROFILE_Y_KAGGLE_USERNAME", "from-env")
    values = environment(env_file)
    assert values["AAS_PROFILE_X_KAGGLE_USERNAME"] == "from-file"
    assert values["AAS_PROFILE_Y_KAGGLE_USERNAME"] == "from-env"


def test_test_switch_setting():
    assert Settings(_env_file=None, kaggle_test_failure="").kaggle_test_failure is None
    assert Settings(_env_file=None, kaggle_test_failure="kernel_error").kaggle_test_failure == "kernel_error"
    with pytest.raises(ValueError):
        Settings(_env_file=None, kaggle_test_failure="everything")
