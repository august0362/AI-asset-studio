"""Helpers for the Character Production tests (CONTRACTS §13): drive a character through the stages over HTTP."""

from __future__ import annotations

import uuid
from typing import Any

from aas_backend.characters import config

API = "/api/v1"
V = "1.1"
COMPUTE = {"profile_id": "default", "accelerator_id": "auto"}
PURPOSES = ["full_body", "front", "side", "back"]


def rid() -> str:
    return str(uuid.uuid4())


def checklist(stage_id: str, *, only_required: bool = True) -> dict[str, Any]:
    items = (
        [i for i in config.required_checklist(stage_id)]
        if only_required
        else sorted(config.checklist_ids(stage_id))
    )
    return {"items": [{"item_id": i, "checked": True, "note": None} for i in items]}


def s1() -> dict[str, Any]:
    return {"stage_id": "s1", "idea": "An adult ice-lotus mage", "directions": ["Elegant, cold, regal"]}


def s2(hair: str = "Long silver-white hair") -> dict[str, Any]:
    return {
        "stage_id": "s2",
        "summary": "An adult female ice-lotus mage.",
        "attributes": [
            {
                "attribute_id": "hair",
                "group": "hair",
                "label": "Hair",
                "value": hair,
                "lock": "locked",
                "reference_ids": [],
            },
            {
                "attribute_id": "eyes",
                "group": "eyes",
                "label": "Eyes",
                "value": "Pale blue",
                "lock": "preferred",
                "reference_ids": [],
            },
        ],
        "answers": [{"question_id": "q_name_role", "status": "answered", "answer": "Ice-lotus mage, ally"}],
        "open_questions": [],
        "rejection_criteria": ["Short hair"],
    }


def s3_profile(model_id: str = "mock-t2d-basic", variations: int = 2) -> dict[str, Any]:
    return {
        "stage_id": "s3",
        "preview_profile": {
            "model_id": model_id,
            "compute_target": "kaggle",
            "variations": variations,
            "width": 512,
            "height": 512,
            "options": {},
        },
        "preview_prompt": "1girl, solo, silver-white long hair, pale blue eyes, ice lotus mage, full body",
    }


def s3_selected(manifest_id: str, task_id: str, model_id: str = "mock-t2d-basic") -> dict[str, Any]:
    content = s3_profile(model_id)
    content["candidates"] = [
        {
            "candidate_id": "cand_01",
            "source": "batch_task",
            "manifest_id": manifest_id,
            "task_id": task_id,
            "verdict": "selected",
            "matches": ["hair"],
            "mismatches": [],
            "feedback": None,
        }
    ]
    content["selected_candidate_id"] = "cand_01"
    return content


def s4(model_id: str = "mock-t2d-basic", purposes=PURPOSES, extra_tasks=()) -> dict[str, Any]:
    tasks = [
        {
            "task_id": f"{p.replace('_', '')}_01",
            "purpose": p,
            "prompt": f"1girl, solo, silver-white long hair, {p.replace('_', ' ')} view, plain background",
            "negative_prompt": None,
            "seed": 41000 + i,
            "width": 512,
            "height": 512,
            "options": {},
        }
        for i, p in enumerate(purposes)
    ]
    tasks += list(extra_tasks)
    return {
        "stage_id": "s4",
        "entries": [
            {"purpose": p, "canonical_prompt": f"{p} of the mage", "negative_prompt": None, "notes": None}
            for p in PURPOSES
        ],
        "production_profile": {"target_model_id": model_id, "compute_target": "kaggle", "options": {}},
        "tasks": tasks,
        "reference_asset_ids": [],
    }


def s5_items(manifest: dict[str, Any]) -> dict[str, Any]:
    items = []
    for index, task in enumerate(manifest["tasks"], start=1):
        items.append(
            {
                "item_id": f"item_{index:03d}",
                "purpose": task["purpose"],
                "manifest_id": manifest["manifest_id"],
                "task_id": task["task_id"],
                "selected": True,
                "note": None,
            }
        )
    return {"stage_id": "s5", "items": items, "consistency_notes": "Same character in every view."}


