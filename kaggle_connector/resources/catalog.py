"""Accelerator catalogs (docs/CONTRACTS.md §6.1, DECISIONS DF-06).

``PROVISIONAL_ACCELERATORS`` is the mock profile's catalog (M1/M2 fixtures). ``KAGGLE_ACCELERATORS`` is the catalog of a
real Kaggle profile: only entries whose ``--accelerator`` value the M3 spike verified. The Kaggle value
(``KAGGLE_MACHINE_SHAPES``) is internal to this module and never appears in a contract.
"""

from __future__ import annotations

from .contracts import AcceleratorSpec

GIB = 1024**3

PROVISIONAL_ACCELERATORS: list[AcceleratorSpec] = [
    AcceleratorSpec(
        accelerator_id="cpu",
        kind="cpu",
        device_count=0,
        vram_bytes_per_device=None,
        max_session_seconds=43200,
    ),
    AcceleratorSpec(
        accelerator_id="gpu_p100",
        kind="gpu_cuda",
        device_count=1,
        vram_bytes_per_device=16 * GIB,
        max_session_seconds=43200,
    ),
    AcceleratorSpec(
        accelerator_id="gpu_t4x2",
        kind="gpu_cuda",
        device_count=2,
        vram_bytes_per_device=15 * GIB,
        max_session_seconds=43200,
    ),
    AcceleratorSpec(
        accelerator_id="tpu_vm",
        kind="tpu",
        device_count=1,
        vram_bytes_per_device=None,
        max_session_seconds=32400,
    ),
]

# ``kaggle kernels push --accelerator`` value (sets ``machine_shape``); ``None`` = no accelerator flag (CPU).
# Verified on 2026-11-06 with CLI 2.2.4: CPU and NvidiaTeslaT4 (2 × Tesla T4, 16106127360 B each, read via NVML).
# P100 has no documented value and TPU is unverified, so neither is offered on a real profile yet (DF-06).
KAGGLE_MACHINE_SHAPES: dict[str, str | None] = {
    "cpu": None,
    "gpu_t4x2": "NvidiaTeslaT4",
}

# Session limits are still the provisional 12 h (A-04): the spike did not run long enough to observe them.
KAGGLE_ACCELERATORS: list[AcceleratorSpec] = [
    spec for spec in PROVISIONAL_ACCELERATORS if spec.accelerator_id in KAGGLE_MACHINE_SHAPES
]
