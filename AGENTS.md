# AGENTS.md — Codex context

**Current milestone: M0 (awaiting owner approval). Next: M1 Mock Frontend.** Status lives in [docs/MILESTONES.md](docs/MILESTONES.md).

## Your role

Module implementation, test generation, code review and bug fixing. Claude Code owns architecture, planning, integration and debugging (see [CLAUDE.md](CLAUDE.md)).

## Shared contracts (read before coding)

- [docs/CONTRACTS.md](docs/CONTRACTS.md): **source of truth** for every schema, endpoint, job state, validation rule and error code. Implement it exactly. Do not rename fields, add states or invent error codes.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): module boundaries and directory layout.
- [docs/MILESTONES.md](docs/MILESTONES.md): what to build now, its acceptance criteria and its required tests.
- [docs/DECISIONS.md](docs/DECISIONS.md): fixed decisions (D-xx) and open ones (DF-xx). Do not decide a DF-xx item yourself.

If a contract is ambiguous or missing something, stop and raise it in the task or PR rather than guessing.

## Module boundaries

| Module | Path | May import |
|---|---|---|
| Interface: frontend | `interface/frontend/` | Backend REST API only |
| Interface: backend | `interface/backend/aas_backend/` | `models`, `kaggle_connector` |
| Models | `models/` | Standard library, pydantic, Pillow |
| Kaggle | `kaggle_connector/` | Standard library, pydantic, the official `kaggle` CLI (subprocess); the notebook runtime may also use psutil and pynvml |

The frontend never handles Kaggle credentials or filesystem paths. The backend is the only writer of `data/`.

## Rules

- Make only the changes the assigned task needs. No unrelated refactors, renames, reformatting or dependency upgrades.
- Every behavior change ships with tests. The validation matrix (CONTRACTS §8.4, V-01…V-20) must keep passing.
- Use mock mode (`AAS_COMPUTE_MODE=mock`, `VITE_API_MODE=mock`) for all default tests. Live Kaggle tests are marked `kaggle` and are opt-in.
- Never commit `.env`, tokens, `kaggle.json` or anything under `data/`.
- Never fabricate metrics. Never silently drop inputs or options.
- No Docker, queues, databases, multi-user auth, rigging or Unity work.

## Collaboration

- One agent per file at a time. Each task lists the files or directories it owns. Do not edit files outside that list.
- Use one branch per task. Rebase onto `main` before review. Claude Code integrates.
- Contract or doc changes go through Claude Code (CONTRACTS §12). Do not edit `docs/` in implementation tasks.
