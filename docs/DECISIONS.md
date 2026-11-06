# Decisions

Short records. Format: **decision**, *why*. Add new entries at the end and never renumber them. Any contract-affecting entry also follows [CONTRACTS.md §12](CONTRACTS.md#12-contract-change-process).

## Architecture decisions

| ID | Decision | Why |
|---|---|---|
| D-001 | **Modular monolith with exactly three business modules: Interface, Models, Kaggle.** The frontend, backend and storage are separated inside Interface. | Small team, single local user. Clear boundaries without the operational cost of services. |
| D-002 | **The Kaggle module's Python package is `kaggle_connector/`**, not `kaggle/`. | A top-level `kaggle` package would shadow the official `kaggle` pip package and break the CLI/API. Approved by the owner on 2026-11-06. |
| D-003 | **CONTRACTS.md is canonical.** It is implemented as Pydantic v2 models in `models/contracts/` (with a JSON Schema export) and as hand-mirrored TS types. Shared JSON fixtures guard both sides. Version `1.0`: MINOR for additive changes, MAJOR plus `/api/v2` for breaking ones. | One source of truth that both agents can follow. Avoids codegen tooling in M1 before a backend exists. |
| D-004 | **Two-phase upload**: `POST /uploads`, then the job request references `upload_id`s. | Lets validation be re-run when the model changes without re-uploading files, and keeps uploads when the model changes (FR-G6). |
| D-005 | **Local filesystem + JSON metadata, atomic writes, no database.** | The MVP scale is a single user with a few hundred jobs. Files are easy to inspect. |
| D-006 | **One in-process worker thread per compute profile (concurrency 1). The frontend polls; no WebSockets.** | No broker needed. One active remote run per profile matches the single-session reality and simplifies status mapping. |
| D-007 | **Kaggle is accessed only through the official `kaggle` CLI, run as a subprocess** with the credentials placed in that process's env and an isolated `KAGGLE_CONFIG_DIR`. | Official tooling. Credentials never enter the global process env or files. Mocking is trivial. |
| D-008 | **Compute profiles and the Kaggle Terms of Use.** Kaggle's Terms of Use allow one account per person and prohibit operating multiple accounts. Rules: (1) a profile is one Kaggle account owned and operated by one person who has authorized its use (`authorization_confirmed: true` is required to enable it); (2) **M3 implements and enables exactly one profile**; (3) the user always selects the profile explicitly; (4) the system never selects, rotates or fails over between profiles, never pools or sums quota across profiles, and never resubmits a job on another profile; (5) automatic recommendation is limited to the accelerator **within** the selected profile. | Compliance and honesty. The owner has stated that three credentials exist and belong to three different people (A-02). Enabling more than one profile is deferred (DF-04). |
| D-009 | **Quota comes only from `kaggle quota --format json`** (CLI ≥ 2.2.1), cached for 5 minutes. Values are `null`/`unavailable` when it is missing or fails. Quota is never derived from assumed weekly limits. | Never fabricate (NFR-3). |
| D-010 | **Live CPU/RAM/GPU telemetry comes from a cooperating managed notebook**: a reporter thread (psutil + NVML, with an `nvidia-smi` fallback) prints `AAS_TELEMETRY` lines, which the connector reads with `kaggle kernels logs -f`. It is best-effort: it requires an executing notebook, may be delayed or missing, and batch logs are not a guaranteed real-time metrics service. GPU0 and GPU1 are reported independently. TPU metrics are `unsupported` in the MVP. | Standard status endpoints do not expose machine metrics. The log stream is the only official channel available. |
| D-011 | **Deterministic resource planner** (CONTRACTS §7): filter by accelerator kind, then check VRAM, session limit and quota with `safety_factor 1.5` and `overhead 600 s`. Errors block, warnings do not. | Explainable, testable, and not a scheduler. |
| D-012 | **Accelerator abstraction**: models declare `accelerator_kind`s (`cpu`/`gpu_cuda`/`tpu`) and VRAM. The Kaggle module's catalog maps `accelerator_id` → Kaggle `--accelerator` value, device count, VRAM and session limit. | Keeps Models independent of Kaggle and Kaggle independent of models. |
| D-013 | **Strict validation, no silent discard**: unknown fields and options are rejected. The backend is authoritative, and the frontend mirrors the same rules as pure functions. | FR-G4/FR-G5. One error code set across both sides. |
| D-014 | **Mock mode is first-class**: `MockApiClient` (frontend, M1) and `MockKaggleClient` (backend, M2), with the same contracts, state sequence, log and telemetry protocol, and configurable resource scenarios. | Every milestone up to M3 is testable without Kaggle or a GPU. |
| D-015 | **Retries**: at most 3 bounded in-job retries for transient remote reads and downloads. Submission is never retried automatically. A user retry creates a new job (`retry_of`). | Each run consumes quota, and failed jobs must stay auditable. |
| D-016 | **Mock GLB** comes from a small pure-Python glTF 2.0 binary writer (a colored box mesh with an embedded texture). The mock PNG is rendered with Pillow (prompt text + category color). | Real, previewable files without heavy 3D dependencies. |
| D-017 | **The Kaggle module adds `resources/` and `runtime/` sub-packages** next to `client/` and `jobs/`. | Quota, telemetry and planning, and the code that runs on Kaggle, have distinct responsibilities. They are still one module. |
| D-018 | **AI agents are development-time only**: Claude Code handles architecture, planning, integration and debugging, and Codex handles module implementation, tests, review and fixes. They share the docs and never edit the same files at the same time. Runtime agent features are deferred (DF-10) and would live inside Interface. | No fourth module. Avoids conflicting edits. |

## Assumptions

| ID | Assumption | Verified by |
|---|---|---|
| A-01 | One local user. The primary development machine is Windows 11, so code must be path-portable (`pathlib`, POSIX paths in metadata). | — |
| A-02 | The owner states that the three Kaggle credentials belong to three different people who each authorized their use (2026-11-06). The app cannot verify this. | Owner, per profile, before enabling it (DF-04) |
| A-03 | `kaggle quota [--format json]`, `kaggle kernels logs [-f]`, and `kaggle kernels push --accelerator --timeout` exist (checked with local `--help`, CLI 2.2.4, on 2026-11-06). Their output formats, latency and accepted values are **unverified**. | M3 spike |
| A-04 | Provisional limits: GPU/CPU session 12 h, TPU session 9 h; T4 = 15 GiB and P100 = 16 GiB VRAM per device; "T4 x2" has two devices. | M3 spike (DF-06) |
| A-05 | GPU quota is consumed by session wall time, not per device. | M3 spike |
| A-06 | Mock runtimes need only the Python standard library and Pillow, and no internet access. | M2 |

## Deferred decisions

| ID | Topic | Decide in | Constraint |
|---|---|---|---|
| DF-01 | Text→2D model(s) per asset category | M4 | Must declare a full `ModelCapabilities` and pass the contract tests |
| DF-02 | Image→3D model | M5 | Only after a benchmark on the same source concepts (multiview fidelity, geometry, textures, Kaggle fit) |
| DF-03 | Text→3D model | M6 | Only after M4 and M5 are stable |
| DF-04 | Enabling a 2nd or 3rd compute profile | After M3 | Each owner confirms authorization. D-008 rules still apply: explicit selection only, no rotation or pooling |
| DF-05 | Field mapping of `kaggle quota` JSON output (GPU/TPU total, used, reset) | M3 spike | Unmapped fields stay `null` |
| DF-06 | Accelerator catalog: Kaggle `--accelerator` values, VRAM, session limits, TPU type | M3 spike | Defaults stay provisional until verified |
| DF-07 | Viability of telemetry via `kernels logs -f`: latency, reliability, rate limits | M3 spike | Target: median sample latency ≤ 60 s. Otherwise live metrics are shown as `unavailable` during runs and the samples are shown after the run |
| DF-08 | Input dataset strategy (one versioned dataset per profile vs one per job), and cleanup | M3 spike | Private only |
| DF-09 | Job cancellation | After M3 | Must map to a Kaggle-supported action |
| DF-10 | In-app agent (error analysis, fix proposals) | After M6 | Inside Interface; opt-in; no fourth module |
| DF-11 | TPU telemetry mechanism | After M3 | `unsupported` until then |
| DF-12 | Hosting real model weights for Kaggle runs (Kaggle Models, datasets, or internet download) | M4 | Licensing reviewed per model |
| DF-13 | Initialize git, plus the branch and PR workflow | Before M1 | Required for the agent file-ownership rule in AGENTS.md |
