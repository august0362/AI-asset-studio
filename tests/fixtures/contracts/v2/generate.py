"""Regenerate the Character Production fixtures (CONTRACTS §13, TEST_PLAN §1) from a real mock-mode run.

    .venv/Scripts/python.exe tests/fixtures/contracts/v2/generate.py

Writes ``example_*.json`` (the §13.6.2 examples, verbatim from CONTRACTS.md) and the payloads below, exactly as the
backend serves them in mock mode. Nothing here contacts Kaggle. Rerun it after a §13 contract change.

``batch_jobs.json`` holds the v1 job record of every batch attempt. ``files/`` holds the bytes behind every image URL
the fixtures mention (``content_url``, ``cover_url``, and ``/jobs/{job_id}/artifacts/{artifact_id}/content`` for each
job artifact they reference); ``files/index.json`` maps each URL to its file, MIME type, size and SHA-256. The bytes
come from the same run as the JSON, so every checksum matches (preview seeds are random, so a rerun changes both).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "interface" / "backend")]

from fastapi.testclient import TestClient  # noqa: E402

from aas_backend.app import create_app  # noqa: E402
from kaggle_connector.client import MockKaggleClient  # noqa: E402
from models.registry import default_registry  # noqa: E402
from tests.character_helpers import API, Driver, V, rid, s1, s2, s3_profile, s3_selected, s4, s5_items  # noqa: E402
from tests.conftest import Harness, image_bytes, make_settings  # noqa: E402

EXAMPLE_NAMES = [
    "example_create_character_request",
    "example_character",
    "example_character_list",
    "example_save_draft_request",
    "example_error_response",
    "example_batch_manifest",
]


def examples() -> dict[str, object]:
    from tests.contract.test_contract_examples import contract_blocks

    found = []
    decoder = json.JSONDecoder()
    for section, language, body in contract_blocks():
        if section == "13.6" and language == "json":
            found.append(decoder.decode(body))
    assert len(found) == len(EXAMPLE_NAMES), len(found)
    return dict(zip(EXAMPLE_NAMES, found, strict=True))


def write(name: str, payload: object) -> None:
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    (HERE / f"{name}.json").write_text(text, encoding="utf-8")


FILES = HERE / "files"
EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def referenced_urls() -> set[str]:
    urls: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, dict):
            for key in ("content_url", "cover_url"):
                url = value.get(key)
                if isinstance(url, str) and url.startswith("/api/v1/"):
                    urls.add(url)
            job_id, artifact_id = value.get("job_id"), value.get("artifact_id")
            if isinstance(job_id, str) and isinstance(artifact_id, str):
                urls.add(f"{API}/jobs/{job_id}/artifacts/{artifact_id}/content")
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for path in HERE.glob("*.json"):
        if not path.stem.startswith("example_"):
            walk(json.loads(path.read_text(encoding="utf-8")))
    return urls


def capture_files(client) -> int:
    """Download every referenced image once, from the same run, and index it by URL."""
    index = {}
    for url in sorted(referenced_urls()):
        response = client.get(url)
        assert response.status_code == 200, (url, response.status_code)
        mime = response.headers["content-type"].split(";")[0]
        relative = url.removeprefix(f"{API}/").removesuffix("/content") + "." + EXTENSIONS[mime]
        target = FILES / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        index[url] = {
            "file": relative,
            "mime_type": mime,
            "size_bytes": len(response.content),
            "sha256": hashlib.sha256(response.content).hexdigest(),
        }
    (FILES / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    return len(index)


def main() -> None:
    for old in HERE.glob("*.json"):
        old.unlink()
    shutil.rmtree(FILES, ignore_errors=True)
    for name, payload in examples().items():
        write(name, payload)

    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        mock = MockKaggleClient(queue_seconds=0.05, run_seconds=0.0, remote_root=Path(tmp) / "remote")
        settings = make_settings(data)
        client = TestClient(create_app(settings, client=mock, registry=default_registry()))
        client.__enter__()
        harness = Harness(client=client, compute=mock, data_dir=data, settings=settings)
        driver = Driver(harness)
        try:
            cid = driver.create("Ice Lotus Mage", ("xianxia", "mage"))
            upload = harness.upload(image_bytes(96, 64))
            image_ref = client.post(
                f"{API}/characters/{cid}/references",
                json={
                    "contract_version": V,
                    "client_request_id": rid(),
                    "kind": "image",
                    "purpose": "moodboard",
                    "title": "Lotus pond palette",
                    "upload_id": upload["upload_id"],
                    "source_note": "Own photo",
                },
            ).json()
            url_ref = client.post(
                f"{API}/characters/{cid}/references",
                json={
                    "contract_version": V,
                    "client_request_id": rid(),
                    "kind": "url",
                    "purpose": "moodboard",
                    "title": "Ice mage board",
                    "url": "https://www.pinterest.com/example/ice-mage/",
                    "source_note": None,
                },
            ).json()
            write("reference_image", image_ref)
            write("reference_url", url_ref)
            content_s1 = {
                **s1(),
                "palette": ["#C8E6F5", "#3A5C8C"],
                "references": [
                    {
                        "reference_id": image_ref["reference_id"],
                        "aspects": ["color"],
                        "likes": "The cold blues",
                        "do_not_copy": None,
                    }
                ],
            }
            driver.approve(cid, "s1", content_s1)
            driver.approve(cid, "s2", s2())
            driver.save(cid, "s3", s3_profile())
            preview = driver.settle(cid, driver.preview(cid))
            driver.approve(cid, "s3", s3_selected(preview["manifest_id"], preview["results"][0]["task_id"]))
            manifest = driver.batch(
                cid, driver.approve(cid, "s4", s4())["approved_revision"]["batch_manifest_id"]
            )
            write("batch_manifest_ready", manifest)

            mock.run_seconds = 1.5
            os.environ["AAS_MOCK_FAIL_TASKS"] = "side_01"  # read by the mock entry when its process starts
            submitted = driver.submit(cid, manifest["manifest_id"])
            write("batch_manifest_submitted", driver.batch(cid, manifest["manifest_id"]))
            partial = driver.settle(cid, submitted)
            del os.environ["AAS_MOCK_FAIL_TASKS"]
            mock.run_seconds = 0.0
            assert partial["status"] == "partially_completed", partial["status"]
            write("batch_manifest_partially_completed", partial)
            write("job_batch_partial", client.get(f"{API}/jobs/{partial['attempts'][0]['job_id']}").json())
            completed = driver.settle(cid, driver.submit(cid, manifest["manifest_id"], action="retry"))
            write("batch_manifest_completed", completed)

            driver.save(cid, "s5", s5_items(completed))
            failed_approval = client.post(
                f"{API}/characters/{cid}/stages/s4/decisions",
                json={"contract_version": V, "action": "approve", "expected_draft_version": 1, "revision": 1},
            )
            write("error_transition_invalid", failed_approval.json())
            driver.decide(cid, "s5", "submit")
            driver.decide(cid, "s5", "approve", note="Front, side and back show the same character.")

            other = driver.create("Ember Knight", ("knight",))
            driver.approve(other, "s1", s1())
            driver.approve(other, "s2", s2())
            driver.save(other, "s3", s3_profile())
            os.environ["AAS_MOCK_FAIL_TASKS"] = "preview_01,preview_02"
            failed = driver.settle(other, driver.preview(other))
            del os.environ["AAS_MOCK_FAIL_TASKS"]
            assert failed["status"] == "failed", failed["status"]
            write("batch_manifest_failed", failed)
            driver.save(other, "s4", {"stage_id": "s4"})
            bad = client.post(
                f"{API}/characters/{other}/stages/s4/decisions",
                json={"contract_version": V, "action": "submit", "expected_draft_version": 1},
            )
            assert bad.status_code == 200
            approval = client.post(
                f"{API}/characters/{other}/stages/s4/decisions",
                json={"contract_version": V, "action": "approve", "expected_draft_version": 1, "revision": 1},
            )
            assert approval.status_code == 422
            write("error_approval_blocked", approval.json())

            write("character", client.get(f"{API}/characters/{cid}").json()["character"])
            write("character_workflow", client.get(f"{API}/characters/{cid}").json())
            write("character_workflow_in_progress", client.get(f"{API}/characters/{other}").json())
            write("character_list", client.get(f"{API}/characters").json())
            for stage in ("s1", "s2", "s3", "s4", "s5", "s6", "s7"):
                write(f"stage_detail_{stage}", client.get(f"{API}/characters/{cid}/stages/{stage}").json())
            write("stage_detail_s4_in_review", client.get(f"{API}/characters/{other}/stages/s4").json())
            write("stage_revision_s5", client.get(f"{API}/characters/{cid}/stages/s5/revisions/1").json())
            write("history_page", client.get(f"{API}/characters/{cid}/history?limit=20").json())
            write("outputs", client.get(f"{API}/characters/{cid}/outputs").json())
            attempt_jobs = []
            for path in sorted(HERE.glob("*.json")):
                if path.stem.startswith("batch_manifest_") or path.stem.startswith("stage_detail_"):
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    for manifest in [payload] if "attempts" in payload else payload.get("batches", []):
                        attempt_jobs += [a["job_id"] for a in manifest["attempts"]]
            write("batch_jobs", [client.get(f"{API}/jobs/{j}").json() for j in dict.fromkeys(attempt_jobs)])
            captured = capture_files(client)
            time.sleep(0.1)
        finally:
            harness.close()
            mock.close()
    text = "".join(p.read_text(encoding="utf-8") for p in HERE.glob("*.json"))
    assert tmp not in text and str(ROOT) not in text, "a local path leaked into a fixture"
    print(
        f"wrote {len(list(HERE.glob('*.json')))} fixtures and {captured} files to {HERE.relative_to(ROOT).as_posix()}"
    )


if __name__ == "__main__":
    main()
