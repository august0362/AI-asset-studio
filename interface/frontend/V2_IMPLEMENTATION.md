# Character Production V2 — frontend implementation

Approved scope: [D-035](../../docs/DECISIONS.md), [V2 contracts](../../docs/CONTRACTS.md#13-character-production-v11), [Stitch handoff](../../design/stitch/v2/HANDOFF.md).

## Implemented

Exactly three page templates share the existing app navigation, React Query cache, theme, i18n and v1 job/artifact APIs:

- `/characters`: `CharacterLibraryPage`. Search by name/ID/tag, stage/status API filters, a style/tag filter over loaded results, grid/list cards, cover image, approved count, timestamps, create, rename and confirmed deletion from each row's actions disclosure.
- `/characters/:characterId`: `CharacterWorkspacePage`. Seven movable nodes, visible input/output ports, 10 dependency edges (7 hard / 3 soft), directional arrows, selected and stale edge styling, drag pan, wheel/keyboard zoom, fit view, reset layout and keyboard node selection. Selection lives in `?node=`; positions persist per character in localStorage. The identity header offers confirmed deletion. Every inspector reads its own stage detail and history.
- `/characters/:characterId/stages/:stageId`: one `StageDetailPage` shell, with input/working/approval columns in a 25/50/25 ratio and seven typed content renderers. S1 references/ideas/sketches; S2 specification and static guided questions; S3 previews, candidate comparison and linked images; S4 prompt purposes, model prompts, tasks and manifest review; S5 batch submission, results, retry and manual set approval; S6/S7 read-only planned views.

Shared components: `WorkflowCanvas`, `StageContentRenderer`, `StageInputs`, `StageFacts`, `EditorialStatus`, `History`, image previews/downloads, `ManifestReview`, `BatchControls` and a native dialog. Existing `ArtifactImage`, `DownloadButton`, `Status`, `Issues` and `PlanPanel` are reused. Job Detail shows all batch image artifacts with task IDs; the log panel supports keyboard scrolling.

Draft saves send the expected version. A 409 preserves text and offers an explicit reload. Background request failures keep the editor mounted. Unsaved draft text, invalid editor text, unfinished reference metadata and review notes trigger navigation/reload warnings. Saving a draft preserves an unfinished reference form. Returning to the workspace restores the selected node and focus.

## Stitch mapping and cleanup

Workspace B is the chosen canvas/inspector base. C contributes the compact identity header and inspector section order. A and C remain archived references. Stage exports map to content renderers, not separate pages.

All 33 original files across 11 exports matched `MANIFEST.json` before implementation. The design contact sheet is `test-results/v2-inspection/stitch-contact.png`. No exported HTML or CDN script is executed or copied into production. External demo artwork has unknown licensing and is not copied; images come from uploads, API artifacts or explicitly marked demo fixtures.

Inventory found no previously integrated V2 implementation, unreachable V2 route or duplicate V2 page to delete. **No files were deleted.** The original handoff ZIP, exports, V1 pages/tests and shared documents were retained. New production code contains only the three templates and shared components. No dependency was added, removed or upgraded.

## API and DEMO boundary

`characterTypes.ts` mirrors the approved V2 schemas. `ApiClient` gains all 19 character routes; `HttpCharacterApi` implements their methods, bodies, encoding, byte responses and error propagation. The v1 job types gain optional `request.batch` and `Artifact.task_id`; job statuses are unchanged.

`MockCharacterApi` is separate from the HTTP transport and selected through the existing `VITE_API_MODE=mock`. The UI clearly labels it DEMO. It stores character drafts, references, revisions, history and frozen PNGs in `aas.characters.demo.v1` in browser localStorage, with guarded reads/writes and an in-memory fallback. V1 mock jobs/uploads still reset on reload; an expired demo job is reported missing, while previously frozen image bytes remain available.

Demo batches use the existing mock job lifecycle, one job for the model group. Task results reference those jobs/artifacts. Successful results survive retries; only failed/not-run tasks are retried. Approval is explicit and frozen images are checksum-checked. None of this is presented as production inference or measured hardware activity. The production backend remains responsible for authoritative workflow rules, atomic storage, concurrency and batch execution.

### Character deletion and movable nodes (D-038)

`deleteCharacter(id)` sends route 19's DELETE without a request body and accepts 204 without attempting JSON parsing. The shared confirmation dialog names the character and explains permanent removal of references, revisions, approved images and history while Kaggle jobs remain in Jobs. Success invalidates the library, removes workspace/stage cache entries and `aas.canvas.<character_id>`, and navigates to `/characters`. A 409 preserves the dialog and layout and uses the existing VI/EN `BATCH_ATTEMPT_RUNNING` translations.

The mock rejects deletion when any manifest has a pending result with an attempt, returning all matching `details.manifest_ids` in a v1.1 envelope. Ready batches with no attempt do not block deletion. Deletion removes stored character data and request-index entries, retains v1 jobs, and records fixture deletions so bundled examples cannot reappear after reload. Previously open clients discard deleted records before saving another character. Storage accesses are guarded; in-memory deletion remains available when storage throws.

Node dragging uses pointer capture, converts viewport deltas by the current zoom, and suppresses selection only after actual movement. Background dragging pans independently; clicks and arrow-key selection remain available. Saved layouts validate all seven finite coordinate pairs; missing/corrupt/blocked storage uses the default. Reset layout restores defaults and fits the graph. Each SVG edge starts at the earlier stage's output and ends at the later stage's input; backward-facing layouts route around the nodes and approach the input from the left, including S5 → S6 → S7.

Changed for D-038: `src/api/{characterTypes,HttpCharacterApi,MockCharacterApi,CharacterApi.test,CharacterDeletion.test}.ts`; `src/features/characters/{CharacterLibraryPage,CharacterWorkspacePage,WorkflowCanvas,shared,DeleteCharacterDialog,DeleteCharacterDialog.test}.tsx`; `src/features/characters/{canvasLayout,canvasLayout.test}.ts`; `src/i18n/characters.{en,vi}.ts`; `src/styles/app.css`; `tests/e2e/d038.spec.ts`; this report. No backend, contracts, canonical docs or shared fixtures were edited.

### Backend v1.1 alignment (D-037)

The D-037 alignment covered routes 1–18 under CONTRACTS §13; D-038 adds route 19 above. Error envelopes accept `"1.0" | "1.1"`. Optional nullable `GenerationResult.request.batch` and `Artifact.task_id` remain supported; `ArtifactView` names the same artifact schema. Job Detail renders every batch image with its task ID. Both dictionaries already contain all 25 §13.7 codes; their coverage test now parses the canonical merged contract.

The shared pack grew from 31 to **32 JSON files** while Claude added `batch_jobs.json` (`list[GenerationResult]`) and matching PNG bytes. All 32 were copied unchanged, alongside the previously mapped `stage-configs.json`. No new fixture name or Python mapping was introduced by this frontend task. `src/api/characterFixtures.ts` provides typed cloned snapshots for every file, including request/error examples and batch-state variants. `MockCharacterApi` serves shared lists, workflows, stages, history, outputs, revisions and selectable batch scenarios; locally created characters retain the interactive demo engine. The complete shared character can also be edited after hydration. `MockApiClient` serves every shared attempt job. Twelve indexed content URLs resolve to the copied PNGs, bundled by Vite, with byte/size/SHA-256 parity tests and an exact inventory check that rejects orphan files. Every indexed URL is exercised through the appropriate mock content method, and all batch attempt `/status` responses are checked. Missing index entries or missing indexed binaries return 404 `ARTIFACT_NOT_FOUND`, without a placeholder fetch. Indexed responses use the MIME type recorded in the index. Locally created demo references and frozen assets retain their actual bytes.

After the backend generator reruns, copy all shared JSON and the entire `files/` tree together, retaining the frontend-only `stage-configs.json`. Never mix IDs or checksums from separate runs; the parity and orphan checks enforce this. No new fixture mapping is required for this follow-up.

The manifest preview ID `bat_000000000000` is never stored, selected for actions or linked. Preview tasks use padded `preview_01` IDs and the contract purpose/seed defaults.

Fixture coverage limitation: `character_workflow_in_progress.json` has only the S4 full stage-detail fixture. Opening its other stage editors reports the unavailable snapshot instead of fabricating missing draft/revision content. The complete character has all seven stage snapshots. Claude should supply additional mapped stage-detail fixtures if full browsing of the second example is required. No contract inconsistency was found.

A read-only live probe of `GET http://127.0.0.1:8000/api/v1/characters?limit=1` was refused because no server was listening. HTTP transport is covered by unit tests; no live batch or Kaggle job was run for this alignment task.

## Verification

Baseline: 332 Vitest tests in 10 files, TypeScript/build and ESLint passed.

| Final check | Result |
|---|---|
| `npm run typecheck` | Pass, 0 TypeScript errors |
| `npm run lint` | Pass, 0 errors / 0 warnings |
| `npm test` | Pass, 466 tests / 16 files (63 shared-fixture tests); includes VI/EN parity, deletion/storage conflicts and layout/edge tests |
| `npm run build` | Pass, 1740 transformed modules; 632.33 kB main and 519.39 kB Three.js chunks trigger Vite size warnings |
| `npm run test:e2e -- --workers=2 --output test-results/d038-regression` | Pass, 49 tests / 4.8 min (38 existing + 11 D-038), including all four themes and both locales |
| `npm run test:e2e -- tests/e2e/d038.spec.ts --grep 'library row deletion\|workspace identity deletion' --output test-results/d038-deletion-followup` | Pass, 2 tests after the additional cross-tab mock deletion cleanup |
| `npm test -- src/i18n/i18n.test.ts` | Pass, 8 tests / 1 file |
| `.venv/Scripts/python -m pytest tests/contract/test_contract_v2.py -q` (read-only, mock) | Pass, 72 tests |
| `npm run test:e2e -- tests/e2e/characters.spec.ts --grep 'shared backend\|production batch' --workers=2 --output test-results/v2-binary-fixtures` | Pass, 2 tests / 30.8 s after the strict missing-binary follow-up |
| Normalized `git diff --check` for frontend | Pass |

Unit tests include all 19 HTTP routes, body-free 204 handling, deletion conflicts with manifest IDs, retained batch jobs, deleted fixture and cross-tab persistence, API conflicts, draft persistence, two-tab versions, URL references without fetching, seven stages, planned write rejection, S1–S5 approvals/freezing/staleness, batch idempotency, task-only retry, dictionary/config checks and editor preservation. Existing validation/theme/language/profile tests remain enabled.

The browser suite includes the original 24 tests plus 14 V2 and 11 D-038 tests. V2 visual checks cover 9 views × 4 themes × 2 locales × 2 widths = 144 screenshot/axe/overflow combinations. D-038 adds dragging without pan, persistence/reset/corrupt layout recovery, edge endpoints/direction, both delete entry points, cancellation, refresh/reload and dialog/error/workspace axe checks in all four themes and both locales. Paths:

- `test-results/v2/{latte|mint|caffe|matcha}/{en|vi}/{library|workspace|stage-s1|…|stage-s7}-{1024|1440}.png`
- `test-results/v2/acceptance/s5-approved.png`
- `test-results/v2/acceptance/approved-demo.png` (downloaded PNG, signature checked)
- `test-results/v2/shared-fixtures/batch-job.png`
- `test-results/v2-contract-alignment/.last-run.json`
- `test-results/v2-binary-fixtures/.last-run.json`
- `test-results/d038/delete-{latte|mint|caffe|matcha}-{en|vi}.png` (8 dialog/error screenshots)
- `test-results/d038-regression/.last-run.json`
- `test-results/d038-deletion-followup/.last-run.json`

The frozen v1 `models.json` remains SHA-256 `8DB10EDBA07BC9CA5BAAE8191E3E9B70100AC24DBBA280A70D27B96E86D7F18F`.

## Test-server incident and safeguards

The first broad regression run reused port 5173 (`reuseExistingServer=true`). During that run the UI was serving HTTP mode and the backend reported Kaggle mode. Two regression POSTs reached the real backend and returned 201. This violated the task instruction not to run Kaggle jobs. The records were inspected, both were already completed, and no job data was deleted:

| Job | Model | Backend / accelerator | Recorded execution duration |
|---|---|---|---|
| `job_20261106T123042Z_cc00f8` | `mock-i3d-multiview` | Kaggle / `gpu_t4x2`, profile `sunny` | 35 s |
| `job_20261106T123106Z_11fb2e` | `mock-t2d-basic` | Kaggle / CPU, profile `sunny` | 35 s |

These are job durations from the API, not GPU quota measurements. Request/response evidence is preserved in `test-results/v2/acceptance/server-reuse-incident.json` and the failed run traces in `test-results/v2-regression/`.

The default browser suite now starts its own server on port **5179**, forces mock mode and refuses to reuse an existing server. A shared mock test fixture blocks every `/api/v1/` network request for all browser pages, including additional tabs. A regression test verifies this block. The opt-in HTTP suite keeps port 5173 and uses the original fixture. `AAS_E2E_PORT` can override the mock test port; URLs in mock specs are relative. The rerun uses these safeguards.

## Run locally

```powershell
cd interface/frontend
$env:VITE_API_MODE = 'mock'
npm run dev -- --port 5174 --strictPort
# Open http://127.0.0.1:5174/characters
```

For HTTP, use `VITE_API_MODE=http` and `VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1` on the approved UI port 5173 (which must be free). HTTP failures are shown; there is no automatic fallback to DEMO. Default browser tests use their isolated port automatically.

No staging, commit or push was performed. Backend, models, connector and canonical documents were not edited by this task.

## Files changed by this task

New: `src/api/{characterTypes,HttpCharacterApi,MockCharacterApi,CharacterApi.test,characterFixtures,CharacterFixtures.test}.ts`, `src/features/characters/` (the three templates, shared canvas/renderers/panels and UI tests), `src/i18n/characters.{en,vi}.ts`, `tests/fixtures/contracts/v2/` (shared JSON/PNG pack plus `stage-configs.json`), `tests/e2e/{characters.spec,mockTest}.ts`, and this report.

Updated: `src/App.tsx`, `src/api/{types,HttpApiClient,MockApiClient}.ts`, `src/i18n/{en,vi,i18n.test}.ts`, `src/styles/app.css`, `src/features/jobs/JobDetail.tsx`, both Playwright configs, the two existing mock browser specs (shared network-block fixture and relative URL), and `README.md`. Other pre-existing working-tree changes belong to earlier work or the other agent and were left in place.
