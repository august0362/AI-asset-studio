# AI Asset Studio

A local-first tool for generating game assets with AI. You choose a pipeline, an asset category and a model, then enter a prompt or upload reference images. The backend runs the job on Kaggle as a batch job, downloads the results and lets you preview and download them locally.

> **Status: M0 — Architecture & Documentation (awaiting approval).** There is no application code yet, and no AI model has been selected.

## Pipelines

| Pipeline | Output | Priority |
|---|---|---|
| Text → 2D | PNG | first real AI pipeline (M4) |
| Image → 3D | GLB (geometry + textures) | highest quality priority, full-body characters (M5) |
| Text → 3D | GLB | last (M6) |

Asset categories: **character, skill_effect** (visual concepts only), **weapon, companion**. Rigging, animation and engine integration are out of scope.

## Architecture

The project is a modular monolith with three business modules:

- **Interface**: React + TypeScript + Vite + Three.js frontend, and a FastAPI backend that owns orchestration, validation, storage and secrets.
- **Models**: versioned contracts, the capability registry, and adapters (mock first).
- **Kaggle** (`kaggle_connector/`): model-agnostic compute profiles, quota and telemetry, job submission, logs and artifacts.

Data stays on the local disk (`data/`, gitignored). The frontend never sees Kaggle credentials or the filesystem. Details are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Roadmap

M0 Docs → M1 Mock Frontend → M2 Model Contracts & Mock Adapters → M3 Kaggle Integration → M4 Text→2D → M5 Image→3D → M6 Text→3D. See [docs/MILESTONES.md](docs/MILESTONES.md).

## Documentation

| Document | Purpose |
|---|---|
| [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) | Goals, workflows, requirements, scope |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, boundaries, directory layout, data flow |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | **Canonical** schemas, API, job states, validation, errors |
| [docs/MILESTONES.md](docs/MILESTONES.md) | M0–M6 scope, acceptance criteria, tests |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions, assumptions, deferred choices |
| [CLAUDE.md](CLAUDE.md) / [AGENTS.md](AGENTS.md) | Context for the Claude Code and Codex agents |

## Configuration

Copy `.env.example` to `.env`. Use `AAS_COMPUTE_MODE=mock` until M3. Kaggle use follows Kaggle's Terms of Use: one account per person, with no account rotation or quota circumvention (see [D-008](docs/DECISIONS.md)).
