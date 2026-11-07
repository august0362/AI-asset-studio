# Product Specification

What the product does and why. How it is built is in [ARCHITECTURE.md](ARCHITECTURE.md) and [CONTRACTS.md](CONTRACTS.md).

## 1. Goal and user

A local-first tool that turns prompts and 2D concept art into game assets. Inference runs as batch jobs on Kaggle, and Image→3D runs on the hosted Meshy API (D-044). All data stays on the user's machine, except the images and prompt of a Meshy job, which are sent to Meshy. It serves **one local user** (a game developer) and has no multi-user accounts.

## 2. Pipelines

| Pipeline | Priority | Input → Output | Status |
|---|---|---|---|
| Text → 2D (`text_to_2d`) | First real AI pipeline (M4) | Prompt (+ style reference if the model supports it) → PNG | Real models for `character` (D-034) |
| Image → 3D (`image_to_3d`) | Highest quality priority (M5) | One or more views (front, side, back…) → GLB with geometry and textures | Meshy (`meshy-7.1`) chosen (D-044); documented, implementation in M5. Mock models until then |
| Text → 3D (`text_to_3d`) | Dropped (M6, D-045) | Prompt → GLB | `planned`: visible but disabled |

**Image → 3D intent:** full-body characters first. The result should preserve identity, anatomy, silhouette, face, hair, outfit, colors and style as closely as the model allows. Perfect reconstruction is **never** promised, especially for regions the references do not show, and the UI says so next to the result.

## 3. Asset categories

- `character`: humanoid, full body preferred.
- `skill_effect`: **visual-only** concepts for skills (effects, auras, projectiles, props). Never gameplay logic.
- `weapon`: weapons, shields, tools.
- `companion`: pets, creatures, mounts.

Each model declares the categories it supports. The owner chooses every real model (D-032).

## 4. Workflows

1. **Generate:** pipeline → category → model (filtered) → a form showing only the inputs that model accepts → prompt and/or images, each with a role → profile and accelerator (or Auto) → review errors, warnings and resource fit → Generate.
2. **Monitor:** status timeline, progress, logs, and live telemetry when available.
3. **Review:** PNG preview or an interactive GLB viewer, then download.
4. **History:** list, filter, reopen, retry (retryable failures only) and delete jobs.
5. **Resources:** profile health, quota, session and telemetry, before or during a job.
6. **Character Production:** a character goes through seven approved stages, from idea to an approved 2D set (§8).

## 5. Functional requirements

**Generation and validation**

| ID | Requirement |
|---|---|
| FR-G1 | List pipelines, categories and compatible models from the backend |
| FR-G2 | Build the form from the model's `ModelCapabilities`, not hard-coded |
| FR-G3 | Accept text and zero, one or many images, each with a role |
| FR-G4 | Validate on every change in the UI. The backend re-validates with the same rules |
| FR-G5 | Reject invalid requests before any remote call. Never silently discard images, prompt or options |
| FR-G6 | On a model change, re-validate, keep all uploads and values, and mark incompatible fields |
| FR-G7 | Every error has a stable code, the affected field and a clear message |
| FR-G8 | Errors disable Generate. Warnings are shown but do not block |
| FR-G10 | Text→2D with Animagine XL 4.0 or FLUX.2 [klein]: optional style images, added by upload or paste, plus the prompt. The model takes the style from the images and the content from the prompt; with no image it follows the prompt only. MOSS-Image-SFT is prompt-only (D-042) |
| FR-G9 | Prompts up to 10 000 characters, or less where the model's text encoder needs it; the prompt field shows the count and the model's limit. Prompts are never truncated (D-041) |

**Jobs and artifacts**

