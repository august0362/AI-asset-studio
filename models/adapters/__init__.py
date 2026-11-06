"""Model adapters: the M2 mocks and, from M4, the real models chosen by the owner (D-034)."""

from .base import ArtifactInvalidError, ModelAdapter, requirements_from
from .diffusers_text_to_2d import DiffusersTextTo2DAdapter
from .mock_image_to_3d import MockImageTo3DAdapter
from .mock_text_to_2d import MockTextTo2DAdapter

ADAPTERS: dict[str, type[ModelAdapter]] = {
    "mock_text_to_2d": MockTextTo2DAdapter,
    "mock_image_to_3d": MockImageTo3DAdapter,
    "diffusers_text_to_2d": DiffusersTextTo2DAdapter,
}

__all__ = [
    "ADAPTERS",
    "ArtifactInvalidError",
    "DiffusersTextTo2DAdapter",
    "MockImageTo3DAdapter",
    "MockTextTo2DAdapter",
    "ModelAdapter",
    "requirements_from",
]
