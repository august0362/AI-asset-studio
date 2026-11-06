"""Mock Image→3D adapter: a textured box GLB whose faces show the supplied views (D-016)."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from ...contracts import VIEW_ROLES, ExpectedOutput, GenerationRequest
from ..base import ModelAdapter

DEFAULT_TEXTURE_RESOLUTION = 1024


class MockImageTo3DAdapter(ModelAdapter):
    entrypoint = "models/adapters/mock_image_to_3d/remote_entry.py"

    def expected_outputs(self, request: GenerationRequest) -> list[ExpectedOutput]:
        return [
            ExpectedOutput(name="model.glb", kind="model_3d", format="glb", required=True),
            ExpectedOutput(name="preview.png", kind="preview", format="png", required=False),
        ]

    def build_arguments(self, request: GenerationRequest) -> dict[str, Any]:
        views = {i.role: PurePosixPath(i.path).name for i in request.inputs if i.role in VIEW_ROLES}
        details = [PurePosixPath(i.path).name for i in request.inputs if i.role == "detail"]
        return {
            "views": views,
            "details": details,
            "asset_category": request.asset_category,
            "model_id": request.model_id,
            "texture_resolution": request.options.get("texture_resolution", DEFAULT_TEXTURE_RESOLUTION),
            "seed": request.options.get("seed"),
        }
