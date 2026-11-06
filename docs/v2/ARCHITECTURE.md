# V2 Architecture — Character Production

> **Status: APPROVED by the owner on 2026-11-06 (D-035).** It extends [docs/ARCHITECTURE.md](../ARCHITECTURE.md), which stays
> canonical for everything that exists.

## 1. Principles

- **Same modular monolith, same three business modules** (Interface, Models, Kaggle). Character Production is a
  **feature of Interface**: a backend package and a frontend feature folder. It is not a fourth module.
- **Reuse first.**
  - Jobs, uploads, validation, the resource planner, storage helpers and the Kaggle connector are used as they are.
  - A batch is a set of ordinary v1 jobs.
  - Character data references job data; it never copies it (an approved image is the one exception, §4.3).
- **No new infrastructure:** no database, broker, queue, scheduler, workflow engine, AI agent or compute system.
  Files under `data/` remain the only storage.
- **Honesty (NFR-3):** every number shown comes from a stored value or a v1 payload; there is no derived "AI score",
  no fake progress and no fake telemetry.

## 2. Boundaries and dependencies

```mermaid
flowchart LR
  subgraph Interface
    FE[frontend\nfeatures/characters] -- HTTP /api/v1 --> API[backend api/characters.py]
    API --> CS[backend characters/\nservice + store]
    CS --> JS[existing JobService\n+ validation + planner]
    CS --> UP[existing UploadStore]
    CS --> FS[(data/characters/)]
    JS --> JF[(data/jobs, inputs, outputs, logs)]
  end
  JS --> M[models\nregistry + adapters]
  JS --> K[kaggle_connector\nunchanged]
  K -- CLI --> KG[(Kaggle)]
```

| Part | Path | Owns | Must not |
|---|---|---|---|
| Character API | `interface/backend/aas_backend/api/characters.py` | The 18 routes (CONTRACTS §13.6), HTTP mapping | Contain workflow rules |
| Character service | `interface/backend/aas_backend/characters/` (`contracts.py`, `config.py`, `service.py`, `store.py`, `batches.py`) | Stage configs, drafts, revisions, approval rules, staleness, freezing, manifests, reconciliation | Call the Kaggle CLI; import `kaggle_connector`; change job records |
| Existing job service | `orchestrator/service.py` | Creates and runs jobs. Gains one internal entry point: create a job from a batch group | — |
| Models | `models/` | `GenerationRequest.tasks` (optional), batch support in `DiffusersTextTo2DAdapter` and its remote entrypoint | Know about characters or stages |
| Kaggle connector | `kaggle_connector/` | **No change** | — |
| Frontend | `interface/frontend/src/features/characters/` + `src/api/characterTypes.ts` | 3 page templates, the components in §6 | Touch files; compute statuses itself; invent metrics |

The character service may call the job service; the job service never imports the character service. A batch job
knows its `request.batch` reference, but job processing does not depend on it.

## 3. Components and integration

| V2 need | Implemented by | New code |
|---|---|---|
| Image references | `POST /uploads` (v1), then promotion into the character folder | Promotion (copy + JSON) |
| Concept candidates, production images | v1 jobs: Studio jobs linked by `job_id`, and batch jobs | `JobReference` resolution |
| Preview and production batches | One v1 job per task group | Manifest build, grouping, submit, reconcile |
| Option checks | v1 `check_option` and validation stages 2–7 | Per-task calls |
| Time and fit estimates | v1 resource planner (`required_seconds`, quota, session limit) | Per-group `estimated_runtime_seconds` |
| Status display | v1 `GET /jobs/{id}/status` | — |
| Atomic writes, path safety | v1 `atomic_write_json`, `safe_path`, ID regexes | New ID regexes |
| Themes, languages | UI.md tokens and i18n | New i18n keys only |

## 4. Storage

### 4.1 Layout

```
data/
├── characters/<character_id>/            # NEW. character_id is immutable; renaming changes character.json only
│   ├── character.json                    # Character
│   ├── history.jsonl                     # StageHistory, append-only
│   ├── stages/<stage_id>/
│   │   ├── draft.json                    # StageDraft (mutable, versioned)
│   │   ├── state.json                    # stored part of StageState: latest/pending/approved revision, last decision
│   │   └── revisions/<nnnn>.json         # StageRevision, immutable after creation (only decision fields change while pending)
│   ├── references/<reference_id>.<ext>   # promoted upload (png/jpg/webp)
│   ├── references/<reference_id>.json    # ReferenceAsset (url references have no file)
│   ├── assets/<asset_id>.png             # frozen approved image (S3, S5)
│   ├── assets/<asset_id>.json            # ArtifactReference
│   └── batches/<manifest_id>.json        # BatchManifest (tasks, groups, attempts, reconciled results)
├── inputs/  outputs/  jobs/  logs/       # v1, unchanged
```

