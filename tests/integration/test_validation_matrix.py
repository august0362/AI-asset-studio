"""Validation matrix V-01…V-20 (CONTRACTS §8.4) through ``POST /validate`` and ``POST /jobs``."""

from __future__ import annotations

import pytest

from models.contracts import ModelCapabilities
from models.registry import MOCK_CAPABILITIES, ModelRegistry
from tests.conftest import API, codes, i3d_body, image_bytes, noise_png, request_body


def validate(h, body):
    response = h.client.post(f"{API}/validate", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def assert_rejected(h, body, expected_codes):
    """Invalid requests: report lists the codes; POST /jobs returns 422; no job is created; no remote call."""
    report = validate(h, body)
    assert (not report["valid"] and report["resource_plan"] is None) or not report["valid"]
    for code in expected_codes:
        assert code in codes(report["errors"]), report["errors"]
    response = h.client.post(f"{API}/jobs", json=body)
    assert response.status_code == 422
    assert codes(response.json()["errors"]) == codes(report["errors"])
    assert h.client.get(f"{API}/jobs").json()["jobs"] == []
    assert h.compute._runs == {}
    return report


def single_body(inputs, **overrides):
    return i3d_body(inputs, model_id="mock-i3d-single", **overrides)


def test_v01_text_only_model_gets_an_image(harness):
    upload = harness.upload(image_bytes(512, 512))
    assert_rejected(
        harness,
        request_body(inputs=[{"upload_id": upload["upload_id"], "role": "style_reference"}]),
        ["MODEL_IMAGE_INPUT_NOT_SUPPORTED"],
    )


def test_v02_single_image_model_gets_three_images(harness):
    report = assert_rejected(
        harness,
        single_body(harness.upload_views()),
        ["MODEL_INPUT_COUNT_EXCEEDED", "MODEL_IMAGE_ROLE_UNSUPPORTED"],
    )
    exceeded = next(e for e in report["errors"] if e["code"] == "MODEL_INPUT_COUNT_EXCEEDED")
    assert exceeded["details"] == {"max_images": 1, "provided": 3}
    assert exceeded["message"] == "This model accepts at most 1 image; 3 were provided."
    unsupported = [e["field"] for e in report["errors"] if e["code"] == "MODEL_IMAGE_ROLE_UNSUPPORTED"]
    assert unsupported == ["inputs[1].role", "inputs[2].role"]


def test_v03_multiview_missing_side_view(harness):
    report = assert_rejected(
        harness, i3d_body(harness.upload_views(("front", "back"))), ["MODEL_REQUIRED_VIEW_MISSING"]
    )
    error = report["errors"][0]
    assert error["details"] == {"missing_roles": ["side"]} and error["field"] == "inputs"
    assert error["message"] == "This model requires a side view. Add an image with the role 'side'."


def test_v04_valid_full_body_front_side_back(harness):
    report = validate(harness, i3d_body(harness.upload_views()))
    assert report["valid"] and report["errors"] == [] and report["warnings"] == []
    plan = report["resource_plan"]
    assert (plan["fit"], plan["accelerator_id"], plan["required_seconds"]) == ("ok", "gpu_t4x2", 1950)


def test_v05_gpu_only_model_with_tpu(harness):
    body = i3d_body(harness.upload_views(), compute={"profile_id": "default", "accelerator_id": "tpu_vm"})
    report = assert_rejected(harness, body, ["MODEL_ACCELERATOR_INCOMPATIBLE"])
    assert report["errors"][0]["field"] == "compute.accelerator_id"


def test_v06_unknown_minimum_vram(harness):
    report = validate(harness, single_body(harness.upload_views(("front",))))
    assert report["valid"] and codes(report["warnings"]) == ["COMPUTE_VRAM_UNKNOWN"]
    assert report["resource_plan"]["fit"] == "unknown"


def test_v07_kaggle_quota_missing(harness_factory):
    h = harness_factory(scenario="quota_missing")
    report = validate(h, i3d_body(h.upload_views()))
    assert report["valid"] and codes(report["warnings"]) == ["COMPUTE_QUOTA_UNKNOWN"]
    assert report["resource_plan"]["fit"] == "unknown"


def test_v08_gpu0_and_gpu1_memory_differ(harness_factory):
    h = harness_factory(scenario="gpu_split")
    devices = h.client.get(f"{API}/compute/profiles/default/snapshot").json()["gpu_devices"]
    assert [(d["index"], d["vram_used_bytes"], d["utilization_percent"]) for d in devices] == [
        (0, 13421772800, 97.0),
        (1, 524288000, 4.0),
    ]


def test_v09_job_exceeds_the_session_limit(harness_factory):
    long_job = ModelCapabilities.model_validate(
        {
            **MOCK_CAPABILITIES[0].model_dump(),
            "model_id": "fixture-long-runtime",
            "runtime": {**MOCK_CAPABILITIES[0].runtime.model_dump(), "estimated_runtime_seconds": 40000},
        }
    )
    h = harness_factory(registry=ModelRegistry([*MOCK_CAPABILITIES, long_job]))
    report = assert_rejected(
        h, request_body(model_id="fixture-long-runtime"), ["COMPUTE_SESSION_LIMIT_EXCEEDED"]
    )
    assert report["errors"][0]["details"]["required_seconds"] == 60600


@pytest.mark.parametrize(
    "scenario,freshness,code",
    [
        ("telemetry_unavailable", "unavailable", "COMPUTE_TELEMETRY_UNAVAILABLE"),
        ("telemetry_stale", "stale", "COMPUTE_TELEMETRY_STALE"),
    ],
)
def test_v10_telemetry_stale_or_unavailable(harness_factory, scenario, freshness, code):
    snapshot = (
        harness_factory(scenario=scenario).client.get(f"{API}/compute/profiles/default/snapshot").json()
    )
    assert (
        snapshot["freshness_status"]["host"] == freshness and snapshot["freshness_status"]["gpu"] == freshness
    )
    assert code in codes(snapshot["error"])
    if scenario == "telemetry_stale":
        assert snapshot["cpu_utilization_percent"] is not None  # last values kept, marked stale
        assert all(e["details"]["age_seconds"] >= 120 for e in snapshot["error"] if e["code"] == code)


def test_v11_required_prompt_is_blank(harness):
    assert_rejected(harness, request_body(prompt="   "), ["MODEL_PROMPT_REQUIRED"])


def test_v12_unsupported_file_format(harness):
    upload = harness.upload(image_bytes(1024, 1024, "WEBP"), "front.webp", "image/webp")
    assert upload["mime_type"] == "image/webp"
    report = assert_rejected(
        harness,
        single_body([{"upload_id": upload["upload_id"], "role": "front"}]),
        ["MODEL_UNSUPPORTED_FILE_FORMAT"],
    )
    assert report["errors"][0]["field"] == "inputs[0].upload_id"


def test_v13_file_too_large_for_the_model(harness):
    big = harness.upload(noise_png(3000, 3000), "front.png")
    assert 20971520 < big["size_bytes"] <= 52428800
    side = harness.upload_views(("side",))[0]
    assert_rejected(
        harness, i3d_body([{"upload_id": big["upload_id"], "role": "front"}, side]), ["MODEL_FILE_TOO_LARGE"]
    )


def test_v14_wrong_dimensions(harness):
    small = harness.upload(image_bytes(256, 256))
    side = harness.upload_views(("side",))[0]
    report = assert_rejected(
        harness,
        i3d_body([{"upload_id": small["upload_id"], "role": "front"}, side]),
        ["MODEL_IMAGE_DIMENSIONS_INVALID"],
    )
    details = report["errors"][0]["details"]
    assert (details["width"], details["height"], details["allowed"]["min_width"]) == (256, 256, 512)


def test_v15_unsupported_category(harness):
    assert_rejected(
        harness, i3d_body(harness.upload_views(), asset_category="weapon"), ["MODEL_CATEGORY_INCOMPATIBLE"]
    )


def test_v16_unsupported_output(harness):
    assert_rejected(harness, request_body(output_format="glb"), ["MODEL_OUTPUT_FORMAT_UNSUPPORTED"])


def test_v17_unsupported_option(harness):
    report = assert_rejected(
        harness,
        single_body(harness.upload_views(("front",)), options={"texture_resolution": 2048}),
        ["MODEL_OPTION_UNSUPPORTED"],
    )
    assert report["errors"][0]["field"] == "options.texture_resolution"


def test_v18_insufficient_quota(harness_factory):
    h = harness_factory(scenario="quota_low")
    report = assert_rejected(h, i3d_body(h.upload_views()), ["COMPUTE_QUOTA_INSUFFICIENT"])
    assert report["errors"][0]["retryable"] is True
    assert report["errors"][0]["details"]["quota_remaining_seconds"] == 1080


def test_v19_model_switch_keeps_uploads(harness):
    views = harness.upload_views()
    assert validate(harness, i3d_body(views))["valid"]
    report = validate(harness, single_body(views))  # switch multiview -> single
    assert "MODEL_INPUT_COUNT_EXCEEDED" in codes(report["errors"])
    assert codes(report["errors"]).count("MODEL_IMAGE_ROLE_UNSUPPORTED") == 2
    for view in views:
        assert harness.client.get(f"{API}/uploads/{view['upload_id']}/content").status_code == 200


def test_v20_planned_pipeline(harness):
    body = request_body(
        pipeline_type="text_to_3d",
        asset_category="companion",
        model_id="mock-t3d-basic",
        prompt="Small fox spirit companion with glowing tail",
        options={},
        output_format="glb",
    )
    report = assert_rejected(harness, body, ["PIPELINE_NOT_AVAILABLE"])
    assert codes(report["errors"]) == ["PIPELINE_NOT_AVAILABLE"]  # stage 2 short-circuits


# --- other stage checks --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mutate,code,field",
    [
        (lambda b: b.update(contract_version="2.0"), "CONTRACT_VERSION_UNSUPPORTED", "contract_version"),
        (lambda b: b.update(extra_field=1), "REQUEST_FIELD_INVALID", "extra_field"),
        (lambda b: b.pop("compute"), "REQUEST_FIELD_INVALID", "compute"),
        (lambda b: b.update(client_request_id="not-a-uuid"), "REQUEST_FIELD_INVALID", "client_request_id"),
        (lambda b: b.update(inputs=[{"upload_id": "upl_x"}]), "REQUEST_FIELD_INVALID", "inputs[0].role"),
        (lambda b: b.update(pipeline_type="text_to_video"), "PIPELINE_UNKNOWN", "pipeline_type"),
        (lambda b: b.update(asset_category="vehicle"), "ASSET_CATEGORY_UNKNOWN", "asset_category"),
        (lambda b: b.update(model_id="does-not-exist"), "MODEL_NOT_FOUND", "model_id"),
        (lambda b: b.update(model_id="mock-i3d-single"), "MODEL_PIPELINE_INCOMPATIBLE", "model_id"),
        (lambda b: b.update(prompt="x" * 1001), "MODEL_PROMPT_TOO_LONG", "prompt"),
        (lambda b: b.update(options={"seed": -1}), "MODEL_OPTION_INVALID", "options.seed"),
        (lambda b: b.update(options={"width": 640}), "MODEL_OPTION_INVALID", "options.width"),
        (lambda b: b.update(options={"seed": True}), "MODEL_OPTION_INVALID", "options.seed"),
        (lambda b: b.update(options={"width": None}), "MODEL_OPTION_INVALID", "options.width"),
        (
            lambda b: b.update(compute={"profile_id": "alice", "accelerator_id": None}),
            "COMPUTE_PROFILE_NOT_FOUND",
            "compute.profile_id",
        ),
        (
            lambda b: b.update(inputs=[], model_id="mock-t2d-basic", prompt=None),
            "MODEL_PROMPT_REQUIRED",
            "prompt",
        ),
    ],
)
def test_stage_errors(harness, mutate, code, field):
    body = request_body()
    mutate(body)
    report = validate(harness, body)
    match = [e for e in report["errors"] if e["code"] == code]
    assert match and match[0]["field"] == field, report["errors"]


