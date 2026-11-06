# AI Asset Studio — frontend

React 18, strict TypeScript, Vite, React Router, TanStack Query and Three.js.
Behavior and types follow [CONTRACTS v1.0](../../docs/CONTRACTS.md). Colors, themes, languages and wording follow
[docs/UI.md](../../docs/UI.md). Layout and typography follow the design reference below.

## Run on Windows

The simplest way is `open.bat` in the repository root: it starts the backend and this UI (HTTP mode) and opens
http://127.0.0.1:5173. `open.bat mock` uses mock compute; `stop.bat` stops both.

To run the UI alone with the in-browser mock API (no backend, `.env`, Kaggle account or GPU needed), use
Node.js 22.12+:

```powershell
cd interface\frontend
npm ci
$env:VITE_API_MODE = 'mock'   # also the default when unset
npm run dev
```

To run it against a backend you started yourself (`.\.venv\Scripts\python -m aas_backend` from the root), set
`$env:VITE_API_MODE = 'http'` and `$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000/api/v1'` before `npm run dev`.
The backend accepts the origins http://127.0.0.1:5173 and http://localhost:5173.

## Try the workflows

- **Text → 2D:** enter a prompt and generate. The job advances through the documented states, then shows a PNG
  with a working download.
- **Image → 3D:** add images. Roles are assigned from the selected model's required/supported roles and can be
  changed. For a quick test, select `tests/fixtures/artifacts/mock.png` twice and assign front and side. Switch to
  Single Image→3D to see retained uploads flagged, then switch back to restore the compatible form.
- **Viewer:** drag to orbit, scroll to zoom, right-drag to pan. With the canvas focused: arrow keys orbit,
  Shift + arrows pan, +/- zoom. Camera presets, wireframe and reset are available. Without WebGL, download still works.
- **Library:** search by category, model or job ID, filter by category or format, inspect an asset or download it.
- **Jobs:** filter by state, inspect the timeline and logs, retry a retryable failure, or delete a finished job.
- **Resources:** auth, quota, session, CPU/RAM and **separate GPU0/GPU1** values, each group with its own source,
  timestamp and freshness. In mock API mode a menu offers the seven development scenarios.
- **Text → 3D:** visible but disabled while `planned`; its route reports `PIPELINE_NOT_AVAILABLE`.
- **Preferences:** the header has the theme mode (Light / Dark / System), the family (Coffee / Green) and the
  language (Tiếng Việt / English).

Prompts, uploads, roles and option values survive model changes and in-app navigation. Option values the next
model does not support are listed as retained and left out of its request (CONTRACTS §8.3). Unsupported prompts
and uploads stay visible, produce errors and block Generate.

## Behavior notes

- **Compute profile:** both Studio and Resources wait for `GET /compute/profiles` and select the first enabled
  profile; nothing is hard-coded. With no enabled profile they show an empty state and request no snapshot.
  Disabled profiles are listed but cannot be selected. A snapshot error stays next to the selector instead of
  replacing the page, and Generate stays disabled until a usable snapshot arrives. Resources accepts a
  `?profile=` override.
- **Errors:** messages are chosen by error `code` and filled from `details`; the code is shown small next to the
  text. An unknown code or a missing placeholder falls back to the backend's English message. All 59 codes in
  CONTRACTS §8.2 have Vietnamese entries.
- **Not translated:** backend log lines, model display names, identifiers, file names and user-entered text.
- **Themes:** the 22 tokens in four `:root[data-theme]` blocks in `src/styles/app.css` mirror UI.md §2. No hex
  values exist outside those blocks. The GLB viewer reads `--viewer-bg` and `--viewer-grid` and updates without
  reloading the model. An inline script in `index.html` applies the theme and language before the first paint.
- **V1 mock API mode:** jobs, uploads and generation drafts live in browser memory and reset on reload. Telemetry is labeled
  MOCK. Outputs are fixed fixtures that do not reflect the prompt: the GLB is a textured box.
- **Fixtures:** contract JSON fixtures in `tests/fixtures/contracts/` are also validated by the backend's pytest
  suite. `models.json` is frozen (SHA-256 `8DB10EDB…F18F`). `tests/fixtures/generate_fixtures.py` rebuilds
  `mock.png`/`mock.glb` using only the Python standard library.
- **Dependencies:** exact versions with a checked-in `package-lock.json`; one `minimatch` override pins the patched
  version used by the lint parser. The only build warning is the lazy-loaded Three.js chunk size (≈520 kB).

