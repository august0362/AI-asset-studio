# Architecture

This is a local-first **modular monolith** with exactly three business modules: **Interface**, **Models** and **Kaggle**.
Schemas are in [CONTRACTS.md](CONTRACTS.md). Rationale is in [DECISIONS.md](DECISIONS.md).

## 1. Modules

| Module | Path | Owns | Must not |
|---|---|---|---|
| Interface: frontend | `interface/frontend/` | UI, Three.js GLB preview, client-side validation (same rules as the backend), polling | Touch Kaggle, credentials or files; call anything except the REST API |
| Interface: backend | `interface/backend/aas_backend/` | FastAPI API, orchestration, authoritative validation, job lifecycle, worker, **all of `data/`**, config and secrets | Contain model-specific logic or Kaggle CLI calls |
| Models | `models/` | Contracts (Pydantic), capability registry, validation rules, adapters | Import `interface` or `kaggle_connector`; know about Kaggle, HTTP or storage |
| Kaggle | `kaggle_connector/` | Profiles, auth, quota, job packaging, submit/poll/logs/download, telemetry, resource planning, notebook runtime | Import `interface` or `models`; know about pipelines, categories or models |

- The package is named `kaggle_connector` so it does not shadow the official `kaggle` package (D-002).
- AI agents are development-time tools, not a module. Any future in-app agent would live inside Interface (DF-10).

### 1.1 Dependency rules

```mermaid
flowchart LR
    FE[interface/frontend] -- HTTP /api/v1 --> BE[interface/backend]
    BE --> M[models]
    BE --> K[kaggle_connector]
    K -- CLI subprocess --> KG[(Kaggle)]
    BE --> FS[(data/ local filesystem)]
    M -. no import .- K
```

- The backend is the only integration point. It maps `ModelInvocation` to `KaggleJobSpec`, and `ModelCapabilities.runtime` to `ResourceRequirements`.
- Third-party dependencies are limited to:
  - `models`: pydantic, Pillow
  - `kaggle_connector`: pydantic and the `kaggle` CLI; the notebook runtime may also use psutil and nvidia-ml-py
- An import-boundary test (M2) enforces these rules.

## 2. Directory structure

```
AI Asset Studio/
├── interface/
│   ├── frontend/src/            # M1: api/ (ApiClient, Http/Mock clients, types.ts), validation/,
│   │                            #     features/{generate,jobs,resources}/, components/ (GlbViewer, Gauge…)
│   └── backend/aas_backend/     # M2: api/, orchestrator/ (validation, worker, state machine), storage/, settings.py
├── models/
│   ├── contracts/               # M2: Pydantic schemas + JSON Schema export
│   ├── registry/                # M2: capability registry + validation stages 2–6
│   └── adapters/                # M2: mock_text_to_2d, mock_image_to_3d; M4+: real adapters
├── kaggle_connector/
│   ├── client/                  # ComputeClient protocol, MockKaggleClient (M2), KaggleCliClient (M3), auth env
│   ├── jobs/                    # packaging, submit, poll, logs, download
│   ├── resources/               # profiles, accelerator catalog, quota, telemetry parsing, planner
│   └── runtime/                 # runs INSIDE the notebook: runner, telemetry reporter, manifest (no backend imports)
├── data/                        # gitignored (CONTRACTS §9)
├── docs/
├── tests/{unit,integration,contract,fixtures/contracts}/
├── pyproject.toml               # M2: one Python project (models, kaggle_connector, aas_backend)
└── .env.example  .gitignore  CLAUDE.md  AGENTS.md  README.md
```

## 3. Technology

| Layer | Choice |
|---|---|
| Frontend | Node 20+, React 18, TypeScript strict, Vite, `three` (GLTFLoader, OrbitControls), TanStack Query, react-router, Vitest + Testing Library |
| Backend | Python 3.11+, FastAPI, uvicorn, pydantic v2, pydantic-settings, python-multipart, Pillow, pytest + httpx, ruff |
| Kaggle | Official `kaggle` CLI ≥ 2.2.1 (2.2.4 installed), run as a subprocess |
| Storage | Local files + JSON. No database |
| Execution | One in-process worker per profile (concurrency 1). No queue broker |

