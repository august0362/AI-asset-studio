"""Mock Text→2D adapter: a Pillow-rendered PNG that is clearly labeled as mock output (D-016).

It also runs batch jobs (§13.9): one "load", then one PNG per task.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from ...contracts import ExpectedOutput, GenerationRequest
from ..base import ModelAdapter, deadline_seconds, task_output_name

DEFAULT_SIZE = 1024


class MockTextTo2DAdapter(ModelAdapter):
    entrypoint = "models/adapters/mock_text_to_2d/remote_entry.py"
    supports_batch = True

    def expected_outputs(self, request: GenerationRequest) -> list[ExpectedOutput]:
        return [ExpectedOutput(name="image.png", kind="image", format="png", required=True)]

    def build_arguments(self, request: GenerationRequest) -> dict[str, Any]:
        options = request.options
        style = next((i for i in request.inputs if i.role == "style_reference"), None)
        return {
            "prompt": request.prompt,
            "asset_category": request.asset_category,
            "model_id": request.model_id,
            "width": options.get("width", DEFAULT_SIZE),
            "height": options.get("height", DEFAULT_SIZE),
            "seed": options.get("seed"),
            "negative_prompt": options.get("negative_prompt"),
            "style_reference": PurePosixPath(style.path).name if style else None,
        }

    def build_batch_arguments(self, request: GenerationRequest) -> dict[str, Any]:
        return {
            "asset_category": request.asset_category,
            "model_id": request.model_id,
            "deadline_seconds": deadline_seconds(request),
            "tasks": [
                {
                    "task_id": task.task_id,
                    "output": task_output_name(task.task_id),
                    "prompt": task.prompt,
                    "width": task.options.get("width", DEFAULT_SIZE),
                    "height": task.options.get("height", DEFAULT_SIZE),
                    "seed": task.options.get("seed"),
                    "negative_prompt": task.options.get("negative_prompt"),
                }
                for task in request.tasks or []
            ],
        }
