"""Capability registry."""

from __future__ import annotations

from collections.abc import Iterable

from ..adapters import ADAPTERS, ModelAdapter
from ..contracts import ModelCapabilities
from .mocks import MOCK_CAPABILITIES
from .real import REAL_CAPABILITIES


class ModelRegistry:
    def __init__(
        self, capabilities: Iterable[ModelCapabilities], adapters: dict[str, type[ModelAdapter]] | None = None
    ) -> None:
        self._models: dict[str, ModelCapabilities] = {}
        for record in capabilities:
            if record.model_id in self._models:
                raise ValueError(f"duplicate model_id {record.model_id}")
            self._models[record.model_id] = record
        self._adapter_types = dict(ADAPTERS if adapters is None else adapters)
        for record in self._models.values():
            if record.accepts_jobs and record.adapter not in self._adapter_types:
                raise ValueError(
                    f"model {record.model_id} accepts jobs but adapter {record.adapter} is missing"
                )

    def get(self, model_id: str) -> ModelCapabilities | None:
        return self._models.get(model_id)

    def list(
        self, pipeline_type: str | None = None, asset_category: str | None = None
    ) -> list[ModelCapabilities]:
        return [
            m
            for m in self._models.values()
            if (pipeline_type is None or pipeline_type in m.supported_pipeline_types)
            and (asset_category is None or asset_category in m.supported_asset_categories)
        ]

    def adapter(self, model_id: str) -> ModelAdapter:
        record = self._models[model_id]
        return self._adapter_types[record.adapter](record)


def default_registry() -> ModelRegistry:
    """The five mocks: mock compute mode and the contract tests."""
    return ModelRegistry(MOCK_CAPABILITIES)


def full_registry() -> ModelRegistry:
    """Mocks plus the real models (D-034). Used in Kaggle mode only: real models need a Kaggle GPU and the
    internet, so mock mode, which runs entrypoints on this machine, never offers them."""
    return ModelRegistry([*MOCK_CAPABILITIES, *REAL_CAPABILITIES])


def registry_for(compute_mode: str) -> ModelRegistry:
    return full_registry() if compute_mode == "kaggle" else default_registry()
