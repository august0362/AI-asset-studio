"""Deterministic resource planner (docs/CONTRACTS.md §7.2, D-011). Pure: no I/O, no other profiles."""

from __future__ import annotations

import math

from .contracts import (
    CONTRACT_VERSION,
    AcceleratorSpec,
    CandidateFit,
    ComputeProfile,
    ErrorItem,
    EstimateBasis,
    KaggleResourceSnapshot,
    ResourcePlan,
    ResourceRequirements,
    issue,
)

SAFETY_FACTOR = 1.5
OVERHEAD_SECONDS = 600
ACCELERATOR_FIELD = "compute.accelerator_id"


def required_seconds(
    estimated_runtime_seconds: int | None, safety_factor: float, overhead_seconds: int
) -> int | None:
    if estimated_runtime_seconds is None:
        return None
    return math.ceil(estimated_runtime_seconds * safety_factor + overhead_seconds)


def _remaining_quota_seconds(kind: str, snapshot: KaggleResourceSnapshot) -> tuple[int | None, bool]:
    """(remaining seconds or None, fresh?) for the quota that applies to ``kind``."""
    hours = snapshot.gpu_quota_remaining_hours if kind == "gpu_cuda" else snapshot.tpu_quota_remaining_hours
    seconds = None if hours is None else math.floor(hours * 3600)
    return seconds, snapshot.freshness_status.quota == "fresh"


def _evaluate(
    c: AcceleratorSpec,
    req: ResourceRequirements,
    required: int | None,
    snapshot: KaggleResourceSnapshot,
    vram_requirement_unknown: bool,
) -> CandidateFit:
    reasons: list[ErrorItem] = []
    if c.kind == "gpu_cuda":
        available = c.vram_bytes_per_device
        if req.minimum_gpu_vram_bytes is not None and available is not None:
            if req.minimum_gpu_vram_bytes > available:
                reasons.append(
                    issue(
                        "COMPUTE_VRAM_INSUFFICIENT",
                        "error",
                        ACCELERATOR_FIELD,
                        f"{c.accelerator_id} has {available} bytes of VRAM per device; the model needs "
                        f"{req.minimum_gpu_vram_bytes}.",
                        {
                            "accelerator_id": c.accelerator_id,
                            "required_vram_bytes": req.minimum_gpu_vram_bytes,
                            "available_vram_bytes": available,
                        },
                    )
                )
        elif available is None or vram_requirement_unknown:
            # A null requirement that is not declared unknown means "not applicable": nothing to check.
            reasons.append(
                issue(
                    "COMPUTE_VRAM_UNKNOWN",
                    "warning",
                    ACCELERATOR_FIELD,
                    f"GPU memory fit on {c.accelerator_id} cannot be checked: the requirement or capacity is unknown.",
                    {
                        "accelerator_id": c.accelerator_id,
                        "required_vram_bytes": req.minimum_gpu_vram_bytes,
                        "available_vram_bytes": available,
                    },
                )
            )
    if required is None:
        reasons.append(
            issue(
                "MODEL_RUNTIME_UNKNOWN",
                "warning",
                "model_id",
                "The model's runtime is unknown, so session and quota fit cannot be estimated.",
            )
        )
    elif required > c.max_session_seconds:
        reasons.append(
            issue(
                "COMPUTE_SESSION_LIMIT_EXCEEDED",
                "error",
                ACCELERATOR_FIELD,
                f"The job needs an estimated {required} s, more than the {c.max_session_seconds} s session limit "
                f"of {c.accelerator_id}.",
                {
                    "accelerator_id": c.accelerator_id,
                    "required_seconds": required,
                    "session_limit_seconds": c.max_session_seconds,
                },
            )
        )
    if c.kind != "cpu":
        remaining, fresh = _remaining_quota_seconds(c.kind, snapshot)
        if remaining is None or not fresh:
            reasons.append(
                issue(
                    "COMPUTE_QUOTA_UNKNOWN",
                    "warning",
                    "compute.profile_id",
                    "Remaining Kaggle quota is unknown or not fresh; the plan cannot confirm it is enough.",
                    {"accelerator_id": c.accelerator_id, "quota_freshness": snapshot.freshness_status.quota},
                )
            )
        elif required is not None and required > remaining:
            reasons.append(
                issue(
                    "COMPUTE_QUOTA_INSUFFICIENT",
                    "error",
                    ACCELERATOR_FIELD,
                    f"The job needs an estimated {required} s but only {remaining} s of quota remain.",
                    {
                        "accelerator_id": c.accelerator_id,
                        "required_seconds": required,
                        "quota_remaining_seconds": remaining,
                    },
                    retryable=True,
                )
            )
    if any(r.severity == "error" for r in reasons):
        fit = "insufficient"
    elif reasons:
        fit = "unknown"
    else:
        fit = "ok"
    return CandidateFit(accelerator_id=c.accelerator_id, fit=fit, reasons=reasons)