## Tests

```powershell
npm run typecheck        # tsc --noEmit
npm run lint             # ESLint, zero warnings
npm test                 # Vitest
npm run build
npx playwright install chromium
npm run test:e2e         # Playwright, mock API mode
npm run test:e2e:http    # Playwright against a running mock-compute backend
```

- **Vitest (374 tests):** validation V-01…V-20, the dynamic form, model switching, the plan panel and resource
  scenarios; both API clients; profile selection without a `default` profile; WCAG contrast recomputed for every
  token pair in UI.md (192 pairs) and doc/CSS/token parity; dictionary key parity, all error codes, fallbacks and
  storage that throws; and source checks for untranslated JSX and color literals.
- **Playwright, mock (37 tests):** every route in all four themes in Vietnamese (1024 and 1440 px) and English
  (1440 px) with axe and overflow checks; the bootstrap applying theme and language before React loads; real image
  decoding, GLB camera control and valid downloads; retry, scenarios, keyboard access and reduced motion; responsive
  checks at 1440 / 1024 / 390 px. Screenshots go to the gitignored `test-results/`.
- **Playwright, HTTP (4 tests):** start the backend in mock compute first (`$env:AAS_COMPUTE_MODE = 'mock'`), stop
  any running UI, then run `npm run test:e2e:http`. It starts Vite in HTTP mode on port 5173, never touches the
  backend, and skips if the backend is not reachable. It checks both pipelines with byte-exact PNG/GLB downloads,
  the full resource plan, a rejected request that creates no job, and the Resources view during and after a GPU
  job. Request/response records are saved under `test-results/http/`.

Automated axe checks are not a full assistive-technology audit.

## Design reference

`design/stitch/` holds the Stitch design exports: [DESIGN.md](../../design/stitch/DESIGN.md) (layout, typography,
spacing, components; its *Colors* section is replaced by UI.md) and one folder per screen under `screens/`
(`generate-studio`, `jobs-logs`, `kaggle-resources`, `asset-library`), each with `code.html` and `screen.png`.
`inventory.json` records the SHA-256 of the original archives and every extracted file. The exports are
references only: they use a light palette, include speculative features and model names, and their CDN scripts
are never executed. Contracts v1.0 decide application behavior.

## Character Production V2

The approved [V2 extension](../../docs/CONTRACTS.md#13-character-production-v11) adds three templates inside the existing app:
`/characters`, `/characters/:characterId`, and `/characters/:characterId/stages/:stageId`.
Workspace B is the canvas/inspector base, combined with C's compact identity header and inspector sections.
The seven-node graph has pan/zoom/fit, keyboard selection and stage-specific inspectors. One Stage Detail shell
renders S1–S7, with S6/S7 planned and read-only. All four themes and VI/EN remain available.

`VITE_API_MODE=mock` selects the explicitly labelled DEMO adapter. Character drafts, revisions, references and
frozen images are stored in browser localStorage (`aas.characters.demo.v1`), with an in-memory fallback if storage
is unavailable. Demo batches reuse the existing mock job lifecycle. V1 mock jobs still reset on reload.
`VITE_API_MODE=http` calls the approved 18 V2 routes and never silently falls back to DEMO. The backend implements these routes under contract v1.1. Shared backend-generated JSON and matching PNG bytes seed the DEMO adapter; newly created DEMO characters remain interactive. Fixture images resolve through `files/index.json`; unindexed fixture URLs return 404 `ARTIFACT_NOT_FOUND`. After backend fixture regeneration, replace the shared JSON and entire `files/` tree together (keep `stage-configs.json`); IDs and checksums must come from the same run.

The default browser suite starts a separate mock server on **5179**, refuses server reuse, and blocks backend API
network requests in every test context. `AAS_E2E_PORT` can override that port. The opt-in HTTP suite keeps 5173 and
must only target a backend configured for mock compute. V2 has dedicated transport, workflow and shared-fixture tests, including 144
route/theme/language/viewport screenshot/axe checks at 1024 and 1440 px.

Run a separate DEMO UI without replacing an existing server:

```powershell
$env:VITE_API_MODE = 'mock'
npm run dev -- --port 5174 --strictPort
# http://127.0.0.1:5174/characters
```

See [V2_IMPLEMENTATION.md](V2_IMPLEMENTATION.md) for changed files, cleanup inventory, API/backend dependencies,
exact verification results, screenshot paths, and the initial test-server reuse incident involving two Kaggle jobs.
No original design export was deleted and no app dependency was added.