### 4.2 Rules

- **IDs only.** Every path is built from validated IDs, roles and fixed names (`safe_path`, v1 §9). User text never
  becomes part of a path. Reference uploads are re-sniffed for their type from the bytes.
- **Atomic writes** use the existing temp-file + fsync + rename. **Revisions** are created with exclusive create, so
  they can never be overwritten. **History** is append-only; a torn last line is ignored on read.
- **One writer.** A per-character lock in the backend serializes writes. Optimistic versions (`version`,
  `draft_version`) detect stale browser tabs (CONTRACTS §13.5.1).
- **Job data is not duplicated.** Drafts, candidates and manifests store `job_id`/`artifact_id`. Jobs remain owned by
  the v1 job store and are deleted only by `DELETE /jobs/{id}`.
- **Approved data is protected.** Approval copies the selected images into `assets/` after checking their
  `sha256`. Nothing in V2 deletes a revision, a frozen asset or a referenced reference.
- **Startup:** like v1 jobs, no repair is needed. Staleness and batch status are derived on read; interrupted writes
  leave only temp files, which are swept.
- **Size:** a character with a full S5 set adds roughly the selected PNGs (a few MB each) plus small JSON files.

### 4.3 Why approved images are copied

`DELETE /jobs/{id}` (v1 §9) removes a job's outputs. Without the copy, an approved S3 concept or S5 set would vanish
when the owner cleans up jobs. Only **selected** images are copied, and only on approval.

## 5. Data flows

### 5.1 Draft → review → approval

```mermaid
sequenceDiagram
  participant UI as StageDetailPage
  participant API as /characters API
  participant S as CharacterService
  UI->>API: PUT draft (expected_draft_version)
  API->>S: validate schema + references, write draft.json
  UI->>API: POST decisions {submit}
  S->>S: create revisions/000N.json (source_revisions = current upstream approvals)
  UI->>API: POST decisions {approve, revision N}
  S->>S: check §5.2 (availability, upstream, checklist, content rules)
  S->>S: S3/S5: copy selected images → assets/; S4: freeze BatchManifest
  S-->>UI: StageDetail (downstream stages now report stale where affected)
```

### 5.2 Preview batch (S3) and production batch (S5)

```mermaid
sequenceDiagram
  participant UI
  participant S as CharacterService
  participant J as JobService (v1)
  participant A as Adapter + remote entry
  participant K as Kaggle connector (v1)
  UI->>S: POST batches {preview} or batches/{id}/submit
  S->>S: check approvals + manifest binding; group tasks by model
  loop one job per group
    S->>J: create job (request.batch, tasks)  — v1 validation + planner
    J->>K: submit one kernel (internet on for real models)
    K->>A: runner loads the model ONCE, renders tasks in order
    A-->>K: task_<id>.png + task_results.json (+ stops at the deadline)
    K-->>J: download → completed (BATCH_PARTIAL if needed) / failed
  end
  UI->>S: GET batches/{id} (when a job turns terminal)
  S->>J: read job records → reconcile TaskResult per task
```

The model is loaded once per job. Tasks that need another model form another group, and therefore another job.
`expected_model_loads` shows the total before submission.

### 5.3 Remote execution of a batch job

1. The runner (v1, unchanged) starts the adapter entrypoint once.
2. The entrypoint:
   1. installs the pinned libraries and downloads the pinned weights (D-032, D-034);
   2. for two-phase models, loads the text encoder, encodes **all** task prompts, then frees it;
   3. loads the image model once;
   4. for each task in order:
      - renders the image with its seed, size and options;
      - checks that the pixels are finite and not blank;
      - writes `task_<task_id>.png`, then appends to `task_results.json`;
      - records a task error and continues with the next task;
      - before starting the next task, checks `deadline_seconds` and marks every remaining task `not_run` if the
        budget is used up.
3. The job exits successfully if at least one task succeeded. Then `collect_outputs` maps each image to an artifact
   with its `task_id`.

One job uses one T4, and nothing assumes the two T4s form one larger GPU.

## 6. Frontend components

All components use the existing tokens (UI.md §2), i18n (UI.md §5–§9) and API client. None of them computes a status
the backend did not send.