def plan(
    req: ResourceRequirements,
    profile: ComputeProfile,
    snapshot: KaggleResourceSnapshot,
    accelerator_id: str | None,
    *,
    vram_requirement_unknown: bool | None = None,
    safety_factor: float = SAFETY_FACTOR,
    overhead_seconds: int = OVERHEAD_SECONDS,
) -> ResourcePlan:
    """Plan for the explicitly selected profile only.

    ``vram_requirement_unknown`` says whether a null ``minimum_gpu_vram_bytes`` is *unknown* (the model lists it in
    ``unknown_requirements``) or *not applicable*. ``None`` treats a null requirement as unknown.
    """
    if vram_requirement_unknown is None:
        vram_requirement_unknown = req.minimum_gpu_vram_bytes is None
    required = required_seconds(req.estimated_runtime_seconds, safety_factor, overhead_seconds)
    basis = EstimateBasis(
        estimated_runtime_seconds=req.estimated_runtime_seconds,
        safety_factor=safety_factor,
        overhead_seconds=overhead_seconds,
    )
    candidates = [a for kind in req.accelerator_kinds for a in profile.accelerators if a.kind == kind]
    if req.multi_gpu == "required":
        candidates = [a for a in candidates if a.device_count >= 2]
    selection = "user_selected" if accelerator_id is not None else "recommended"

    def blocked(message: str, details: dict) -> ResourcePlan:
        return ResourcePlan(
            contract_version=CONTRACT_VERSION,
            profile_id=profile.profile_id,
            accelerator_id=accelerator_id,
            selection=selection,
            fit="insufficient",
            required_seconds=required,
            estimate_basis=basis,
            session_limit_seconds=None,
            quota_remaining_seconds=None,
            candidates=[],
            warnings=[],
            errors=[issue("MODEL_ACCELERATOR_INCOMPATIBLE", "error", ACCELERATOR_FIELD, message, details)],
        )

    supported = [a.accelerator_id for a in candidates]
    if not candidates:
        return blocked(
            "No accelerator in this profile is compatible with the model.",
            {"accelerator_kinds": req.accelerator_kinds, "multi_gpu": req.multi_gpu},
        )
    if accelerator_id is not None and accelerator_id not in supported:
        return blocked(
            f"The model cannot run on '{accelerator_id}'. Compatible accelerators: {', '.join(supported)}.",
            {"accelerator_id": accelerator_id, "compatible_accelerators": supported},
        )

    by_id = {c.accelerator_id: c for c in candidates}
    if accelerator_id is not None:  # only the user's choice is evaluated (as in the §7.3 example)
        fits = [_evaluate(by_id[accelerator_id], req, required, snapshot, vram_requirement_unknown)]
        chosen = fits[0]
    else:
        fits = [_evaluate(c, req, required, snapshot, vram_requirement_unknown) for c in candidates]
        chosen = next((f for f in fits if f.fit == "ok"), None) or next(
            (f for f in fits if f.fit == "unknown"), None
        )

    if chosen is None:  # recommended, every candidate insufficient: the first candidate's reasons block
        first = fits[0]
        return ResourcePlan(
            contract_version=CONTRACT_VERSION,
            profile_id=profile.profile_id,
            accelerator_id=None,
            selection=selection,
            fit="insufficient",
            required_seconds=required,
            estimate_basis=basis,
            session_limit_seconds=None,
            quota_remaining_seconds=None,
            candidates=fits,
            warnings=[r for r in first.reasons if r.severity == "warning"],
            errors=[r for r in first.reasons if r.severity == "error"],
        )

    spec = by_id[chosen.accelerator_id]
    remaining = None if spec.kind == "cpu" else _remaining_quota_seconds(spec.kind, snapshot)[0]
    return ResourcePlan(
        contract_version=CONTRACT_VERSION,
        profile_id=profile.profile_id,
        accelerator_id=chosen.accelerator_id,
        selection=selection,
        fit=chosen.fit,
        required_seconds=required,
        estimate_basis=basis,
        session_limit_seconds=spec.max_session_seconds,
        quota_remaining_seconds=remaining,
        candidates=fits,
        warnings=[r for r in chosen.reasons if r.severity == "warning"],
        errors=[r for r in chosen.reasons if r.severity == "error"],
    )


def run_timeout_seconds(plan_: ResourcePlan) -> int | None:
    """``kernels push --timeout`` = min(required ?? max_session, max_session) (§7.2)."""
    if plan_.session_limit_seconds is None:
        return None
    if plan_.required_seconds is None:
        return plan_.session_limit_seconds
    return min(plan_.required_seconds, plan_.session_limit_seconds)
