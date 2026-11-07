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
| V2-3 Character Production: Library + Workspace | **Done** (2026-11-06, D-038, D-039) |
| V2-4 … V2-5 Character Production: Stage Detail | In progress (Codex) |
| UI refresh to the V2 Stitch look, canvas follow-ups | Implemented, awaiting owner sign-off (D-039; built by Claude Code at the owner's direction) |
| D-040 Multiple authorized profiles, one app-wide compute slot | Implemented and verified, awaiting owner sign-off (2026-11-06; backend work transferred to Codex for this task; uncommitted) |
| D-041/D-042 Text→2D run control, run groups, deletion, long prompts, style images | Implemented and verified, awaiting owner sign-off (2026-11-07; uncommitted) |
| V2-6 Character Production: integration and sign-off | Not started |
| M5 Image-to-3D Models | In progress: Kaggle benchmark run (D-043); the owner chose Meshy (D-044); contract v1.3 documented, implementation not started |
| M6 Text-to-3D Models | **Dropped** (owner, 2026-11-07, D-045): `text_to_3d` stays `planned` |

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

## D-040 — Multiple authorized profiles, one app-wide compute slot

Owner decision: [DECISIONS D-040](DECISIONS.md), resolving DF-04; behavior in [CONTRACTS §4 and §6.1](CONTRACTS.md). No schema, field or error-code additions. The M3 one-profile acceptance above remains historical.

- [x] Documentation first: D-040, DF-04, A-02, Auth/Execution architecture rows, contract scheduling rule, `.env.example` and agent context.
- [x] Enable each listed, confirmed profile; read credentials only for enabled profiles; reject missing credentials by variable name; ignore `AAS_ACTIVE_PROFILE` with one notice.
- [x] Isolate auth checks, five-minute auth/quota refresh, subprocess env and empty config directory per enabled profile; retain per-profile refresh limiting.
- [x] Serialize v1 and V2 batch-group jobs through one FIFO compute slot, keeping each selected profile immutable, with no failover or resubmission.
- [x] Offline tests: configuration, three-profile isolation, FIFO across profiles and v1/V2 groups, failure behavior, secret scans and V-01…V-20; full pytest and frontend checks.
- [x] HTTP UI verification: ComputeInspector, BatchPanel and ResourcesPage with three enabled profiles, without a paid GPU run. Frontend changes, if needed, are reported as a separate Codex prompt.
- [ ] Owner sign-off. D-040 changes stay uncommitted until requested.

Verification (2026-11-06):

| Check | Result |
|---|---|
| `npx tsc --noEmit` | Pass, 0 errors |
| `npm run lint` | Pass, 0 errors/warnings |
| `npx vitest run` | 497 passed, 17 files |
| `npx playwright test --workers=2` (mock, isolated port 5189) | 60 passed, 11.6 min; axe in four themes and VI/EN, 1024/1440 px; Studio also 390 px |
| `npm run test:e2e:http` (isolated mock backend and frontend ports) | 4 passed, 48.3 s |
| `npm run build` | Pass, 1743 modules; existing large-chunk warning |
| `.venv/Scripts/python -m pytest -q` | 528 passed, 1 skipped, 3 live Kaggle tests deselected; 319.17 s |
| Focused D-040 configuration/client/FIFO tests plus validation matrix | 70 passed, 43.58 s |
| `ruff check interface/backend kaggle_connector models tests` | Pass |
| `ruff format --check` on nine changed/new Python files | Pass |
| HTTP UI with three enabled profiles plus one disabled profile, offline fake CLI | 3 checks passed: ComputeInspector, BatchPanel, ResourcesPage; selected profiles switch correctly, disabled option stays disabled, Resources `?profile=beta` works, all eight API snapshot responses 200; no jobs or remote submissions created |

- D-039 was committed and pushed to `origin/main` as `3c45827` using the owner's requested title. Only its 23 explicitly staged files were committed. Verification found and fixed the 390 px preference-control overflow. HTTP test URL/port overrides avoid collisions with the running application.
- D-040 code: `interface/backend/aas_backend/{profiles.py,settings.py,orchestrator/service.py,orchestrator/worker.py}` and `kaggle_connector/client/kaggle_cli.py`. Tests: updated `tests/unit/test_kaggle_profiles.py` and `tests/integration/test_kaggle_client.py`; added `tests/unit/test_kaggle_multi_profiles.py` and `tests/integration/test_multi_profile_jobs.py`.
- The FIFO test holds profile A while B and C remain `created`, exercises all four v1/batch combinations, verifies order and immutable profile IDs, then verifies failures never submit on another account. Profile tests cover disabled credential reads, missing credentials at startup, safe obsolete-variable notices, independent identity checks/caches/background refresh, separate subprocess envs/empty config directories and all-profile secret scans.
- D-040 needs no frontend change. The three-selector HTTP check uses the real backend with an injected offline fake CLI and synthetic account data. No paid GPU run was made; `.env` was not edited. Account ownership remains unverifiable (A-02).
- Evidence under `interface/frontend/test-results/`: D-039 screenshots `d039/{latte,mint,caffe,matcha}/{library,workspace,stage}-{en,vi}-{1024,1440}.png`; browser run `d039-final/`; HTTP suite `http/`; three-profile UI `d040-http/{compute-inspector,batch-panel,resources}.png` and `d040-http/ui-check.json`. The UI verification script is `d040-http/verify.py` (run from the repo root with `.venv/Scripts/python`). These are local test outputs, not committed fixtures.

## D-041 — Text→2D run control, run groups, deletion, long prompts, style images

Owner requests of 2026-11-07: [DECISIONS D-041 and D-042](DECISIONS.md), contract v1.2 in [CONTRACTS §14](CONTRACTS.md#14-run-control-run-groups-and-deletion-v12). **Implemented and verified (2026-11-07), awaiting owner sign-off; uncommitted.** D-040's code (uncommitted) is the base of the new scheduler; the owner may sign off both together.

Ownership: the owner assigned the whole task, frontend included, to Claude Code.

- [x] Documentation first: D-041, A-08, DF-15, CONTRACTS v1.2 (§1.3, §3.2, §4, §5, §6.4, §8.2, §14), ARCHITECTURE, PRODUCT_SPEC FR-G9 and FR-J5…FR-J11, UI glossary, `.env.example`, agent context.
- [x] **G.0 Verification session (before C and H; approved, D-042 (8)):** one Kaggle T4×2 session with a one-off tool outside the app, deleted afterwards, as in D-033. It touches no contract, registry or `data/`.
  - Animagine + IP-Adapter (D-042 (5)) with 0, 1, 2 and 4 style images; klein with 0, 1, 2 and 4 style images. Fixed seed, 1024×1024.
  - For each case: peak reserved GPU memory and seconds per image; the images go to the owner.
  - klein's prompt window: `max_sequence_length` 512, 1024 and 2048 with a long prompt whose last sentence asks for something visible. Record whether it runs and whether the late request shows.
  - Write the results in the DECISIONS run log, then set `max_images`, runtimes and klein's `prompt_max_length` from them (D-042 (7)).
- [x] **A. Contracts (§12):** fixtures for `scheduling`, `RunGroup`, the bulk-delete response and the new error codes; Pydantic models; TS types.
- [x] **B. Backend:**
  - `auto_run`, held and waiting jobs, `PATCH /jobs/{id}`.
  - Deleting held and waiting jobs, and `POST /jobs/delete`.
  - Held and waiting jobs keep their place after a restart.
  - Scheduler with `AAS_MAX_PARALLEL_SESSIONS`: one profile at a time, quota reservation within that profile.
  - Kernel deletion for failed jobs too.
- [x] **C. Run groups:**
  - `POST /jobs/groups` and its checks.
  - Generated kernel with two processes, one per T4.
  - Per-job manifests and log routing.
  - Shared status until `downloading`, then a separate outcome for each job.
  - The kernel is deleted once both jobs end.
- [x] **D. Prompts:**
  - Global limit of 10 000 characters.
  - Registry limits: Animagine XL 4.0 and MOSS-Image-SFT 10 000, FLUX.2 [klein] 8 192 (its 2 048-token window was measured in G.0, D-042 (10)).
  - Remote token check before the image model loads, failing with `MODEL_PROMPT_TOO_LONG`.
- [x] **E. Frontend (Codex):**
  - Text→2D form: an auto-run switch whose value is remembered; a character counter with the model's limit on the prompt field.
  - Jobs & logs:
    - An auto-run switch on each held or waiting job.
    - *Run together* for two selected held jobs.
    - Multi-select, *Select all completed* and *Delete selected*, with one confirmation.
  - Asset library:
    - *Delete*, which deletes the job, after a confirmation that names the job and its image count.
    - Remove the hard-coded `· MOCK` label on every card (`LibraryPage.tsx`) and show a mock badge only for `is_mock` models.
  - Use the UI.md §8 terms.
- [x] **H. Style images (D-042, CONTRACTS §14.9):**
  - Registry: Animagine and klein accept `style_reference` images with the measured `max_images`; Animagine gets `style_strength`.
  - Adapter and remote entry: IP-Adapter with the InstantStyle setting, loaded only when a job has style images; klein reference images; pinned downloads inside the run only.
  - Validation: the existing image rules (V-01…V-20) apply to the new inputs.
  - Frontend (Codex): a style-image area for those two models, with upload, paste from the clipboard and drag-and-drop; the `style_strength` slider for Animagine; a hint for klein. MOSS shows no image area.
- [x] **F. Data:** the owner asked to delete the PNG mock jobs: 11 `mock-t2d-basic` jobs deleted on 2026-11-07 through `DELETE /jobs/{id}` on the owner's backend (17 mock-model jobs were left, not 19). The 6 GLB `mock-i3d-multiview` jobs remain until the owner decides.
- [x] **G. Verification runs through the app** (approved, D-042 (8)):
  1. A group of two klein jobs on T4×2, about 5 GPU minutes: both GPUs used, both outputs valid, wall time close to one job's, kernel deleted.
  2. *(Dropped: the owner states that Kaggle has no concurrent-session limit, A-08.)*
  3. klein's prompt window: done in G.0.
  4. Through the app, after H: one Animagine job with 2 style images and one klein job with 2 style images, run as a group (G.1 can be the same run).
- [ ] Owner sign-off.

**Verification (2026-11-07):**

| Check | Result |
|---|---|
| `.venv/Scripts/python -m pytest -q` (live tests deselected) | 594 passed, 1 skipped, 330 s |
| `ruff check interface/backend kaggle_connector models tests`; `ruff format --check` on the changed files | Pass |
| `npx tsc --noEmit`, `npm run lint` | Pass |
| `npx vitest run` | 509 passed, 18 files |
| `npx playwright test` (mock, isolated port 5180) | 60 passed (existing specs) + 12 passed (`d041.spec.ts`: auto-run, *Run together*, multi-select delete, style area, library delete; axe in four themes × VI/EN at 1024/1440/390 px) |
| `npm run test:e2e:http` (isolated mock backend 8012, frontend 5181) | 5 passed (new case e: held job, switch, group refusal, bulk delete) |
| `npm run build` | Pass, 1746 modules; existing large-chunk warning |
| G.0 (one-off tool, three sessions on `atume`) | See the DECISIONS run log; about 0.5 h of T4×2 |
| Live CPU check, `AAS_KAGGLE_TEST_FAILURE=kernel_error` (isolated kaggle backend 8014) | `failed` with `KAGGLE_KERNEL_ERROR` in 80 s; logs kept in the app; kernel deleted on Kaggle (status read is refused afterwards) |
| Live G.1/G.4 run group (isolated kaggle backend 8013) | Second attempt, after the fix: both jobs `completed` in one kernel (`aas-grp-…`), one 332 s session, the same `remote_ref`. Animagine with 2 style images on GPU 0: 25.2 s per image (IP-Adapter downloaded in the run, images resized to 224×224); klein with 2 reference images on GPU 1: 57.1 s. Logs separated per job, telemetry stored for both, the kernel and both input datasets deleted ("Remote run cleaned up" in both logs). The second process waited 23 s for the install lock |

- The first live group run found a real bug: both processes ran `pip install` at once and collided (`OSError … /usr/local/bin/diffusers-cli`); Animagine failed, klein completed with 2 style images (44.1 s per image), and cleanup still deleted the kernel and both datasets. Fixed with an exclusive file lock around the install in the remote entry, with a test.
- A held job no longer blocks *Generate*: several held jobs can be created and then grouped.
- Owner requests during the work: a finished job's image now comes first in the job detail; the PNG mock jobs were deleted (F).

Not in scope: style images for MOSS, img2img, ControlNet, LoRA training, style images in V2 batch jobs, automatic grouping, groups of more than two, stopping a running job (DF-09).

**Acceptance:**
- With auto-run off, a job stays held through a backend restart. Turning auto-run on runs it.
- A group of two runs in one kernel. Both jobs complete, and the wall time is close to the longer job's. A failure in one job leaves the other unaffected.
- Held, waiting and terminal jobs can be deleted; a started job is refused. The bulk delete reports a result for each job.
- A failed job's kernel is deleted (live CPU check with `AAS_KAGGLE_TEST_FAILURE=kernel_error`, no GPU).
- Prompts:
  - A 10 000-character prompt is accepted for Animagine and MOSS.
  - A 2 001-character prompt is rejected for klein.
  - A prompt longer than its encoder window fails with `MODEL_PROMPT_TOO_LONG` before the image model loads.
- Real images carry no MOCK label. Deleting an asset removes its job.
- V-01…V-20, the D-040 FIFO tests and the secret scans still pass.

**Tests:**
- Offline:
  - Scheduler: held, waiting and starting; FIFO order; one profile at a time; quota reservation; restart.
  - Group checks (every `reason`).
  - Group kernel package and per-job log routing, with the fake CLI.
  - Delete, bulk delete and the delete/slot race.
  - Kernel cleanup for failed jobs.
  - Prompt limits and the token check (mock runtime).
- Frontend (Vitest and Playwright, mock):
  - Auto-run switch and *Run together*.
  - Multi-select delete.
  - Library delete and the mock badge.
  - Prompt counter.
  - axe in four themes, VI/EN.
- Style images: registry records, validation of `style_reference` inputs, `style_strength`, the adapter building IP-Adapter and klein arguments, no adapter load without images (mock runtime); V2 prompt fields at 10 000.
- Live (`kaggle`, opt-in): G.0 (one-off tool), G.1 and G.4.

---

## V2 — Character Production

Scope and acceptance criteria: [PRODUCT_SPEC.md §8](PRODUCT_SPEC.md#8-character-production-v2). Tests: [v2/TEST_PLAN.md](v2/TEST_PLAN.md). Decisions OD-01…OD-14: [DECISIONS.md](DECISIONS.md#v2-open-decisions-od).

| Milestone | Owner of the work | Scope | Completion gate | Status |
|---|---|---|---|---|
| **V2-0 Contract freeze** | Claude Code (docs), owner | Docs; the OD decisions answered | Owner approval | **Done**: D-035; CONTRACTS v1.1 merged as §13 (D-037); fixtures in `tests/fixtures/contracts/v2/` |
| **V2-1 Backend core** | Claude Code | `characters/` package: IDs, store (atomic, exclusive-create revisions, history), StageConfig, routes 1–14 and 19, approval rules, staleness, freezing | TEST_PLAN §2 and §3 pass in mock mode; all v1 tests pass | **Done** (D-038; route 19 *delete character* added) |
| **V2-2 Batch execution** | Claude Code | `GenerationRequest.tasks`, `request.batch`, `Artifact.task_id`, `BATCH_PARTIAL`; batch support in the adapter and remote entry (one load per job, per-task results, deadline); routes 15–18; reconciliation | TEST_PLAN §4 passes with the mock adapter | **Done** (D-038): B-01…B-12 pass; the owner accepted it without the live run B-13, which stays an optional check (owner approves the GPU use) before real batch use |
| **V2-3 Library + Workspace** | Codex | `characterTypes.ts`, ApiClient methods, mock fixtures, `CharacterLibraryPage` (with delete), `CharacterWorkspacePage` (identity header, canvas with movable nodes, inspector) | TEST_PLAN §5.1–5.3 pass; axe and themes clean; VI/EN parity | **Done** (D-039). The follow-ups in D-039 (smooth drag, data-flow edges, double-click, V2 Stitch look) are tracked separately |
| **V2-4 Stage Detail S1–S4** | Codex | Shared layout + S1, S2, S3 (preview batch UI), S4 (task list, manifest review) | TEST_PLAN §5.4–5.6 pass | In progress |
| **V2-5 S5 + planned S6/S7** | Codex | S5 batch submit/status/results/retry/approval; S6/S7 read-only; optional Studio prefill | TEST_PLAN §5.7–5.8 pass | In progress |
| **V2-6 Integration & sign-off** | Both, owner | End-to-end in HTTP mode against the mock backend, then one real character to S5 on Kaggle (owner-approved GPU use) | TEST_PLAN §6 passes; PRODUCT_SPEC §8.5 demonstrated; owner sign-off | Not started |

- Codex builds against the fixtures, as in M1/M2. S5 needs a `text_to_2d` model; the mocks are enough for tests.
- **Ownership:** Claude Code owns the docs, `characters/`, `api/characters.py`, the job-service batch entry point, `models/` changes, Python tests and `tests/fixtures/contracts/v2/`. Codex owns `interface/frontend/` and `design/stitch/v2/` (a layout reference only).

## M5 — Image-to-3D Models

- **Scope:** benchmark first, then integrate. Full-body characters come first. Since D-044 the integrated model is Meshy's hosted API, not a Kaggle model.
- **Prerequisites:** M4 stable (at least one category in use).
- **Out of scope:** rigging, animation, Unity, Text→3D.

**Tasks**
- [ ] Build the fixed private benchmark set: several full-body characters, each with front, side and back views.
- [x] Run the benchmark. It measures **multiview fidelity** (silhouette, face, hair, outfit, colors), **geometry** (manifoldness, floating parts, triangle count), **texture** (resolution, seams, color accuracy), **Kaggle fit** (VRAM, runtime vs. session limit, quota cost) and **failure rate**. Scoring uses a human rubric plus automatic metrics where feasible.
- [ ] Benchmark report in `docs/`.
- [x] The owner picks the model(s) (D-032); the choice is recorded in DECISIONS (DF-02): **Meshy** (`meshy-7.1`) over the hosted API (D-044).
- [x] Contract v1.3 documented: CONTRACTS §15, ARCHITECTURE §6.1, D-044, A-09.
- [ ] The owner registers a paid Meshy plan, creates an API key with a monthly credit limit and puts it in `.env` as `AAS_MESHY_API_KEY` (never in chat or the repo).
- [ ] v1.3 fixtures (`tests/fixtures/contracts/v1_3/`), Pydantic models and TS types (CONTRACTS §15.10).
- [ ] `MeshyApiClient` and `MockMeshyClient` behind `ComputeClient`; Meshy FIFO slots; credit planning; snapshot with credits; task cleanup.
- [ ] Adapter `meshy_image_to_3d` whose capability record declares the supported views (CONTRACTS §15.2).
- [ ] Frontend (Codex, from a handoff prompt): Meshy plan panel, Resources card, consumed credits, data-leaves-the-machine note.
- [ ] The UI states that unseen regions are approximated.
- [ ] Tests as in M4, in mock mode: every §15.8 code, no key in `data/` or responses, no signed URL stored.
- [ ] GLB structural checks.
- [ ] V-02/V-03/V-04 against the real records; contract tests pass.
- [ ] Live smoke run (marked `meshy`, owner approves the credits): the three benchmark characters; measure the runtime for `estimated_runtime_seconds`.
- [ ] Owner sign-off.

## M6 — Text-to-3D Models

- **Status: dropped (D-045).** The owner does not want a text → image → 3D path; `text_to_3d` stays `planned` and the tasks below are not done.
- **Former scope:** set `text_to_3d` to `available` and integrate models under the same contracts.
- **Prerequisites:** M4 and M5 stable.
- **Out of scope:** rigging, animation, engine integration.

**Tasks**
- [ ] Research note and capability records; the owner picks the model(s) (D-032).
- [ ] Adapters.
- [ ] Availability change (a MINOR bump only if the schema changes).
- [ ] A GLB is produced for each fixed prompt per category.
- [ ] Tests follow the M4/M5 pattern. Example C (CONTRACTS §3.2) now succeeds, and all earlier tests pass.
- [ ] Owner sign-off.
