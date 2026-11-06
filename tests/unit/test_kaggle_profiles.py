"""Kaggle-mode profile configuration (D-008, D-025): one active, authorized profile; others listed as disabled."""

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


def test_only_the_active_profile_is_enabled_and_carries_credentials():
    profiles = load_profiles(settings(compute_profiles="sunny,atume,duma", active_profile="sunny"), env())
    assert [(p.profile_id, p.enabled) for p in profiles] == [
        ("sunny", True),
        ("atume", False),
        ("duma", False),
    ]
    assert profiles[0].token == TOKENS["SUNNY"]
    assert profiles[1].token is None and profiles[2].token is None  # never loaded
    assert all(TOKENS["SUNNY"] not in repr(p) for p in profiles)
    public = [p.public().model_dump_json() for p in profiles]
    assert not any(t in text for text in public for t in TOKENS.values())
    assert all("-user" not in text for text in public)  # the account name is not the default display name


def test_several_profiles_need_an_explicit_choice():
    with pytest.raises(ProfileConfigError, match="AAS_ACTIVE_PROFILE"):
        load_profiles(settings(compute_profiles="sunny,atume"), env())
    single = load_profiles(settings(compute_profiles="sunny"), env())
    assert single[0].enabled


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"AAS_PROFILE_SUNNY_AUTHORIZATION_CONFIRMED": "false"}, "AUTHORIZATION_CONFIRMED"),
        ({"AAS_PROFILE_SUNNY_KAGGLE_API_TOKEN": ""}, "KAGGLE_API_TOKEN"),
        ({"AAS_PROFILE_SUNNY_KAGGLE_USERNAME": ""}, "KAGGLE_USERNAME"),
    ],
)
def test_an_unusable_active_profile_is_refused_without_printing_values(overrides, message):
    with pytest.raises(ProfileConfigError, match=message) as info:
        load_profiles(settings(compute_profiles="sunny,atume", active_profile="sunny"), env(**overrides))
    assert not any(t in str(info.value) for t in TOKENS.values())


def test_an_unauthorized_inactive_profile_does_not_block():
    profiles = load_profiles(
        settings(compute_profiles="sunny,atume", active_profile="sunny"),
        env(AAS_PROFILE_ATUME_AUTHORIZATION_CONFIRMED="false"),
    )
    assert profiles[1].authorization_confirmed is False and profiles[1].enabled is False


@pytest.mark.parametrize("value", ["Sunny!", "a", "sunny,sunny"])
def test_invalid_profile_lists(value):
    with pytest.raises(ProfileConfigError):
        load_profiles(settings(compute_profiles=value, active_profile="sunny"), env())


def test_unknown_active_profile():
    with pytest.raises(ProfileConfigError, match="not listed"):
        load_profiles(settings(compute_profiles="sunny", active_profile="duma"), env())


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
