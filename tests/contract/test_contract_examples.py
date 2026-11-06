"""The canonical examples in docs/CONTRACTS.md validate against the Pydantic models, and the mocks match them.

Shared fixtures in ``tests/fixtures/contracts/*.json`` (CONTRACTS §11) are validated too when present.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from aas_backend.export_schemas import export
from aas_backend.schemas import ErrorResponse, GenerationResult, ValidationReport
from kaggle_connector.client import mock_profile
from kaggle_connector.resources import ResourceRequirements, parse_line, plan
from kaggle_connector.resources.contracts import (
    ComputeProfile,
    KaggleResourceSnapshot,
    OutputManifest,
    ResourcePlan,
)
from models.adapters import requirements_from
from models.contracts import (
    Catalog,
    CreateJobRequest,
    GenerationRequest,
    ModelCapabilities,
    ModelInvocation,
    UploadRecord,
)
from models.registry import build_catalog, default_registry
from models.registry.validation import parse_create_job_request

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "docs" / "CONTRACTS.md"
FIXTURES = ROOT / "tests" / "fixtures" / "contracts"
PLACEHOLDER_TIME = "2026-11-06T10:20:00Z"

SECTION_MODELS: dict[str, type[BaseModel]] = {
    "2.1": ModelCapabilities,
    "2.3": GenerationRequest,
    "2.4": ModelInvocation,
    "3.1": UploadRecord,
    "3.2": CreateJobRequest,
    "3.3": ValidationReport,
    "3.4": GenerationResult,
    "5.1": Catalog,
    "5.2": ErrorResponse,
    "6.1": ComputeProfile,
    "6.2": KaggleResourceSnapshot,
    "6.4": OutputManifest,
    "7.3": ResourcePlan,
}


def _strip_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))


def _objects(text: str) -> list[Any]:
    decoder, index, out = json.JSONDecoder(), 0, []
    text = text.strip()
    while index < len(text):
        value, end = decoder.raw_decode(text, index)
        out.append(value)
        index = end
        while index < len(text) and text[index].isspace():
            index += 1
    return out


def contract_blocks() -> list[tuple[str, str, str]]:
    """(section, language, body) for every fenced block in CONTRACTS.md."""
    section, blocks, lines = "", [], CONTRACTS.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        heading = re.match(r"^#{2,3} (\d+(?:\.\d+)?)\.? ", lines[i])
        if heading:
            section = heading.group(1)
        fence = re.match(r"^```(\w*)$", lines[i])
        if fence:
            body = []
            i += 1
            while not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            blocks.append((section, fence.group(1), "\n".join(body)))
        i += 1
    return blocks


def fill_placeholders(value: Any, key: str = "") -> Any:
    """The docs abbreviate some timestamps as "…"; give them a real value before validating."""
    if isinstance(value, dict):
        return {k: fill_placeholders(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [fill_placeholders(v, key) for v in value]
    if value == "…" and (key == "at" or key.endswith("_at")):
        return PLACEHOLDER_TIME
    return value


def json_examples() -> list[tuple[str, Any]]:
    examples = []
    for section, language, body in contract_blocks():
        if language in ("json", "jsonc"):
            for obj in _objects(_strip_comments(body)):
                examples.append((section, obj))
    return examples


EXAMPLES = json_examples()


def test_every_documented_example_is_covered():
    assert {section for section, _ in EXAMPLES} == set(SECTION_MODELS)
    assert len([s for s, _ in EXAMPLES if s == "3.2"]) == 3  # requests A, B, C


@pytest.mark.parametrize("section,example", EXAMPLES, ids=[f"§{s}" for s, _ in EXAMPLES])
def test_example_validates_against_its_model(section, example):
    model = SECTION_MODELS[section]
    if model is CreateJobRequest:
        request, errors = parse_create_job_request(example)
        assert request is not None, errors
        return
    payload = fill_placeholders(example)
    if model is GenerationResult:
        # §3.4 abbreviates compute.resource_plan to three fields of request B's plan; the full plan is §7.3.
        full_plan = next(obj for s, obj in EXAMPLES if s == "7.3")
        abbreviated = payload["compute"]["resource_plan"]
        assert {k: full_plan[k] for k in abbreviated} == abbreviated
        payload["compute"]["resource_plan"] = full_plan
    instance = model.model_validate(payload)
    if model is not GenerationResult:  # the §3.4 example also abbreviates timestamps
        assert instance.model_dump(mode="json") == example


def example(section: str) -> Any:
    return next(obj for s, obj in EXAMPLES if s == section)


def test_mock_multiview_record_is_the_section_2_1_example():
    assert default_registry().get("mock-i3d-multiview").model_dump(mode="json") == example("2.1")


def test_catalog_endpoint_payload_is_the_section_5_1_example():
    assert build_catalog().model_dump(mode="json") == example("5.1")


def test_mock_profile_catalog_is_the_section_6_1_catalog():
    assert [a.model_dump() for a in mock_profile().accelerators] == example("6.1")["accelerators"]


def test_planner_reproduces_the_section_7_3_plan():
    """Request B on a fresh snapshot with 18.5 h of GPU quota remaining."""
    from datetime import timedelta

    from kaggle_connector.resources import QuotaReading, build_snapshot
    from kaggle_connector.resources.contracts import utc_now

    now = utc_now()
    quota = QuotaReading(
        30.0, 11.5, 18.5, None, None, None, None, now - timedelta(minutes=1), "kaggle_cli_quota"
    )
    snapshot = build_snapshot(
        mock_profile(),
        auth_status="authenticated",
        quota=quota,
        session=None,
        telemetry=None,
        telemetry_source="none",
        now=now,
    )
    caps = default_registry().get("mock-i3d-multiview")
    requirements = ResourceRequirements.model_validate(requirements_from(caps).model_dump())
    profile = mock_profile().model_copy(update={"profile_id": "default"})
    assert plan(requirements, profile, snapshot, "gpu_t4x2").model_dump(mode="json") == example("7.3")
    assert plan(requirements, profile, snapshot, None).accelerator_id == "gpu_p100"


def test_section_6_4_protocol_lines_parse():
    lines = next(body for s, lang, body in contract_blocks() if s == "6.4" and lang == "").splitlines()
    kinds = [parse_line(line.replace("job_…", "job_x")).kind for line in lines]
    assert kinds == ["progress", "telemetry"]


def test_json_schema_export(tmp_path):
    written = export(tmp_path)
    assert len(written) >= 20
    request_schema = json.loads((tmp_path / "CreateJobRequest.schema.json").read_text(encoding="utf-8"))
    assert request_schema["additionalProperties"] is False
    assert "client_request_id" in request_schema["required"]
    for path in written:
        assert json.loads(path.read_text(encoding="utf-8"))["$id"].startswith("aas/contracts/1.0/")


# --- shared fixtures (written by the frontend task; optional here) -------------------------------------------


def classify(payload: dict[str, Any]) -> type[BaseModel] | None:
    keys = set(payload)
    rules = [
        ({"compute_profile_id", "freshness_status"}, KaggleResourceSnapshot),
        ({"model_id", "inputs", "runtime", "options_schema"}, ModelCapabilities),
        ({"pipelines", "asset_categories"}, Catalog),
        ({"valid", "errors", "warnings"}, ValidationReport),
        ({"job_id", "status_history"}, GenerationResult),
        ({"upload_id", "sha256", "expires_at"}, UploadRecord),
        ({"profile_id", "accelerators", "authorization_confirmed"}, ComputeProfile),
        ({"profile_id", "candidates", "estimate_basis"}, ResourcePlan),
        ({"client_request_id", "compute"}, CreateJobRequest),
    ]
    return next((model for required, model in rules if required <= keys), None)


FIXTURE_FILES = sorted(FIXTURES.glob("*.json")) if FIXTURES.is_dir() else []


@pytest.mark.skipif(not FIXTURE_FILES, reason="no shared fixtures in tests/fixtures/contracts yet")
@pytest.mark.parametrize("path", FIXTURE_FILES, ids=lambda p: p.name)
def test_shared_fixture_validates(path):
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload if isinstance(payload, list) else [payload]
    for item in items:
        model = classify(item) if isinstance(item, dict) else None
        if model is None:
            pytest.skip(f"{path.name}: payload type not recognized")
        if model is CreateJobRequest:
            assert parse_create_job_request(item)[0] is not None
        else:
            model.model_validate(item)
