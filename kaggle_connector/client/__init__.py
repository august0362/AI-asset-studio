"""Compute clients: ``MockKaggleClient`` (M2) and ``KaggleCliClient`` (M3, one authorized Kaggle profile)."""

from .base import ComputeClient, ComputeError, KaggleJobSpec, OutputSpec, RemoteRefNotFound, RemoteStatus
from .kaggle_cli import KaggleCliClient, KaggleProfileConfig
from .mock import FAILURES, MOCK_PROFILE_ID, SCENARIOS, MockKaggleClient, mock_profile

__all__ = [
    "FAILURES",
    "MOCK_PROFILE_ID",
    "SCENARIOS",
    "ComputeClient",
    "ComputeError",
    "KaggleCliClient",
    "KaggleJobSpec",
    "KaggleProfileConfig",
    "MockKaggleClient",
    "OutputSpec",
    "RemoteRefNotFound",
    "RemoteStatus",
    "mock_profile",
]