def test_unknown_or_expired_upload_and_prompt_not_supported(harness):
    body = single_body([{"upload_id": "upl_" + "0" * 32, "role": "front"}], prompt="a knight")
    report = validate(harness, body)
    assert set(codes(report["errors"])) == {"UPLOAD_NOT_FOUND", "MODEL_PROMPT_NOT_SUPPORTED"}


def test_duplicate_views_and_insufficient_count(harness):
    front = harness.upload_views(("front",))[0]
    report = validate(harness, i3d_body([front, {**front}]))
    assert "MODEL_IMAGE_ROLE_DUPLICATE" in codes(report["errors"])
    assert "MODEL_INPUT_COUNT_INSUFFICIENT" in codes(validate(harness, i3d_body([front]))["errors"])


def test_experimental_model_warns(harness):
    report = validate(
        harness,
        request_body(
            model_id="mock-t2d-styleref",
            options={},
            compute={"profile_id": "default", "accelerator_id": "gpu_t4x2"},
        ),
    )
    assert report["valid"] and "MODEL_EXPERIMENTAL" in codes(report["warnings"])


def test_malformed_json_is_400(harness):
    response = harness.client.post(
        f"{API}/validate", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400 and codes(response.json()["errors"]) == ["REQUEST_FIELD_INVALID"]
