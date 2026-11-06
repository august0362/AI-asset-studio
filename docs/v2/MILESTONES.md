# V2 Milestones — Character Production

> **Status: APPROVED by the owner on 2026-11-06 (D-035).** It extends [docs/MILESTONES.md](../MILESTONES.md); the same
> definition of done applies: every listed test passes, fixtures validate on both sides, no secrets anywhere,
> DECISIONS updated, owner sign-off.

## 1. Order and gates

| Milestone | Owner of the work | Scope | Completion gate |
|---|---|---|---|
| **V2-0 Contract freeze** | Claude Code (docs), owner | This document set; the open decisions below are answered | **Done 2026-11-06**: owner approval (D-035); CONTRACTS v1.1 merged as §13 (D-037); fixtures in `tests/fixtures/contracts/v2/` |
| **V2-1 Backend core** | Claude Code | `characters/` package: IDs, store (atomic, exclusive-create revisions, history), StageConfig, routes 1–14, approval rules, staleness, freezing; fixtures `tests/fixtures/contracts/v2/` | TEST_PLAN §2 and §3 pass in mock mode; all v1 tests pass. **Done 2026-11-06** (owner sign-off, D-038; route 19 *delete character* added) |
| **V2-2 Batch execution** | Claude Code | `GenerationRequest.tasks`, `request.batch`, `Artifact.task_id`, `BATCH_PARTIAL`; batch support in the adapter and remote entry (one load per job, per-task results, deadline); routes 15–18; reconciliation | TEST_PLAN §4 passes with the mock adapter; **one** live Kaggle batch smoke run (owner approves the GPU use first) shows one model load for ≥ 2 tasks. **Done 2026-11-06** (owner sign-off, D-038): B-01…B-12 pass with the mock adapter; the owner accepted V2-2 without the live run B-13, which stays an optional check before real batch use |
| **V2-3 Library + Workspace** | Codex | `characterTypes.ts`, ApiClient methods, mock fixtures, `CharacterLibraryPage`, `CharacterWorkspacePage` (identity header, canvas, inspector) | TEST_PLAN §5.1–5.3 pass; axe and themes clean; VI/EN parity |
| **V2-4 Stage Detail S1–S4** | Codex | Shared layout + S1, S2, S3 (preview batch UI), S4 (task list, manifest review) | TEST_PLAN §5.4–5.6 pass |
| **V2-5 S5 + planned S6/S7** | Codex | S5 batch submit/status/results/retry/approval; S6/S7 read-only; optional Studio prefill | TEST_PLAN §5.7–5.8 pass |
| **V2-6 Integration & sign-off** | Both, owner | End-to-end in HTTP mode against the mock backend, then one real character to S5 on Kaggle (owner-approved GPU use) | TEST_PLAN §6 (regression) passes; PRODUCT_SPEC §5 acceptance criteria demonstrated; owner sign-off |

- V2-1 and V2-3 can run in parallel once V2-0 is approved: Codex builds against the fixtures, as in M1/M2.
- V2 does not depend on M5/M6. S5 needs a `text_to_2d` model: the mocks are enough until the M4 models are
  integrated.
- **M4 dependency:** V2-2 extends the M4 real-model adapter with batch support, so it is planned after that adapter
  passes its own smoke runs (OD-12). Met on 2026-11-06: all three M4 models pass (D-036).

## 2. Responsibilities

| Area | Claude Code | Codex |
|---|---|---|
| `docs/v2/*`, `docs/CONTRACTS.md` merge, DECISIONS | ✔ | reads |
| `interface/backend/…/characters/`, `api/characters.py`, job service batch entry point | ✔ | — |
| `models/` (GenerationRequest.tasks, adapter, remote entry) | ✔ | — |
| Python tests, contract fixtures (`tests/fixtures/contracts/v2/`) | ✔ | reads |
| `interface/frontend/` (types, client, pages, components, i18n, Playwright) | — | ✔ |
| `design/stitch/v2/` (reference only) | handoff notes | ✔ |

## 3. Open decisions (owner) — all accepted as proposed on 2026-11-06 (D-035)

