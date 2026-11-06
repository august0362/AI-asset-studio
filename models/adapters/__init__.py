"""Model adapters. M2 ships mocks only; real adapters arrive in M4+ (no model is selected before then)."""

from .base import ArtifactInvalidError, ModelAdapter, requirements_from
from .mock_image_to_3d import MockImageTo3DAdapter
from .mock_text_to_2d import MockTextTo2DAdapter

ADAPTERS: dict[str, type[ModelAdapter]] = {
    "mock_text_to_2d": MockTextTo2DAdapter,
    "mock_image_to_3d": MockImageTo3DAdapter,
}

__all__ = [
    "ADAPTERS",
    "ArtifactInvalidError",
    "MockImageTo3DAdapter",
    "MockTextTo2DAdapter",
    "ModelAdapter",
    "requirements_from",
]
