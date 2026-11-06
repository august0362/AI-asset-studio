"""Compute clients. ``MockKaggleClient`` (M2); ``KaggleCliClient`` arrives in M3."""

from .base import ComputeClient, ComputeError, KaggleJobSpec, OutputSpec, RemoteRefNotFound, RemoteStatus
from .mock import FAILURES, MOCK_PROFILE_ID, SCENARIOS, MockKaggleClient, mock_profile

__all__ = [
    "FAILURES",
    "MOCK_PROFILE_ID",
    "SCENARIOS",
    "ComputeClient",
    "ComputeError",
    "KaggleJobSpec",
    "MockKaggleClient",
    "OutputSpec",
    "RemoteRefNotFound",
    "RemoteStatus",
    "mock_profile",
]