| ID | Requirement |
|---|---|
| FR-J1 | Create, list, view, retry (when retryable) and delete jobs |
| FR-J2 | Show status, the timeline, progress, logs and errors |
| FR-J3 | PNG inline preview, and GLB in a Three.js viewer (orbit, zoom, reset) |
| FR-J4 | Download each artifact as `<job_id>_<artifact_id>.<ext>` |
| FR-J5 | Jobs survive a backend restart. Held and waiting jobs keep their place |
| FR-J6 | Auto-run switch: on, a new job runs by itself (one job, one Kaggle session); off, it is held in `created` until the owner turns auto-run on or runs it in a group. The switch can be flipped while the job waits (D-041) |
| FR-J7 | Group exactly two held Text→2D jobs into one Kaggle session, one job per T4; each job keeps its own results. No automatic grouping |
| FR-J8 | Delete held or waiting jobs (nothing has reached Kaggle yet), and delete many jobs at once, with "select all completed" and one confirmation |
| FR-J9 | Delete an asset from the Asset library; this deletes the job that produced it, after a confirmation. A mock label appears only on assets of mock models |
| FR-J10 | Up to `AAS_MAX_PARALLEL_SESSIONS` Kaggle sessions run at the same time, on one profile at a time |
| FR-J11 | The Kaggle notebook of every finished job, completed or failed, is deleted after its logs and outputs are stored locally |

**Kaggle resources**

| ID | Requirement |
|---|---|
| FR-R1 | Profile authentication status and health |
| FR-R2 | Weekly GPU/TPU quota (total, used, remaining) and reset time **when Kaggle reports them**, otherwise "unknown" |
| FR-R3 | Session status, plus an estimated time remaining labeled as an estimate |
| FR-R4 | CPU % and RAM used/total for the running session |
| FR-R5 | **GPU0 and GPU1 separately:** utilization, VRAM, and temperature when available |
| FR-R6 | Source, timestamp and freshness for every metric group. Never present stale or missing data as live |
| FR-R7 | Predicted job fit (`ok`/`unknown`/`insufficient`) with reasons |
| FR-R8 | Explicit profile selection among authorized profiles only. Auto picks only the accelerator within that profile |
| FR-R9 | Meshy: authentication status and credits (balance, monthly, permanent, reset time) with source and freshness; each Meshy job shows its estimated credits before Generate and the credits it really used afterwards (D-044, CONTRACTS §15) |

**Appearance** ([UI.md](UI.md))

| ID | Requirement |
|---|---|
| FR-U1 | Light and dark mode, plus a "system" setting that follows the OS |
| FR-U2 | Two color themes per mode: light `latte` and `mint`, dark `caffe` and `matcha` |
| FR-U3 | The theme choice persists across reloads and applies before the first paint |
| FR-U4 | Every theme meets WCAG AA contrast, and status is never shown by color alone |
| FR-U5 | Previews (PNG, GLB viewer) follow the theme's viewer colors without reloading the asset |
| FR-U6 | The UI is available in Vietnamese and English, switchable at any time (UI.md §5) |
| FR-U7 | The first visit picks Vietnamese when the browser prefers it; the choice persists across reloads |
| FR-U8 | Error and warning text is localized by error code, falling back to the backend's English message |
| FR-U9 | Dates and numbers are formatted for the selected language |

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 Local-first | The backend binds to `127.0.0.1`. All data stays in `data/`. One exception (D-044): the images and prompt of a Meshy Image→3D job are sent to Meshy, and the UI says so |
| NFR-2 Secrets | Kaggle credentials and the Meshy API key never reach the frontend, logs, job files, notebooks or the repo |
| NFR-3 Honesty | No fabricated telemetry, quota or runtime. Unknowns are shown as unknown, and estimates are labeled |
| NFR-4 Compliance | Kaggle ToS: one account per person; no quota circumvention or account rotation (D-008) |
| NFR-5 Reliability | Atomic metadata writes. Failures keep inputs and logs. Transient retries are bounded, and runs are never auto-resubmitted |
| NFR-6 Simplicity | 3 modules. No DB, broker, containers or multi-user auth |
| NFR-7 Testability | Everything runs end-to-end in `mock` mode without Kaggle or a GPU |
| NFR-8 Responsiveness | UI validation < 100 ms. Status polling every 2 s. Local API < 500 ms (excluding file transfer) |

