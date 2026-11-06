# Product Specification

This document covers what the product does and why. How it is built is defined in [CONTRACTS.md](CONTRACTS.md).

## 1. Goal and user

A local-first tool that turns prompts and 2D concept art into game assets. Inference runs as batch jobs on Kaggle, and all data stays on the user's machine. It serves **one local user** (a game developer) and has no multi-user accounts.

## 2. Pipelines

| Pipeline | Priority | Input → Output | Status |
|---|---|---|---|
| Text → 2D (`text_to_2d`) | First real AI pipeline (M4) | Prompt (+ style reference if the model supports it) → PNG | Mock until M3 |
| Image → 3D (`image_to_3d`) | Highest quality priority (M5) | One or more views (front, side, back…) → GLB with geometry and textures | Mock until M3 |
| Text → 3D (`text_to_3d`) | Last (M6) | Prompt → GLB | `planned`: visible but disabled |

**Image → 3D intent:** full-body characters first. The result should preserve identity, anatomy, silhouette, face, hair, outfit, colors and style as closely as the model allows. Perfect reconstruction is **never** promised, especially for regions the references do not show, and the UI says so next to the result.

## 3. Asset categories

- `character`: humanoid, full body preferred.
- `skill_effect`: **visual-only** concepts for skills (effects, auras, projectiles, props). Never gameplay logic.
- `weapon`: weapons, shields, tools.
- `companion`: pets, creatures, mounts.

Each model declares the categories it supports. No model is selected before M4.

## 4. Workflows

1. **Generate:** pipeline → category → model (filtered) → a form showing only the inputs that model accepts → prompt and/or images, each with a role → profile and accelerator (or Auto) → review errors, warnings and resource fit → Generate.
2. **Monitor:** status timeline, progress, logs, and live telemetry when available.
3. **Review:** PNG preview or an interactive GLB viewer, then download.
4. **History:** list, filter, reopen, retry (retryable failures only) and delete jobs.
5. **Resources:** profile health, quota, session and telemetry, before or during a job.

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

**Jobs and artifacts**

| ID | Requirement |
|---|---|
| FR-J1 | Create, list, view, retry (when retryable) and delete jobs |
| FR-J2 | Show status, the timeline, progress, logs and errors |
| FR-J3 | PNG inline preview, and GLB in a Three.js viewer (orbit, zoom, reset) |
| FR-J4 | Download each artifact as `<job_id>_<artifact_id>.<ext>` |
| FR-J5 | Jobs survive a backend restart |

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

## 6. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 Local-first | The backend binds to `127.0.0.1`. All data stays in `data/` |
| NFR-2 Secrets | Kaggle credentials never reach the frontend, logs, job files, notebooks or the repo |
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
- Selecting real models before the M4 and M5 benchmarks.
