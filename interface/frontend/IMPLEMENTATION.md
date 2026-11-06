# M1 frontend implementation handoff

Implemented on 2026-11-06. Owner acceptance and the shared milestone status remain
with the owner/Claude Code. No backend, Models, Kaggle connector, `data/`, shared
contracts or `docs/` files were edited. No Git repository existed, so no branch,
rebase, commit or PR was created and DF-13 was not decided.

## Delivered behavior

- Four React screens with the Obsidian workstation shell, tool shelf, cyan active
  states, violet secondary accents, green status indicators and self-hosted Inter.
- Catalog-driven pipelines/categories; all five mock models; dynamic options and
  input controls from ModelCapabilities. Text → 3D remains planned and disabled.
- Real multi-image decoding/uploads, upload IDs, thumbnails and all six reference
  roles. Model changes retain uploads, prompt and options, flag incompatibilities,
  and disable Generate for errors. Unsupported options are retained, explained and
  excluded from that model's request as specified by CONTRACTS §8.3.
- Pure stages 2–7 validation, stable error codes/fields, warnings and deterministic
  per-device resource planning. Server/mock validation runs again before creation.
- Typed ApiClient, MockApiClient and HttpApiClient under `/api/v1`; no asset-library
  API was invented. Library items derive from completed jobs, with search/filter,
  inspection and actual downloads.
- Mock job creation, idempotency, per-profile serialization, documented transitions,
  history, cursor pagination, timeline, logs, retryable failures and terminal deletion.
  Progress remains null when unreported; no fabricated progress percentages appear.
- Valid PNG and embedded-texture GLB fixtures. Three.js GLTFLoader/OrbitControls
  provide orbit, zoom, pan, reset, camera presets, wireframe, keyboard controls,
  loading/error states and GPU-resource cleanup.
- Seven resource scenarios; auth/profile status, quota/reset unknowns, session
  estimates, CPU/RAM, GPU0/GPU1 independently, temperature, source, timestamp,
  freshness, stale/unavailable/not-applicable states and unsupported TPU telemetry.
- URL-based filters and resource scenarios, draft retention across navigation,
  reload warning, keyboard focus, skip link, reduced motion and responsive layouts.

## Created file manifest

All paths below are relative to `interface/frontend/` unless prefixed otherwise.

| Area | Created files |
|---|---|
| Entry/config | `package.json`, `package-lock.json`, `index.html`, `tsconfig.json`, `vite.config.ts`, `eslint.config.js`, `playwright.config.ts`, `.env.example`, `.gitignore` |
| Handoff | `README.md`, `IMPLEMENTATION.md` |
| Application | `src/App.tsx`, `src/main.tsx`, `src/styles/app.css` |
| API | `src/api/types.ts`, `client.ts`, `errors.ts`, `fixtures.ts`, `queries.ts`, `MockApiClient.ts`, `HttpApiClient.ts` |
| Shared UI | `src/components/ui.tsx`, `ArtifactPreview.tsx`, `GlbViewer.tsx` |
| Generate | `src/features/generate/Draft.tsx`, `GeneratePage.tsx`, `ComputeInspector.tsx`, `ImageInputs.tsx`, `ModelOptions.tsx` |
| Library | `src/features/library/LibraryPage.tsx` |
| Jobs | `src/features/jobs/JobsPage.tsx`, `JobDetail.tsx` |
| Resources | `src/features/resources/ResourcesPage.tsx` |
| Validation | `src/validation/validate.ts`, `planner.ts` |
| Unit/component tests | `src/validation/validate.test.ts`, `src/api/MockApiClient.test.ts`, `src/features/generate/GeneratePage.test.tsx`, `src/features/resources/ResourcesPage.test.tsx` |
| Browser tests | `tests/setup.ts`, `tests/e2e/studio.spec.ts` |
| Fixture generator | `tests/fixtures/generate_fixtures.py` |
| Contract fixtures | `tests/fixtures/contracts/catalog.json`, `models.json`, `profiles.json`, `snapshot.json`, `artifact-metadata.json` |
| Binary fixtures | `tests/fixtures/artifacts/mock.png`, `mock.glb` |
| Canonical design | Repository-root `design/stitch/DESIGN.md`, `HANDOFF.md`, `inventory.json`; `screens/{generate-studio,asset-library,jobs-logs,kaggle-resources}/{code.html,screen.png}` |

The frontend `.gitkeep` was preserved. Build outputs, dependencies, logs, browser
downloads, traces and screenshots are excluded by the frontend `.gitignore`.

## Every design cleanup action

1. Inspected all four original ZIPs before extracting. Each had three entries.
2. Created one canonical location at repository-root `design/stitch/`.
3. Extracted the following byte-identical HTML/screenshot pairs:

| Original file under `interface/frontend/` | Canonical screen under `design/stitch/screens/` | Final action |
|---|---|---|
| `stitch_ai_asset_studio.zip` | `generate-studio/code.html`, `generate-studio/screen.png` | ZIP removed after verification |
| `stitch_ai_asset_studio (1).zip` | `jobs-logs/code.html`, `jobs-logs/screen.png` | ZIP removed after verification |
| `stitch_ai_asset_studio (2).zip` | `kaggle-resources/code.html`, `kaggle-resources/screen.png` | ZIP removed after verification |
| `stitch_ai_asset_studio (3).zip` | `asset-library/code.html`, `asset-library/screen.png` | ZIP removed after verification |

4. Kept one DESIGN.md after confirming all four archived copies were identical.
5. Added `inventory.json` with original archive, HTML and screenshot SHA-256 hashes.
6. Added a HANDOFF.md provenance index; none was supplied in the original archives.
7. After application verification, rechecked each original archive's hash and all
   12 archived entries against the canonical files, then removed the four ZIPs.
   Every unique source HTML and screenshot remains. No unrelated file was removed.

## Design fidelity and review evidence

The original export screenshots are light-mode references. The implementation
consistently applies the approved dark Obsidian DESIGN.md tokens. It preserves
the navigation, compact shelf, three-pane generation hierarchy, central viewport,
right compute/options inspector, library cards, jobs/log inspection and resource
instruments. Layout stacks at tablet/mobile sizes instead of clipping controls.

The export's actual model names, speculative topology controls, multiple enabled
profiles, cancellation, invented telemetry and unsupported output formats were
not promoted into functional UI. Contracts v1.0 determine available behavior.

Inspected generated screenshots of all four screens at 1440, 1024 and 390 pixels.
Browser evidence is generated at `test-results/screenshots/` (12 PNGs, gitignored).
The simple box replaces the export's character illustration because D-016/M1
explicitly require a valid small textured-box fixture. It is labeled as a mock.

Reviewed against the freshly fetched Web Interface Guidelines. Final code checks:

```text
src/App.tsx:1 - pass: semantic navigation, landmarks, skip link, route title
src/components/GlbViewer.tsx:1 - pass: keyboard alternatives, named controls, failure state
src/features/generate/ImageInputs.tsx:1 - pass: labeled upload/roles, real decode errors
src/features/generate/GeneratePage.tsx:1 - pass: retained input errors and disabled invalid generation
src/features/jobs/JobDetail.tsx:1 - pass: named logs, terminal-delete confirmation, permitted retries
src/features/resources/ResourcesPage.tsx:1 - pass: labeled independent meters and provenance
src/styles/app.css:1 - pass: visible focus, dark native controls, reduced motion, responsive overflow checks
```

The user's explicit requirement to disable invalid Generate takes precedence over
the guideline's general preference to leave submit enabled until submission.
No full manual screen-reader or real touch-device certification is claimed.

## Actual final verification

Commands ran in `interface/frontend/`:

| Command | Result |
|---|---|
| `npm run fixtures` | Pass; reproducible 42,102-byte PNG and 2,044-byte GLB, five mock records and contract JSON |
| `npm run typecheck` | Pass; strict `tsc --noEmit` |
| `npm run lint` | Pass; ESLint with zero warnings |
| `npm test` | Pass; 53 tests across four files |
| `npm run build` | Pass; production output includes both actual fixture files and local fonts |
| `npx playwright install chromium` | Completed |
| `npm run test:e2e` | Pass; all 10 tests, 45.2 seconds in the final full run |
| `npm audit` | Pass; zero reported vulnerabilities |

V-01–V-07, V-09 and V-11–V-18/V-20 are pure validation tests. V-08 and V-10
are component tests; V-19 is a component test and a real-browser upload workflow.
Additional tests cover options, retention, unsupported inputs, navigation, planning,
schema errors, expiry, duplicate roles, lifecycle/idempotency/serialization, logs,
retry restrictions, pagination, binaries and HTTP request paths.

Browser tests compare canvas output after orbit, zoom, pan and reset; parse actual
downloaded PNG/GLB signatures; exercise both mock pipelines and all scenarios;
reject corrupt uploads; check keyboard/reduced motion; verify zero horizontal
page overflow; and run axe WCAG A/AA checks on four screens at three widths.
No violations were reported in those 12 automated screen/viewport checks.

Also ran `npm run preview -- --port 4173 --strictPort` and a separate headless
Playwright production smoke against the built output: all four routes, actual
GLB loading, PNG/GLB HTTP bytes, the direct `gpu_split` scenario, and no page errors.
The preview server is left available at http://127.0.0.1:4173 for review.

## Remaining limits

- M1 uses fixed artifacts and memory-only history/uploads/drafts. No real inference,
  Kaggle connectivity, persistent backend storage or real authentication exists.
- HttpApiClient has transport unit coverage; live M2 integration/Pydantic fixture
  validation is pending the separately owned backend.
- The production build reports the standard non-blocking chunk-size warning for
  the lazy-loaded Three.js core (519.39 kB minified; 131.77 kB gzip).
- DF-13/Git workflow, milestone documentation updates and owner signoff remain
  with the owner/Claude Code. No shared contract or deferred decision was changed.

Exact Windows run commands and workflow instructions are in [README.md](README.md).