| Component | Responsibility | Data | Notes |
|---|---|---|---|
| `CharacterLibraryPage` | `/characters`: search, filter by stage and status, grid/list, create | `GET /characters` | The summary counts (in progress, drafts, completed) come from the listed summaries only |
| `CharacterWorkspacePage` | `/characters/:id`: identity header, canvas, inspector | `GET /characters/{id}` | Reads/writes `?node=` |
| `CharacterIdentityHeader` | Name, tags, cover, approved count and current stage; actions: *Open stage*, *Open Generate Studio*, *Rename* | `Character`, `CharacterSummary` | No "fork", "export package" or engine badges (not in scope) |
| `WorkflowCanvas` | Draws the 7 fixed nodes and their edges. Pan (drag, or Space + drag), zoom (wheel, `+`/`-`), *fit view*. Arrow keys move the selection | `stages[]` | Default layout two rows (S1–S4, S5–S7); an edge always runs from the earlier stage's output port to the later stage's input port; the user can **drag nodes** to move them (D-038). Positions are a per-browser view preference in `localStorage` (key per character), never sent to the backend; *Reset layout* restores the default. Still no adding, removing or connecting nodes. Proposal: hand-written SVG + CSS transform, no new library (OD-11) |
| `WorkflowNode` | Stage number, title, `editorial_status` chip (text + icon, never colour alone), availability badge (`planned`), INPUT port (left) and OUTPUT port (right), the approved revision | `WorkflowStage` | Focusable, `aria-pressed` for the selection |
| `WorkflowEdge` | Curved connector from an OUTPUT port to an INPUT port: solid for a hard dependency, dashed for soft; highlighted when either end is selected; marked "stale" when the downstream end is stale | `StageConfig.dependencies`, `StageState.approved.stale_reasons` | |
| `FlowInspector` | For the selected node: objective, inputs (upstream revisions), outputs, checklist progress, blockers (as returned), stale reasons, history excerpt, and *Open Stage Detail* | `WorkflowStage` | Works for all 7 stages, including planned ones |
| `StageDetailPage` | `/characters/:id/stages/:stageId`: one shared layout | `GET …/stages/{stageId}` | The back link restores `?node=` |
| `StageContentRenderer` | Picks the content configuration by `stage_id` (S1…S7) | `StageDetail` | Seven configurations, one page |
| `StageInputZone` | Left column: read-only upstream inputs (`inputs[]`) and frozen assets | `StageInput[]` | |
| `StageWorkingArea` | Centre column: the stage's editor (S1 references and notes, S2 spec form and guided questions, S3 preview gallery and comparison, S4 prompt entries, task list and manifest review, S5 batch status, per-task results and selection; S6/S7 read-only planned view) | `draft.content`, `batches`, `resolved_jobs` | Saves with `expected_draft_version`; a 409 offers *Reload* |
| `StageApprovalZone` | Right column: objective, `ApprovalChecklist`, blockers, revisions, decisions (*Submit*, *Approve*, *Request revision*, *Withdraw*) | `config`, `state`, `revisions` | *Approve* is disabled while `blockers` is not empty, and the blockers are listed |
| `ApprovalChecklist` | Checklist items from `StageConfig.checklist`, with state from the draft | `ChecklistItemConfig[]`, `ApprovalChecklist` | Required items are marked |
| `AssetPreview` | Shows a reference, a job artifact or a frozen asset; zoom; provenance panel (model, revision, prompt, seed, size, sha256, job) | `ReferenceAsset`, `ResolvedJob`, `ArtifactReference` | Labels each image *preview*, *production* or *frozen* |
| `JobStatusCard` | One job: v1 status, progress (`null` → "Không rõ"), link to Jobs & logs | `GET /jobs/{id}/status` | Uses the existing status labels and polling |

**Batch controls**

| Stage | Control | Backed by |
|---|---|---|
| S3 | *Generate Quick Preview*, *Preview Gallery*, *Compare Candidates*, *Revise Prompt*, *Approve Concept* | Route 15; routes 6 and 7 |
| S4 | *Production Task List*, *Review Batch Manifest*, *Ready for Production* | `StageDetail.manifest_preview` and `resource_plans`; checklist item `manifest_reviewed`; route 7 |
| S5 | *Submit Production Batch*, *Batch Job Status*, *Per-task Results*, *Retry Failed Tasks*, *Final 2D Approval* | Routes 17, 16 and 18; v1 job status; routes 6 and 7 |

A control whose backend is not implemented yet is shown disabled with the label **DEMO** (prototype only) or
**Planned**. It is never shown as working.
