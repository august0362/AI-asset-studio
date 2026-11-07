"""Authorized compute profiles (CONTRACTS §6.1, §10; D-040).

Listed, confirmed profiles are enabled. Only their credentials are read. Unconfirmed profiles remain listed as
disabled. The obsolete ``AAS_ACTIVE_PROFILE`` is ignored; notices and errors name variables, never secret values.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Mapping
from pathlib import Path

from dotenv import dotenv_values

from kaggle_connector.client import KaggleProfileConfig
from models.contracts.common import PROFILE_ID_PATTERN

from .settings import Settings

PROFILE_ID = re.compile(PROFILE_ID_PATTERN)
log = logging.getLogger("aas_backend")


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
    if settings.active_profile is not None or "AAS_ACTIVE_PROFILE" in env:
        log.warning("AAS_ACTIVE_PROFILE is obsolete and ignored (D-040).")

    profiles = []
    for profile_id in ids:
        confirmed = (env.get(_var(profile_id, "AUTHORIZATION_CONFIRMED")) or "").strip().lower() == "true"
        username = ""
        token = None
        if confirmed:
            username = (env.get(_var(profile_id, "KAGGLE_USERNAME")) or "").strip()
            if not username:
                raise ProfileConfigError(f"{_var(profile_id, 'KAGGLE_USERNAME')} is empty.")
            token = (env.get(_var(profile_id, "KAGGLE_API_TOKEN")) or "").strip() or None
            if not token:
                raise ProfileConfigError(f"{_var(profile_id, 'KAGGLE_API_TOKEN')} is empty.")
        profiles.append(
            KaggleProfileConfig(
                profile_id=profile_id,
                username=username,
                authorization_confirmed=confirmed,
                enabled=confirmed,
                token=token,
                display_name=(env.get(_var(profile_id, "DISPLAY_NAME")) or "").strip() or None,
                owner_label=(env.get(_var(profile_id, "OWNER_LABEL")) or "").strip() or None,
            )
        )
    return profiles
