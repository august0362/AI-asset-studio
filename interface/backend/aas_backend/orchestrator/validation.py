"""Authoritative validation: stages 1-6 from Models plus stage 7 (compute) from the Kaggle planner (§8.1).

Stage 7 reads only the cached snapshot; nothing here contacts a remote service.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kaggle_connector.client import ComputeClient
from kaggle_connector.resources import ResourcePlan, ResourceRequirements
from kaggle_connector.resources import plan as plan_resources
from models.adapters import requirements_from
from models.contracts import CONTRACT_VERSION, CreateJobRequest, ErrorItem, ModelCapabilities, error
from models.registry import ModelRegistry, ModelValidation, parse_create_job_request, validate_model_request
from models.registry.validation import UploadLookup

from ..schemas import ValidationReport


def to_model_error(item) -> ErrorItem:
    """Convert a kaggle_connector ErrorItem (same shape) to the Models ErrorItem."""
    return ErrorItem.model_validate(item.model_dump())


@dataclass
class ValidationOutcome:
    report: ValidationReport
    request: CreateJobRequest | None = None
    model: ModelValidation | None = None
    plan: ResourcePlan | None = None
    errors: list[ErrorItem] = field(default_factory=list)

    @property
    def capabilities(self) -> ModelCapabilities | None:
        return self.model.capabilities if self.model else None


def _stage_compute(
    req: CreateJobRequest, caps: ModelCapabilities, client: ComputeClient
) -> tuple[list[ErrorItem], list[ErrorItem], ResourcePlan | None]:
    profiles = {p.profile_id: p for p in client.profiles() if p.enabled}
    profile = profiles.get(req.compute.profile_id)
    if profile is None:
        return (
            [
                error(
                    "COMPUTE_PROFILE_NOT_FOUND",
                    "compute.profile_id",
                    f"Compute profile '{req.compute.profile_id}' does not exist or is not enabled.",
                    {"profile_id": req.compute.profile_id, "available_profiles": sorted(profiles)},
                )
            ],
            [],
            None,
        )
    snapshot = client.snapshot(profile.profile_id)
    if snapshot.authentication_status != "authenticated":
        return (
            [
                error(
                    "COMPUTE_PROFILE_UNAUTHENTICATED",
                    "compute.profile_id",
                    "This compute profile is not authenticated.",
                    {"authentication_status": snapshot.authentication_status},
                    retryable=True,
                )
            ],
            [],
            None,
        )
    requirements = ResourceRequirements.model_validate(requirements_from(caps).model_dump())
    resource_plan = plan_resources(requirements, profile, snapshot, req.compute.accelerator_id)
    return (
        [to_model_error(e) for e in resource_plan.errors],
        [to_model_error(w) for w in resource_plan.warnings],
        resource_plan,
    )


def validate_request(
    raw: object, *, registry: ModelRegistry, client: ComputeClient, lookup: UploadLookup
) -> ValidationOutcome:
    def report(errors, warnings, plan=None) -> ValidationReport:
        return ValidationReport(
            contract_version=CONTRACT_VERSION,
            valid=not errors,
            errors=errors,
            warnings=warnings,
            resource_plan=plan,
        )

    req, schema_errors = parse_create_job_request(raw)
    if req is None:
        return ValidationOutcome(report(schema_errors, []), errors=schema_errors)

    model = validate_model_request(req, registry, lookup)
    errors, warnings = list(model.errors), list(model.warnings)
    resource_plan = None
    if model.capabilities is not None:
        compute_errors, compute_warnings, resource_plan = _stage_compute(req, model.capabilities, client)
        errors += compute_errors
        warnings += compute_warnings
    shown_plan = resource_plan if not model.errors and model.capabilities is not None else None
    return ValidationOutcome(
        report(errors, warnings, shown_plan), request=req, model=model, plan=resource_plan, errors=errors
    )
