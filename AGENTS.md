# AGENTS.md — shared context for Codex and Claude Code

**Current milestone: V2 Character Production (D-035, D-037). V2-0 done (contracts v1.1 = CONTRACTS §13, fixtures in `tests/fixtures/contracts/v2/`); V2-1 backend and V2-2 batch execution done (D-038; the live batch smoke run B-13 was not required); V2-3 Library + Workspace done (D-039); V2-4, V2-5 and the V2 Stitch UI refresh (D-039) by Codex. M0, M1, M2, M3 and M4 done (M4: Animagine XL 4.0, FLUX.2 [klein] 4B and MOSS-Image-SFT for `character`, D-034/D-036/D-037; weights download from the internet, D-032). M5 and M6 not started.** Status lives in [docs/MILESTONES.md](docs/MILESTONES.md).

This file is the single set of rules for both agents. Claude Code loads it through [CLAUDE.md](CLAUDE.md).

## Roles

- **Codex:** module implementation, tests, code review and bug fixing.
- **Claude Code:** architecture and documentation, implementation planning, system integration and debugging.

## Canonical documents (read before changing anything)

| Document | Purpose |
|---|---|
| [docs/CONTRACTS.md](docs/CONTRACTS.md) | **Source of truth**: schemas, endpoints, job states, validation rules, error codes. Implement it exactly: do not rename fields, add states or invent error codes |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Modules, dependency rules, directory layout, data flow |
| [docs/MILESTONES.md](docs/MILESTONES.md) | What to build now, its acceptance criteria and required tests |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Fixed decisions (D-xx), assumptions (A-xx) and open ones (DF-xx). Do not decide a DF-xx item yourself |
| [docs/PRODUCT_SPEC.md](docs/PRODUCT_SPEC.md) | Requirements (FR-/NFR- IDs; §8 Character Production) |
| [docs/UI.md](docs/UI.md) | Color tokens, the four themes, graphic design rules, Vietnamese/English rules and the glossary (use its terms exactly) |
| [docs/v2/CHARACTER_WORKFLOW.md](docs/v2/CHARACTER_WORKFLOW.md), [docs/v2/TEST_PLAN.md](docs/v2/TEST_PLAN.md) | Character Production: the seven stages, their gates and content rules; its test plan |

Do not restate their content elsewhere; link to them. If a contract is ambiguous or missing something, stop and raise it rather than guessing.

## Module boundaries

There are exactly three business modules. Never add a fourth one.

| Module | Path | May import |
|---|---|---|
| Interface: frontend | `interface/frontend/` | Backend REST API only |
| Interface: backend | `interface/backend/aas_backend/` | `models`, `kaggle_connector` |
| Models | `models/` | Standard library, pydantic, Pillow. A real model's remote entrypoint runs only in the notebook and may also import its pinned runtime libraries (torch, diffusers, …; D-034) |
| Kaggle | `kaggle_connector/` | Standard library, pydantic, the official `kaggle` CLI (subprocess); the notebook runtime may also use psutil and pynvml |

`models` and `kaggle_connector` never import each other or `interface`; only the backend integrates them. The frontend never handles Kaggle credentials or filesystem paths. The backend is the only writer of `data/`.

## Rules

- Work only within the current milestone's scope, and make only the changes the task needs. No unrelated refactors, renames, reformatting or dependency upgrades.
- Contract changes follow CONTRACTS §12 and come first: docs, then fixtures, then code. They go through Claude Code.
- Real AI models are chosen **only by the owner** (D-032), through the process in MILESTONES.
- Kaggle: official CLI only. One enabled profile; the user selects it explicitly. No account rotation, quota pooling or auto-failover (D-008).
- Never fabricate telemetry, quota, runtimes or metrics: use `null` plus an explicit status. Never silently drop inputs or options.
- Secrets live only in `.env`. They never go into logs, `data/`, API responses, notebooks or commits. Never commit `.env`, tokens, `kaggle.json` or anything under `data/`.
- Every behavior change ships with tests. The validation matrix (CONTRACTS §8.4, V-01…V-20) must keep passing.
- Default tests use mock mode (`AAS_COMPUTE_MODE=mock`, `VITE_API_MODE=mock`). Live Kaggle tests are marked `kaggle` and are opt-in. Every paid GPU run needs the owner's approval first.
- No Docker, queues, databases, multi-user auth, rigging or Unity work.
- A milestone is done only when its tests pass and the owner signs off.

## Collaboration

- **File ownership.** Codex: `interface/frontend/`, `design/stitch/`. Claude Code: `interface/backend/`, `models/`, `kaggle_connector/`, `tests/` (Python), `pyproject.toml`. Shared documents (`docs/`, this file, `README.md`) are changed only through Claude Code at the owner's direction.
- One agent per file at a time. Never edit files the other agent owns unless the owner says so for that task.
- Never run `git add -A`, commit or push automatically; the owner commits. The branch and PR workflow is still open (DF-13).

## Environment

Windows 11, Python 3.13 (target ≥ 3.11) in `.venv`, Node.js 22.12+, Kaggle CLI 2.2.4. Use `pathlib`, and store POSIX relative paths in metadata. `open.bat` starts the backend and UI in the background (`open.bat mock` for mock mode); `stop.bat` stops them.
