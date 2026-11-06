# Milestones

The order is fixed: **M0 → M1 → M2 → M3 → M4 → M5 → M6**. Character Production (**V2-0 … V2-6**, §V2) runs alongside and does not depend on M5/M6. Each milestone starts only after its prerequisites are done.
Related: [CONTRACTS.md](CONTRACTS.md) · [ARCHITECTURE.md](ARCHITECTURE.md) · [DECISIONS.md](DECISIONS.md)

**Definition of done:**
- Every acceptance criterion is demonstrated and every listed test **passes**. Code merely existing is not enough.
- Shared fixtures validate on both the frontend and the backend.
- No secrets appear anywhere.
- DECISIONS and the status table are updated.
- The owner signs off.

| Milestone | Status |
|---|---|
| M0 Architecture & Documentation | **Done** (owner approved 2026-11-06) |
| M1 Mock Frontend | **Done** (2026-11-06, including color themes and Vietnamese, D-023, D-024) |
| M2 Model Contracts & Mock Adapters | **Done** (2026-11-06) |
| M3 Kaggle Integration | **Done** (2026-11-06; profile `SUNNY`, D-025) |
| M4 Text-to-2D Models | **Done** (2026-11-06; Animagine XL 4.0, FLUX.2 [klein] 4B, MOSS-Image-SFT for `character`, D-034, D-036, D-037) |
| V2-0 … V2-2 Character Production: contracts, backend, batches | **Done** (2026-11-06, D-037, D-038) |
| V2-3 … V2-5 Character Production: frontend | In progress (Codex) |
| V2-6 Character Production: integration and sign-off | Not started |
| M5 Image-to-3D Models | Not started |
| M6 Text-to-3D Models | Not started |

---

## Done milestones (summary)

Every task of M0–M4 was checked off and signed off by the owner on 2026-11-06. The full checklists are in the git history.

**M0 — Architecture & Documentation.** Spec, architecture, contracts v1.0, milestones, decisions and agent context; exactly three modules; cross-document name check; every link resolves; `git init` (`main`, pushed to `github.com/august0362/AI-asset-studio`; the branch/PR workflow is still open, DF-13).

**M1 — Mock Frontend** (Codex; built in parallel with M2 by owner instruction, D-019).
- The full UI on `MockApiClient`: three pipeline screens, four categories, model-driven forms, multi-image upload with roles, client-side validation (CONTRACTS §8 stages 2–7 and the §7.2 planner), profile/accelerator selection with a ResourcePlan panel, jobs, logs, PNG preview, GLB viewer, downloads and the mock Resources view with its seven scenarios.
- Color themes (D-023, UI.md §1–§4) and Vietnamese/English (D-024, UI.md §5–§9), with WCAG contrast, persistence before first paint and every §8.2 error code localized.
- Verified 2026-11-06: typecheck, ESLint, Vitest (V-01…V-20), `vite build`, Playwright with axe in all four themes and both languages. `mock.{png,glb}` live in `interface/frontend/tests/fixtures/`.

**M2 — Model Contracts & Mock Adapters** (Claude Code).
- `models/contracts` (Pydantic + JSON Schema), the registry with the five §2.2 mocks (values CONTRACTS is silent on are marked `# gap`, A-07), mock Text→2D PNG and Image→3D GLB adapters (D-016), `MockKaggleClient`, and every §5 endpoint with the worker, state machine, reconciliation, storage and sweeps.
- Accepted: Text→2D and Image→3D through the HTTP API and the UI in http mode; V-xx through the API; restart mid-job; `PATH_INVALID` on traversal.
- Owner decisions: D-020 (contract clarifications), D-021 (VRAM not applicable), D-022 (streamed upload limit).

**M3 — Kaggle Integration** (one authorized profile, D-008, D-025).
- Spike results: quota mapping D-026, accelerators D-027/D-031, live telemetry D-028, one dataset per job D-029; client design D-030.
- `KaggleCliClient` with subprocess-env auth, packaging, dataset upload, status mapping, logs, download, quota and telemetry. The mock adapters double as the smoke adapter.
- Accepted on Kaggle and checked in the UI by the owner: a full lifecycle on T4×2, a deliberate `KAGGLE_KERNEL_ERROR` (D-031 test switch), real auth and quota, GPU0/GPU1 telemetry, no secret leaks. Tests: recorded CLI output, secret-leak test, opt-in `pytest -m kaggle`. Run log in DECISIONS.

**M4 — Text-to-2D Models** (`character`).
- Selection benchmark outside the app (D-033): five candidates × the nine cases of the [Prompt Book](sources/M4_Text_to_2D_Prompt_Book_v1.md); gallery `M4_Text2D_Gallery.html` (repository root, not committed). The owner kept three models (D-034).
- Per model (D-036): research note, full `ModelCapabilities` (`models/registry/real.py`), one adapter `models/adapters/diffusers_text_to_2d/`, measured runtimes 25 / 9 / 354 s, unit tests and the V-matrix, and one live smoke run each (MOSS after an out-of-memory fix).

