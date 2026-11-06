# AI Asset Studio

A local-first tool for generating game assets with AI. You choose a pipeline (Text→2D, Image→3D, Text→3D), an asset category and a model, then enter a prompt or upload reference images. The backend runs the job on Kaggle as a batch job, downloads the results and lets you preview and download them locally. The UI is in Vietnamese or English, with four color themes.

**Status:** M0–M4 done: the full UI, the backend, real Kaggle runs on one profile and three real Text→2D models for characters. V2 Character Production (seven approved stages from idea to a 2D set): backend done, frontend in progress. Next: M5 Image→3D, M6 Text→3D. See [docs/MILESTONES.md](docs/MILESTONES.md).

## Run (Windows)

1. Once: create the Python environment (`python -m venv .venv`, then `.venv\Scripts\pip install -e .[dev]`) and copy `.env.example` to `.env`.
2. Double-click **`open.bat`**: it starts the backend and the UI in the background and opens http://127.0.0.1:5173. Use `open.bat mock` to run without Kaggle.
3. Double-click **`stop.bat`** to stop both.

Logs are in `%TEMP%\ai-asset-studio\`. Kaggle use follows Kaggle's Terms of Use: one account per person, no account rotation or quota circumvention ([D-008](docs/DECISIONS.md)).

## Documentation

| Document | Purpose |
|---|---|
| [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) | Goals, pipelines, categories, requirements, scope; §8 Character Production |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, boundaries, directory layout, data flow, Kaggle connector; §8 Character Production |
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | **Canonical** schemas, API, job states, validation, errors |
| [docs/UI.md](docs/UI.md) | Color themes, Vietnamese/English UI and glossary |
| [docs/MILESTONES.md](docs/MILESTONES.md) | M0–M6 and V2 scope, acceptance criteria, status |
| [docs/v2/](docs/v2/CHARACTER_WORKFLOW.md) | Character Production: the seven stages ([CHARACTER_WORKFLOW](docs/v2/CHARACTER_WORKFLOW.md)) and the [TEST_PLAN](docs/v2/TEST_PLAN.md) |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions, assumptions, open choices, Kaggle run log |
| [docs/sources/](docs/sources/) | The owner's source material: character workflow v1.0, M4 Prompt Book |
| [interface/frontend/README.md](interface/frontend/README.md) | Frontend: run, test, design reference |
| [AGENTS.md](AGENTS.md) / [CLAUDE.md](CLAUDE.md) | Rules for the Codex and Claude Code agents |