Exact versions are pinned when each package is created.

## 4. Runtime modes

- `AAS_COMPUTE_MODE=mock` selects `MockKaggleClient`. It runs the job package locally and produces the same status sequence, `AAS_*` log lines and manifest as Kaggle, with configurable quota and telemetry scenarios. It is used in M1 (frontend `VITE_API_MODE=mock` → `MockApiClient`), in M2, and in every automated test.
- `kaggle` selects `KaggleCliClient` (M3+).
- Contracts are identical in both modes. Only `/health.compute_mode` tells them apart.

## 5. Data flow

### 5.1 Generation job

```mermaid
sequenceDiagram
    participant FE as Frontend
    participant BE as Backend
    participant M as Models
    participant K as kaggle_connector
    participant KG as Kaggle
    FE->>BE: POST /uploads (each image) → UploadRecord
    FE->>FE: validate on every change (CONTRACTS §8)
    FE->>BE: POST /validate
    BE->>M: stages 2–6
    BE->>K: plan(requirements, selected profile, snapshot)
    BE-->>FE: ValidationReport + ResourcePlan
    FE->>BE: POST /jobs
    BE->>BE: re-validate, copy inputs, write job (created)
    BE->>M: build_invocation
    BE->>K: submit(KaggleJobSpec)
    K->>KG: upload inputs (uploading) → kernels push (queued)
    loop every 30 s
        K->>KG: kernels status / logs
    end
    K->>KG: kernels output → remote_raw (downloading)
    BE->>M: collect_outputs → Artifact[] (completed)
    FE->>BE: poll status, GET artifacts
```

### 5.2 Resource monitoring

```mermaid
flowchart LR
    Q[kaggle quota --format json] --> R[snapshot builder]
    S[kaggle kernels status] --> R
    L[kaggle kernels logs -f] --> P[telemetry parser] --> R
    R --> C[(memory cache + telemetry.jsonl)] --> API[GET /compute/profiles/:id/snapshot] --> V[Resources view]
```

Each snapshot group (quota, session, host, gpu) carries its own source, timestamp and freshness. Live metrics exist only while a cooperating notebook is running (DF-07).

## 6. Kaggle connector (M3)

| Concern | Design |
|---|---|
| Auth | One profile = one account. Credentials from `.env` go only into the subprocess env. Each profile gets an isolated, empty `KAGGLE_CONFIG_DIR`. Auth is checked with `kaggle quota` |
| Inputs | Image jobs: a private dataset version per profile (`<owner>/aas-inputs/<job_id>/`). Text-only jobs skip this step. Strategy to be confirmed (DF-08) |
| Submit | A generated private kernel (`kernel-metadata.json` + `runner.py`, which embeds the manifest, entrypoint and runtime, with no secrets) → `kaggle kernels push --accelerator --timeout` to `<owner>/aas-runner` |
| Poll | `kaggle kernels status` every 30 s, mapped to CONTRACTS §4 |
| Logs | `kaggle kernels logs -f` while running. `kaggle kernels logs` afterwards is authoritative. Lines are redacted before storage |
| Artifacts | `kaggle kernels output -p outputs/<job_id>/remote_raw` → manifest check → `collect_outputs` |
| Retries | CONTRACTS §4. Never auto-resubmit, never switch profile |
| Quota | `kaggle quota --format json`, cached for 5 min. Field mapping per DF-05. Old CLI or a failed call gives `null` + `unavailable` |
| Stance | Kaggle is a limited batch platform. No persistent sessions or real-time inference |

## 7. Frontend routes

- `/generate/{text-to-2d|image-to-3d|text-to-3d}`: category → model (filtered) → dynamic form built from `inputs` and `options_schema` → profile, accelerator (Auto or a compatible one) and ResourcePlan panel → Generate. Text→3D is visible but disabled while `planned`.
- `/jobs`, `/jobs/:jobId`: history, status timeline, logs, image or GLB preview, downloads.
- `/resources`: the Kaggle Resources view (FR-R1–FR-R8).

The validation module is pure (no React) and is tested against V-01…V-20.
