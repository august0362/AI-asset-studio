"""Kaggle compute profiles from ``.env`` / the environment (CONTRACTS §6.1, §10; DECISIONS D-008, D-025).

``AAS_COMPUTE_PROFILES`` lists every profile the UI shows. ``AAS_ACTIVE_PROFILE`` names the **one** enabled profile
(optional when only one is listed). Only the active profile's credentials are read; the others are listed as
disabled, and a profile is never enabled without ``AUTHORIZATION_CONFIRMED=true``. Error messages name the variable,
never its value.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

from kaggle_connector.client import KaggleProfileConfig
from models.contracts.common import PROFILE_ID_PATTERN

from .settings import Settings

PROFILE_ID = re.compile(PROFILE_ID_PATTERN)


class ProfileConfigError(ValueError):
    """The kaggle-mode profile configuration is unusable. The message is safe to print."""


def environment(env_file: Path | None = Path(".env")) -> dict[str, str]:
    """``.env`` values overlaid by the process environment (the same precedence as pydantic-settings)."""
    values: dict[str, str] = {}
    if env_file is not None and env_file.is_file():
        values.update({k: v for k, v in dotenv_values(env_file).items() if v is not None})
    values.update(os.environ)
    return values


def _var(profile_id: str, name: str) -> str:
    return f"AAS_PROFILE_{profile_id.upper().replace('-', '_')}_{name}"


def load_profiles(settings: Settings, env: Mapping[str, str]) -> list[KaggleProfileConfig]:
    ids = [p.strip().lower() for p in settings.compute_profiles.split(",") if p.strip()]
    if not ids:
        raise ProfileConfigError("AAS_COMPUTE_PROFILES lists no profile.")
    for profile_id in ids:
        if not PROFILE_ID.match(profile_id):
            raise ProfileConfigError(f"AAS_COMPUTE_PROFILES: invalid profile id {profile_id!r}.")
    if len(set(ids)) != len(ids):
        raise ProfileConfigError("AAS_COMPUTE_PROFILES lists a profile twice.")
    active = (settings.active_profile or "").strip().lower() or None
    if active is None:
        if len(ids) > 1:
            raise ProfileConfigError(
                "Several profiles are listed: set AAS_ACTIVE_PROFILE to the one profile to enable (D-008)."
            )
        active = ids[0]
    if active not in ids:
        raise ProfileConfigError("AAS_ACTIVE_PROFILE is not listed in AAS_COMPUTE_PROFILES.")

    profiles = []
    for profile_id in ids:
        username = (env.get(_var(profile_id, "KAGGLE_USERNAME")) or "").strip()
        confirmed = (env.get(_var(profile_id, "AUTHORIZATION_CONFIRMED")) or "").strip().lower() == "true"
        is_active = profile_id == active
        token = key = None
        if is_active:
            if not confirmed:
                raise ProfileConfigError(
                    f"{_var(profile_id, 'AUTHORIZATION_CONFIRMED')} must be true to enable this profile."
                )
            if not username:
                raise ProfileConfigError(f"{_var(profile_id, 'KAGGLE_USERNAME')} is empty.")
            token = (env.get(_var(profile_id, "KAGGLE_API_TOKEN")) or "").strip() or None
            key = (env.get(_var(profile_id, "KAGGLE_KEY")) or "").strip() or None
            if not token and not key:
                raise ProfileConfigError(f"{_var(profile_id, 'KAGGLE_API_TOKEN')} is empty.")
        profiles.append(
            KaggleProfileConfig(
                profile_id=profile_id,
                username=username,
                authorization_confirmed=confirmed,
                enabled=is_active,
                token=token,
                legacy_key=key,
                display_name=(env.get(_var(profile_id, "DISPLAY_NAME")) or "").strip() or None,
                owner_label=(env.get(_var(profile_id, "OWNER_LABEL")) or "").strip() or None,
            )
        )
    return profiles