## 7. Scope

**MVP (through M3):** three pipeline screens, four categories, model-driven forms and validation, mock adapters producing real PNG/GLB, history, previews and downloads, and one authorized Kaggle profile with quota, status, logs, downloads and a best-effort telemetry proof of concept.

**Excluded:**
- Rigging, animation, Unity or engine integration.
- Executable skill logic.
- Multi-user auth.
- Docker, Kubernetes, Redis, Celery, RabbitMQ, cloud databases and microservices.
- Account rotation, quota pooling or circumvention.
- Persistent or real-time inference.
- Job cancellation and the in-app agent (both deferred).
- Real models chosen by anyone but the owner (D-032).

## 8. Character Production (V2)

Approved by the owner on 2026-11-06 (D-035). §1–§7 still apply unless this section says otherwise. The stages are defined in [v2/CHARACTER_WORKFLOW.md](v2/CHARACTER_WORKFLOW.md) and the tests in [v2/TEST_PLAN.md](v2/TEST_PLAN.md).

### 8.1 Goal

Give one local user a guided, approval-based way to turn a character idea into an approved 2D asset set that is ready for 3D. It follows the owner's seven-stage workflow and reuses the existing generation, jobs and Kaggle features.

The cost goal is **Lightweight Preview → Human Approval → Batch Production**: cheap previews until the design is right, then a single production batch per model in which the large model is loaded only once.

### 8.2 Scope

**In V2:**
- **Character Library:** create, rename, tag, search, filter and delete (D-038).
- **Character Workspace:** a fixed seven-node graph with an inspector; nodes can be moved (D-038).
- **Stage Detail:** one layout with seven configurations.
- **S1–S5 working end to end,** each with drafts, immutable revisions, an approval checklist, history and downstream staleness.
- **References:** image uploads and URL text.
- **Quick preview batches** in S3, the **production batch manifest** in S4, and production batch runs with per-task results and per-task retry in S5.
- **Frozen copies** of the approved S3 concept and S5 set.
- **S6 and S7 visible as `planned`**, read-only.

**Not in V2:**
- An eighth stage, custom stages, editable graphs, or node creation, deletion or connection.
- Image→3D, rigging, animation and Unity in S6/S7. Rigging stays excluded from the product (§7).
- Any AI assistant or agent. The S2 guided questions are static text (DF-10).
- Multi-user review, comments by other people, or accounts. Prototype "reviewers" become the owner's own notes.
- Automatic similarity, "consistency" or "prompt adherence" scores. No such metric exists.
- Fetching Pinterest or other URLs, thumbnails or pin counts.
- Export packages and forks (OD-04).
- Local preview inference (planned, OD-09). LoRA or trigger-token management.
- A new database, scheduler, queue, compute system or job states.
- Running the two T4s as one GPU.

### 8.3 User stories

| ID | As the owner, I want to… | So that… |
|---|---|---|
| US-1 | create a character and find it again by name, tag, stage or status | I can manage several characters |
| US-2 | see all seven stages, their status and what blocks each one, on one canvas | I know what to do next |
| US-3 | collect references with what I like and what not to copy, plus notes and a sketch | the spec is based on my intent |
| US-4 | answer guided questions and mark every attribute Locked, Preferred or Flexible | the identity stays fixed later |
| US-5 | make quick, cheap previews with a light model, compare them with the spec, revise and pick one | I validate the look before spending GPU time |
| US-6 | write canonical and model-specific prompts and review the production task list with its model loads, time and quota fit | the production run is predictable |
| US-7 | submit one production batch, watch the real job status, and see each task's result and error | a long run is efficient and transparent |
| US-8 | retry only the failed tasks | finished images are never regenerated |
| US-9 | approve the whole 2D set, multiview first, as one decision | S6 receives a consistent set |
| US-10 | change an approved stage without losing the old approval, and see which later stages need review | revisions are safe |
| US-11 | keep approved images even if I delete the jobs that made them | approvals are durable |

