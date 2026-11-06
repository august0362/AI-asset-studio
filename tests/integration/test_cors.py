"""CORS allows only the frontend dev origin (CONTRACTS §5), in either loopback spelling."""

from __future__ import annotations

import pytest

from aas_backend.app import allowed_origins
from tests.conftest import API


def test_loopback_aliases():
    assert allowed_origins("http://localhost:5173") == ["http://localhost:5173", "http://127.0.0.1:5173"]
    assert allowed_origins("http://127.0.0.1:5173") == ["http://127.0.0.1:5173", "http://localhost:5173"]
    assert allowed_origins("http://studio.example:5173") == ["http://studio.example:5173"]


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("http://localhost:5173", True),
        ("http://127.0.0.1:5173", True),
        ("http://127.0.0.1:4173", False),
        ("http://evil.example", False),
    ],
)
def test_preflight(harness, origin, allowed):
    response = harness.client.options(
        f"{API}/jobs",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )
    assert (response.headers.get("access-control-allow-origin") == origin) is allowed
