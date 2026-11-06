"""The seven fixed stages (docs/v2/CHARACTER_WORKFLOW.md §1, §3, §5). Defined once here and served to the frontend.

Labels are i18n keys; the frontend owns their text. Availability is evaluated on read.
"""

from __future__ import annotations

from models.registry import ModelRegistry

from .contracts import ChecklistItemConfig, GuidedQuestion, StageConfig, StageDependency

REQUIRED_PURPOSES = ["full_body", "front", "side", "back"]  # OD-03

_DEPENDENCIES: dict[str, list[tuple[str, str]]] = {
    "s1": [],
    "s2": [("s1", "hard")],
    "s3": [("s2", "hard"), ("s1", "soft")],
    "s4": [("s2", "hard"), ("s3", "hard")],
    "s5": [("s4", "hard"), ("s2", "soft")],
    "s6": [("s5", "hard"), ("s2", "soft")],
    "s7": [("s6", "hard")],
}

# (item_id, required)
_CHECKLISTS: dict[str, list[tuple[str, bool]]] = {
    "s1": [
        ("references_tagged", True),
        ("direction_chosen", True),
        ("enough_for_spec", True),
        ("unchangeable_noted", False),
        ("sketch_attached", False),
    ],
    "s2": [
        ("locked_clear", True),
        ("unknowns_marked", True),
        ("reference_map_done", True),
        ("no_conflicts", True),
        ("rejection_criteria", False),
        ("3d_constraints", False),
    ],
    "s3": [
        ("face_hair_ok", True),
        ("silhouette_ok", True),
        ("locked_match", True),
        ("art_direction_ok", True),
        ("rejects_noted", False),
    ],
    "s4": [
        ("locked_covered", True),
        ("no_invention", True),
        ("model_support_checked", True),
        ("turnaround_neutral", True),
        ("manifest_reviewed", True),
        ("params_separated", False),
    ],
    "s5": [
        ("identity_each", True),
        ("anatomy_ok", True),
        ("no_crop_or_occlusion", True),
        ("multiview_same_character", True),
        ("proportions_stable", True),
        ("front_back_readable", True),
        ("set_reviewed_as_whole", True),
    ],
    "s6": [
        ("silhouette_360", True),
        ("texture_ok", True),
        ("mesh_clean", True),
        ("rig_ready", True),
        ("export_valid", True),
    ],
    "s7": [
        ("skeleton_ok", True),
        ("skinning_ok", True),
        ("extreme_poses_ok", True),
        ("animation_test", True),
        ("engine_import_ok", True),
    ],
}

CORE_QUESTIONS = [
    "q_name_role",
    "q_identity_marks",
    "q_appearance",
    "q_outfit_layers",
    "q_props",
    "q_style",
    "q_reference_map",
    "q_view_details",
    "q_variable_vs_fixed",
]
EXTRA_QUESTIONS = ["q_variants", "q_motion_parts", "q_3d_limits", "q_scale", "q_not_this_character"]
QUESTION_IDS = frozenset(CORE_QUESTIONS + EXTRA_QUESTIONS)


def dependencies(stage_id: str) -> list[tuple[str, str]]:
    return _DEPENDENCIES[stage_id]


def downstream(stage_id: str) -> list[str]:
    return [s for s, deps in _DEPENDENCIES.items() if any(u == stage_id for u, _ in deps)]


def checklist_ids(stage_id: str) -> set[str]:
    return {item_id for item_id, _ in _CHECKLISTS[stage_id]}


def required_checklist(stage_id: str) -> list[str]:
    return [item_id for item_id, required in _CHECKLISTS[stage_id] if required]


def has_character_text_to_2d(registry: ModelRegistry) -> bool:
    return any(m.accepts_jobs for m in registry.list("text_to_2d", "character"))


def availability(stage_id: str, registry: ModelRegistry) -> tuple[str, str | None]:
    """(availability, reason), CHARACTER_WORKFLOW §5."""
    if stage_id == "s5" and not has_character_text_to_2d(registry):
        return "unavailable", "no_text_to_2d_model"
    if stage_id == "s6":
        return "planned", "planned_m5"
    if stage_id == "s7":
        return "planned", "out_of_scope"
    return "available", None


def stage_config(stage_id: str, registry: ModelRegistry) -> StageConfig:
    state, reason = availability(stage_id, registry)
    questions = []
    if stage_id == "s2":
        questions = [
            GuidedQuestion(question_id=q, label_key=f"stage.s2.question.{q}", core=q in CORE_QUESTIONS)
            for q in CORE_QUESTIONS + EXTRA_QUESTIONS
        ]
    return StageConfig(
        stage_id=stage_id,
        order=int(stage_id[1]),
        title_key=f"stage.{stage_id}.title",
        objective_key=f"stage.{stage_id}.objective",
        availability=state,
        availability_reason=reason,
        dependencies=[StageDependency(stage_id=u, kind=k) for u, k in _DEPENDENCIES[stage_id]],
        checklist=[
            ChecklistItemConfig(item_id=i, label_key=f"stage.{stage_id}.check.{i}", required=r)
            for i, r in _CHECKLISTS[stage_id]
        ],
        required_purposes=list(REQUIRED_PURPOSES) if stage_id in ("s4", "s5") else [],
        guided_questions=questions,
    )