### 8.4 Functional requirements

| ID | Requirement |
|---|---|
| FR-C1 | Characters have an immutable `character_id`. The name, summary, tags and cover can change |
| FR-C2 | The library lists characters with their current stage, approved count and per-stage status, and supports search and filters |
| FR-C3 | Exactly seven stages in a fixed order and dependency graph, served by the backend (`StageConfig`) |
| FR-C4 | Each stage has a draft (save at any time), immutable revisions (submit), and an owner decision (approve, request revision, withdraw) |
| FR-C5 | Approval requires the stage to be available, its hard dependencies approved and unchanged, every required checklist item checked, and its content rules met |
| FR-C6 | Approving an upstream revision keeps every downstream snapshot and flags the affected downstream stages as needing review. Nothing is deleted or regenerated |
| FR-C7 | `editorial_status`, `feature_availability` and job/task/batch statuses are separate fields |
| FR-C8 | References come from v1 uploads (copied into the character) or from URLs (stored as text, never fetched) |
| FR-C9 | S3 runs preview batches with a preview profile. Previews are labelled with their model and never presented as predicting the production model |
| FR-C10 | S4 approval freezes a batch manifest bound to the S2 and S4 revisions, listing its tasks, groups, expected model loads and estimate |
| FR-C11 | S5 submits the manifest as one v1 job per group, only while its revisions are current. The model loads once per job |
| FR-C12 | Per-task results, errors and provenance are stored; partial results are kept; retry covers failed and not-run tasks only |
| FR-C13 | S3 and S5 approval copy the selected images into the character (frozen assets), with provenance |
| FR-C14 | Optimistic concurrency on every write; a conflict never overwrites data |
| FR-C15 | S6 and S7 are visible, read-only and labelled *Planned* |
| FR-C16 | Selecting a node, opening its Stage Detail and going back keeps the same node selected |
| FR-C17 | Everything works in VI/EN and in all four themes (UI.md); new terms are added to the glossary |
| FR-C18 | A character can be deleted as a whole, after a confirmation, unless one of its batch attempts is running (D-038) |

### 8.5 Acceptance criteria (V2 done)

- AC-1: Every route and status in CONTRACTS §13 is implemented, and its fixtures validate on both sides.
- AC-2: A character can be taken from S1 to an approved S5 set in mock mode. The S5 set holds `full_body`, `front`, `side` and `back` (OD-03).
- AC-3: Re-approving S2 marks S3, S4 and S5 as `needs_revision`, and their frozen assets stay downloadable.
- AC-4: A production batch with several tasks for one model runs as one job with one model load. A partial failure keeps the finished images, and *Retry* creates a job with only the unfinished tasks.
- AC-5: Production cannot be submitted before S2 and S4 are approved, or after they were re-approved (`BATCH_MANIFEST_STALE`).
- AC-6: Deleting the source job of an approved image does not affect the approval or the frozen file.
- AC-7: No screen shows a number that is absent from a payload: no fake GPU, VRAM, progress or similarity values.
- AC-8: S6/S7 cannot be drafted or approved (`STAGE_NOT_AVAILABLE`).
- AC-9: Every v1 test still passes (V-01…V-20 included); v1 endpoints behave as before for non-batch jobs.
- AC-10: The owner signs off.

### 8.6 Non-functional additions

| ID | Requirement |
|---|---|
| NFR-V1 | Local API < 500 ms for every V2 read (≤ 100 characters, ≤ 60 tasks per manifest), excluding image transfer |
| NFR-V2 | No data loss on crash: atomic writes, exclusive-create revisions, append-only history |
| NFR-V3 | No GPU work without an explicit click; never more than one job per task group per click |
| NFR-V4 | Keyboard access to the canvas (focus, arrow-key selection, zoom keys); status never shown by colour alone |
