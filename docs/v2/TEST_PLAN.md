# V2 Test Plan — Character Production

> **Status: APPROVED by the owner on 2026-11-06 (D-035).** Milestone gates: [MILESTONES.md § V2](../MILESTONES.md#v2--character-production).

Default tests run in mock mode (`AAS_COMPUTE_MODE=mock`, `VITE_API_MODE=mock`). Live Kaggle tests are opt-in
(`-m kaggle`), and each one needs the owner's approval before it uses GPU quota.

## 1. Fixtures

- `tests/fixtures/contracts/v2/*.json` holds every JSON example in [CONTRACTS.md §13.6.2](../CONTRACTS.md#1362-examples), plus one full
  `CharacterWorkflow`, one `StageDetail` per stage, and a `BatchManifest` in each `batch_status`.
- **Backend:** each fixture validates against its Pydantic model. **Frontend:** the mock client serves them and a
  Vitest test type-checks them. A fixture that fails either side breaks the build (as v1 §11).

## 2. Backend unit tests

| Area | Cases |
|---|---|
| IDs and paths | Every new ID regex (valid and invalid); `PATH_INVALID` before any file access; no user text in a path; links and `..` rejected |
| Storage | Atomic writes (a crash mid-write leaves the old file); revisions use exclusive create (a second write fails); history append and a torn last line; per-character lock serializes concurrent writes |
| Status derivation | `editorial_status` for every row of CONTRACTS §13.5.3 (table-driven); `blocked` vs `not_started`; `draft` while an older approval stays in use |
| Staleness | Re-approving S2 marks S3/S4 (hard) and S5 (soft) stale with the correct `StaleReason`; resubmitting and approving clears it; nothing is written by staleness |
| Approval gate | Each §5.2 condition alone makes approval fail with its code; all conditions met → approved; a failed approval changes nothing |
| Content rules | Per stage (CHARACTER_WORKFLOW §3): S1 idea/reference + direction; S2 locked attribute; S3 exactly one selected; S4 required purposes and tasks, valid model/options, session-limit fit; S5 one selected per required purpose |
| Freezing | S3/S5 approval copies selected PNGs, verifies `sha256`, records provenance; a sha mismatch → `LINKED_ARTIFACT_INVALID`, nothing approved |
| Manifest | Freezing S4 binds `approved_spec_revision`/`prompt_set_revision`; grouping by model (one group per model, `expected_model_loads = len(groups)`); `estimated_runtime_seconds` = per-image time × tasks; references `applied`/`not_applied` with reasons |
| Batch status | `batch_status` and `retryable_task_ids` for every task-status combination (§5.6) |
| Concurrency | `CHARACTER_VERSION_CONFLICT`, `STAGE_DRAFT_CONFLICT` with the current versions in `details` |

## 3. API contract and integration tests (mock compute)

| ID | Scenario | Expected |
|---|---|---|
| I-01 | Create, list (search, `stage`, `status` filters), get, rename | Rename keeps `character_id`; `version` increments; history events |
| I-02 | Full S1 → S5 in mock mode | Every stage approved; S5 frozen assets exist; `GET /outputs` lists them |
| I-03 | Promote an upload; delete it while referenced | `ReferenceAsset` created, the file copied; delete → `409 REFERENCE_IN_USE` |
| I-04 | URL reference | Stored; no network request (the test asserts no outgoing HTTP) |
| I-05 | Link a Studio job to S3 and S5 | `ResolvedJob` filled from the v1 record; job data not copied |
| I-06 | Delete the source job of an approved image | Approval unchanged; frozen file downloadable; draft items show `missing: true` |
| I-07 | Upstream change | Approve S2 r2 → S3/S4/S5 `needs_revision`; old snapshots and assets intact; no job created |
| I-08 | Planned stages | Draft/decisions on S6/S7 → `STAGE_NOT_AVAILABLE` |
| I-09 | Unknown fields, wrong types, bad IDs | `REQUEST_FIELD_INVALID` / `PATH_INVALID` with the v1 envelope |
| I-10 | Two tabs | The second save with an old `expected_draft_version` → 409, the first save intact |
| I-11 | Delete a character (D-038) | `204`; its folder is gone, it leaves the list, every route on it → `CHARACTER_NOT_FOUND`; the v1 jobs of its batches remain; a running batch attempt → `409 BATCH_ATTEMPT_RUNNING` and nothing is removed; a leftover `.deleted-*` folder is removed at startup |

## 4. Batch execution tests

Run with the mock adapter and a fake compute client unless marked *live*.

| ID | Requirement | Test |
|---|---|---|
| B-01 | **No unnecessary model loads** | A batch job with 3 tasks for one model: the remote entry's load counter (the `MODEL_LOAD …` log line, CONTRACTS §13.9) is exactly 1; two models → two jobs → two loads, and `expected_model_loads = 2` |
| B-02 | **Manifest consistent with approved revisions** | The frozen manifest's revisions equal the S2/S4 approvals; re-approving S2 or S4 → submit returns `BATCH_MANIFEST_STALE`; tasks equal the S4 revision's tasks exactly |
| B-03 | **No production before approval** | Submit with S4 not approved, pending or stale → rejected; preview batch with S2 not approved → `STAGE_BLOCKED`; no job is created in any of these cases |
| B-04 | **Partial failure** | Task 2 of 3 raises → job `completed` with `BATCH_PARTIAL`; results: succeeded/failed/succeeded; primary = task 1 |
| B-05 | **Task-level resume** | Retry after B-04 creates one job with only task 2; tasks 1 and 3 are never re-rendered (call counter); attempts = 2 |
| B-06 | **Deadline** | The budget ends after task 1 → tasks 2–3 `not_run`; the job still completes; their images are not lost |
| B-07 | **No lost results** | Every succeeded task has an artifact with its `task_id` and matching `sha256` after reconciliation; a whole failed job → all tasks `failed` with the job error |
| B-08 | **No fake telemetry** | Batch and stage responses contain no GPU/VRAM/progress field that is absent from v1 payloads; the remote entry emits telemetry only through the v1 runner |
| B-09 | **Preview and production models may differ** | Preview batch with model A, production with model B: both succeed; previews are labelled with A; no response claims B's output from A's |
| B-10 | No model mixing | A manifest can only contain `text_to_2d` tasks; an `image_to_3d` model in S4 → `MODEL_PIPELINE_INCOMPATIBLE` (v1 code) |
| B-11 | v1 retry on a batch job | `409 JOB_NOT_RETRYABLE` with `use_batch_retry` (OD-10) |
| B-12 | Idempotency | Repeating submit with the same `client_request_id` creates no second job |
| B-13 *live* | One real batch on Kaggle (owner-approved) | ≥ 2 tasks for one M4 model; the log shows one model load; per-task PNGs downloaded and reconciled |

## 5. Frontend tests (Vitest + Playwright, mock API)

| ID | Area | Checks |
|---|---|---|
| 5.1 | Library | Search and filters call the API with the right params; counts derive from listed data only; empty state; create dialog; delete with a confirmation dialog naming the character, then the list refreshes (`BATCH_ATTEMPT_RUNNING` shown localized) |
| 5.2 | Canvas | 7 nodes, no add/delete/connect affordance; nodes can be dragged and the edges follow, with no re-render of the page and no `localStorage` write per pointer move (saved once on drop); double-click on a node opens its Stage Detail (Enter does the same from the keyboard); an edge animates *data flow* in `--mana` only when its upstream stage has an approved, non-stale revision, and is static under `prefers-reduced-motion`; positions persist per character in `localStorage` (survive reload; a missing or corrupt value falls back to the default); *Reset layout*; edges run output → input in stage order; pan, zoom, fit view; keyboard selection; edges highlighted for the selection; hard (solid) vs soft (dashed); stale edge marked |
| 5.3 | Inspector + navigation | Every stage shows objective, inputs, outputs, checklist, blockers; selecting S5 → Stage Detail → back keeps `?node=s5` selected (URL and focus) |
| 5.4 | Shared layout | One `StageDetailPage` renders all seven configurations; input zone read-only; approval zone lists blockers and disables Approve while any exist |
| 5.5 | Drafts | Save sends `expected_draft_version`; a 409 shows *Reload* without losing the user's text |
| 5.6 | S3/S4 batch UI | Generate Quick Preview disabled with blockers until S2 is approved; gallery labels previews with their model; S4 shows tasks, `expected_model_loads`, the estimate (labelled) and the resource-plan fit from the payload |
| 5.7 | S5 | Submit disabled until the manifest is current; job status from v1; per-task results; Retry shown only with `retryable_task_ids`; final approval needs every required slot |
| 5.8 | Planned | S6/S7 read-only, labelled *Planned*; no enabled action |
| 5.9 | Honesty | Source check: no hard-coded GPU, VRAM, temperature, percentage or similarity value in `features/characters/` (same approach as the v1 colour-literal check) |
| 5.10 | i18n + themes | Dictionary parity for all new keys; every new error code localized; axe clean in all four themes, VI and EN, at 1024 and 1440 px; status never by colour alone; the 24 tokens of UI.md §2 match `tokens.json` and `app.css` |

## 6. Regression

- All v1 backend tests (pytest) and frontend tests (Vitest, Playwright mock and HTTP) pass unchanged, including the
  validation matrix V-01…V-20.
- Non-batch jobs: `request.batch` is `null` and `Artifact.task_id` is `null`; the v1 fixtures still validate (the new
  fields are optional).
- `POST /jobs/{id}/retry` behaves as before for non-batch jobs.
- The import-boundary test still passes: `characters/` lives in the backend and imports neither `kaggle_connector`
  nor anything from the frontend.
