"""Accelerator catalog (docs/CONTRACTS.md §6.1). **Provisional** until the M3 spike verifies it (DF-06, A-04).

The Kaggle ``--accelerator`` value per entry is added (and kept internal) in M3.
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