| ID | Decision | Proposal |
|---|---|---|
| OD-01 | Merge V2 contracts into `docs/CONTRACTS.md`, or keep `docs/v2/CONTRACTS.md` linked from it | Merge into CONTRACTS.md as v1.1 sections (one source of truth); keep `docs/v2/` for workflow/spec |
| OD-02 | Stage IDs: `s1`…`s7` | Accept |
| OD-03 | Required purposes for S4/S5: `full_body`, `front`, `side`, `back`; portrait/key visual optional. The V2 brief lists Portrait and Key Visual among S4 outputs; the owner's workflow makes them optional before 3D | Accept the proposal; the owner can add `portrait`/`key_visual` as required later (a config change) |
| OD-04 | Character deletion / archive | **Changed by the owner 2026-11-06 (D-038):** hard delete, `DELETE /characters/{id}` (CONTRACTS §13.6 route 19); no archive |
| OD-05 | Seeds: v1 jobs with `seed: null` do not record the drawn seed | S4 production tasks always carry an explicit seed (the UI pre-fills one); preview batches may use random seeds |
| OD-06 | Frozen copies of approved images (duplicates the selected PNGs only) | Accept; the alternative (blocking job deletion) would change v1 behaviour |
| OD-07 | When S6 becomes `available` | After M5 ships a real `image_to_3d` model and a DECISIONS entry flips it |
| OD-08 | Splitting one task group across both T4s (two processes, two model loads, about half the wall time) | Not in V2; revisit after measuring real batch runs |
| OD-09 | Local preview inference | `planned`: the local GPU (4 GB) cannot hold any chosen model; a separate local compute client would be new infrastructure |
| OD-10 | v1 `POST /jobs/{id}/retry` on a batch job | Return `409 JOB_NOT_RETRYABLE` (`use_batch_retry`) so retries always update the manifest |
| OD-11 | Canvas implementation | Hand-written SVG + CSS transform (7 fixed nodes; no new dependency). Alternative: `@xyflow/react` (MIT) if Codex finds pan/zoom accessibility too costly |
| OD-12 | V2 order relative to M4 | V2-0/V2-1/V2-3 now; V2-2 after the M4 adapter passes its smoke runs |
| OD-13 | Preview default model | FLUX.2 [klein] 4B (~9 s/image); production: the owner's choice per character |
| OD-14 | Placement of the owner's `CHARACTER_PRODUCTION_WORKFLOW.md` (repository root) | Keep it where it is as the source material; V2 docs link to it |

## 4. Conflicts found while drafting (resolved as proposed)

| # | Conflict | Sources | Proposed resolution |
|---|---|---|---|
| C-01 | The V2 brief asks for `docs/THEMES.md` and `docs/LOCALIZATION.md` | Brief vs repo | Both were merged into [UI.md](../UI.md) on 2026-11-06; V2 refers to UI.md |
| C-02 | `design/stitch/v2/` did not exist; the exports were in `interface/frontend/AI_Asset_Studio_V2_Stitch_11_Exports_Handoff.zip` | Brief vs repo | Extracted unchanged into `design/stitch/v2/` (33 files, SHA-256 verified against MANIFEST.json) |
| C-03 | Rigging/animation/Unity are excluded from the product, but S7 is a stage | PRODUCT_SPEC §7 vs brief | S7 exists as a `planned`, read-only stage; enabling it needs a product-scope decision |
| C-04 | The prototypes show reviewers, multi-user comments and an "AI pipeline agent" | Stitch vs PRODUCT_SPEC (one user, DF-10) | Single owner; notes are the owner's; no agent |
| C-05 | The prototypes show P100, LoRA stacks, trigger tokens, Face-Lock/ArcFace scores, prompt adherence/consistency %, GPU temperature, VRAM, latency and memory bars | Stitch vs D-031, NFR-3 | Removed; only stored or v1-reported values are shown |
| C-06 | The Stitch DESIGN.md defines its own palette (purple accent) | Stitch vs UI.md tokens | UI.md's 22 tokens and four themes win; Stitch is layout reference only |
| C-07 | `DELETE /jobs/{id}` removes artifacts, which approvals rely on | v1 §9 vs V2 approvals | Copy selected images on approval (OD-06) |
| C-08 | Staged uploads expire after 24 h | v1 §3.1/§9 vs references | References are promoted (copied) into the character |
| C-09 | v1 requires exactly one primary artifact; a batch yields many images | v1 §3.5 vs batches | Many `image` artifacts with `task_id`; the first succeeded task is primary |
| C-10 | `seed: null` loses the drawn seed | v1 vs provenance | Explicit seeds for production (OD-05) |
| C-11 | M4 Text→2D models are text-only: no identity conditioning, no reference image input | D-034 vs "use approved previews as references" | References recorded per model as `applied`/`not_applied` with a reason; never silently dropped |
| C-12 | The S4 required purposes differ between the brief and the owner's workflow | Brief vs CHARACTER_PRODUCTION_WORKFLOW | OD-03 |
| C-13 | The prototypes have "Export Character Package", "Fork", EXR packs, "subscribe to GPU notifications" and a "topology wireframe" | Stitch vs scope | Not in V2 |
| C-14 | Prototype IDs `#CHR-0042` and demo characters | Stitch vs contracts | Demo data; real IDs are `chr_<12 hex>` |
| C-15 | `docs/MILESTONES.md` status table still showed M4 "Not started" | repo | The status row was updated to reflect the benchmark and model choice (docs only) |