## V2 — Character Production

Scope and acceptance criteria: [PRODUCT_SPEC.md §8](PRODUCT_SPEC.md#8-character-production-v2). Tests: [v2/TEST_PLAN.md](v2/TEST_PLAN.md). Decisions OD-01…OD-14: [DECISIONS.md](DECISIONS.md#v2-open-decisions-od).

| Milestone | Owner of the work | Scope | Completion gate | Status |
|---|---|---|---|---|
| **V2-0 Contract freeze** | Claude Code (docs), owner | Docs; the OD decisions answered | Owner approval | **Done**: D-035; CONTRACTS v1.1 merged as §13 (D-037); fixtures in `tests/fixtures/contracts/v2/` |
| **V2-1 Backend core** | Claude Code | `characters/` package: IDs, store (atomic, exclusive-create revisions, history), StageConfig, routes 1–14 and 19, approval rules, staleness, freezing | TEST_PLAN §2 and §3 pass in mock mode; all v1 tests pass | **Done** (D-038; route 19 *delete character* added) |
| **V2-2 Batch execution** | Claude Code | `GenerationRequest.tasks`, `request.batch`, `Artifact.task_id`, `BATCH_PARTIAL`; batch support in the adapter and remote entry (one load per job, per-task results, deadline); routes 15–18; reconciliation | TEST_PLAN §4 passes with the mock adapter | **Done** (D-038): B-01…B-12 pass; the owner accepted it without the live run B-13, which stays an optional check (owner approves the GPU use) before real batch use |
| **V2-3 Library + Workspace** | Codex | `characterTypes.ts`, ApiClient methods, mock fixtures, `CharacterLibraryPage` (with delete), `CharacterWorkspacePage` (identity header, canvas with movable nodes, inspector) | TEST_PLAN §5.1–5.3 pass; axe and themes clean; VI/EN parity | In progress |
| **V2-4 Stage Detail S1–S4** | Codex | Shared layout + S1, S2, S3 (preview batch UI), S4 (task list, manifest review) | TEST_PLAN §5.4–5.6 pass | In progress |
| **V2-5 S5 + planned S6/S7** | Codex | S5 batch submit/status/results/retry/approval; S6/S7 read-only; optional Studio prefill | TEST_PLAN §5.7–5.8 pass | In progress |
| **V2-6 Integration & sign-off** | Both, owner | End-to-end in HTTP mode against the mock backend, then one real character to S5 on Kaggle (owner-approved GPU use) | TEST_PLAN §6 passes; PRODUCT_SPEC §8.5 demonstrated; owner sign-off | Not started |

- Codex builds against the fixtures, as in M1/M2. S5 needs a `text_to_2d` model; the mocks are enough for tests.
- **Ownership:** Claude Code owns the docs, `characters/`, `api/characters.py`, the job-service batch entry point, `models/` changes, Python tests and `tests/fixtures/contracts/v2/`. Codex owns `interface/frontend/` and `design/stitch/v2/` (a layout reference only).

## M5 — Image-to-3D Models

- **Scope:** benchmark first, then integrate. Full-body characters come first.
- **Prerequisites:** M4 stable (at least one category in use).
- **Out of scope:** rigging, animation, Unity, Text→3D.

**Tasks**
- [ ] Build the fixed private benchmark set: several full-body characters, each with front, side and back views.
- [ ] Run the benchmark. It measures **multiview fidelity** (silhouette, face, hair, outfit, colors), **geometry** (manifoldness, floating parts, triangle count), **texture** (resolution, seams, color accuracy), **Kaggle fit** (VRAM, runtime vs. session limit, quota cost) and **failure rate**. Scoring uses a human rubric plus automatic metrics where feasible.
- [ ] Benchmark report in `docs/`.
- [ ] The owner picks the model(s) (D-032); the choice is recorded in DECISIONS (DF-02).
- [ ] Adapters whose capability records declare the supported views.
- [ ] The UI states that unseen regions are approximated.
- [ ] Tests as in M4.
- [ ] GLB structural checks.
- [ ] V-02/V-03/V-04 against the real records; contract tests pass.
- [ ] Owner sign-off.

## M6 — Text-to-3D Models

- **Scope:** set `text_to_3d` to `available` and integrate models under the same contracts.
- **Prerequisites:** M4 and M5 stable.
- **Out of scope:** rigging, animation, engine integration.

**Tasks**
- [ ] Research note and capability records; the owner picks the model(s) (D-032).
- [ ] Adapters.
- [ ] Availability change (a MINOR bump only if the schema changes).
- [ ] A GLB is produced for each fixed prompt per category.
- [ ] Tests follow the M4/M5 pattern. Example C (CONTRACTS §3.2) now succeeds, and all earlier tests pass.
- [ ] Owner sign-off.