class Driver:
    def __init__(self, harness) -> None:
        self.h = harness
        self.c = harness.client

    def create(self, name: str = "Ice Lotus Mage", tags=("xianxia", "mage")) -> str:
        response = self.c.post(
            f"{API}/characters",
            json={
                "contract_version": V,
                "client_request_id": rid(),
                "name": name,
                "summary": None,
                "tags": list(tags),
            },
        )
        assert response.status_code == 201, response.text
        return response.json()["character_id"]

    def detail(self, cid: str, stage: str) -> dict[str, Any]:
        response = self.c.get(f"{API}/characters/{cid}/stages/{stage}")
        assert response.status_code == 200, response.text
        return response.json()

    def save(self, cid: str, stage: str, content: dict, check: dict | None = None, *, expect: int = 200):
        version = self.detail(cid, stage)["draft"]["draft_version"]
        response = self.c.put(
            f"{API}/characters/{cid}/stages/{stage}/draft",
            json={
                "contract_version": V,
                "expected_draft_version": version,
                "content": content,
                "checklist": check if check is not None else checklist(stage),
            },
        )
        assert response.status_code == expect, response.text
        return response.json()

    def decide(
        self, cid: str, stage: str, action: str, revision: int | None = None, *, expect: int = 200, note=None
    ):
        detail = self.detail(cid, stage)
        if revision is None and action in ("approve", "withdraw"):
            revision = detail["state"]["pending_revision"]
        response = self.c.post(
            f"{API}/characters/{cid}/stages/{stage}/decisions",
            json={
                "contract_version": V,
                "action": action,
                "expected_draft_version": detail["draft"]["draft_version"],
                "revision": revision,
                "note": note,
            },
        )
        assert response.status_code == expect, response.text
        return response.json()

    def approve(self, cid: str, stage: str, content: dict, check: dict | None = None) -> dict[str, Any]:
        self.save(cid, stage, content, check)
        self.decide(cid, stage, "submit")
        return self.decide(cid, stage, "approve")

    def preview(self, cid: str, *, expect: int = 201, request_id: str | None = None) -> dict[str, Any]:
        response = self.c.post(
            f"{API}/characters/{cid}/batches",
            json={
                "contract_version": V,
                "client_request_id": request_id or rid(),
                "kind": "preview",
                "compute": COMPUTE,
            },
        )
        assert response.status_code == expect, response.text
        return response.json()

    def batch(self, cid: str, mid: str) -> dict[str, Any]:
        response = self.c.get(f"{API}/characters/{cid}/batches/{mid}")
        assert response.status_code == 200, response.text
        return response.json()

    def submit(
        self, cid: str, mid: str, *, expect: int = 200, request_id: str | None = None, action="submit"
    ):
        response = self.c.post(
            f"{API}/characters/{cid}/batches/{mid}/{action}",
            json={"contract_version": V, "client_request_id": request_id or rid(), "compute": COMPUTE},
        )
        assert response.status_code == expect, response.text
        return response.json()

    def settle(self, cid: str, manifest: dict[str, Any]) -> dict[str, Any]:
        """Wait for every attempt job, then read the reconciled manifest."""
        for attempt in manifest["attempts"]:
            self.h.wait(attempt["job_id"])
        return self.batch(cid, manifest["manifest_id"])

    def through_s4(self, cid: str, *, model_id: str = "mock-t2d-basic", s4_content=None) -> dict[str, Any]:
        """S1-S3 approved (S3 from a preview batch), S4 approved; returns the frozen production manifest."""
        self.approve(cid, "s1", s1())
        self.approve(cid, "s2", s2())
        self.save(cid, "s3", s3_profile())
        preview = self.settle(cid, self.preview(cid))
        task_id = next(r["task_id"] for r in preview["results"] if r["status"] == "succeeded")
        self.approve(cid, "s3", s3_selected(preview["manifest_id"], task_id))
        detail = self.approve(cid, "s4", s4_content or s4(model_id))
        manifest_id = detail["approved_revision"]["batch_manifest_id"]
        return self.batch(cid, manifest_id)
