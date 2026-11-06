# CLAUDE.md — Claude Code context

**Current milestone: M0 (awaiting owner approval). Next: M1 Mock Frontend.** Status lives in [docs/MILESTONES.md](docs/MILESTONES.md).

## Your role

Architecture and documentation, implementation planning, system integration and debugging. Codex implements modules, writes tests and reviews code (see [AGENTS.md](AGENTS.md)).

## Canonical documents (read before changing anything)

1. [docs/CONTRACTS.md](docs/CONTRACTS.md): schemas, API, job states, validation, error codes. **Source of truth.**
2. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): modules, dependency rules, directory layout.
3. [docs/MILESTONES.md](docs/MILESTONES.md): scope and acceptance criteria per milestone.
4. [docs/DECISIONS.md](docs/DECISIONS.md): decisions, assumptions, deferred choices.
5. [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md): requirements (FR-/NFR- IDs).

Do not restate their content elsewhere. Link to them.

## Rules

- There are exactly three business modules: **Interface** (`interface/frontend`, `interface/backend`), **Models** (`models/`) and **Kaggle** (`kaggle_connector/`). Never add a fourth one.
- `models` and `kaggle_connector` never import each other or `interface`. Only the backend integrates them.
- Work only within the current milestone's scope. Anything listed as out of scope stays out.
- Contract changes follow CONTRACTS §12 and come first: docs, then fixtures, then code.
- Never select a real AI model before M4 or M5, and do so only through the process in MILESTONES.
- Kaggle: use the official CLI only. One authorized profile in M3. The user selects the profile explicitly. No account rotation, quota pooling or auto-failover (D-008).
- Never fabricate telemetry, quota or runtimes. Use `null` plus an explicit status.
- Secrets live only in `.env`. They never go into logs, `data/`, responses, notebooks or commits.
- Treat the `data/` folder as local and gitignored.
- A milestone is done only when its tests pass and the owner signs off.
- Do not edit files that Codex is working on. Coordinate through task assignment (AGENTS.md § Collaboration).

## Environment

Windows 11 dev machine, Python 3.13 available (target ≥ 3.11), Kaggle CLI 2.2.4 installed. Use `pathlib`, and store POSIX relative paths in metadata.
