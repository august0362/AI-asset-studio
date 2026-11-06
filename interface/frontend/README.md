# AI Asset Studio — M1 mock frontend

React 18, strict TypeScript, Vite, React Router, TanStack Query and Three.js.
The visual reference is [the canonical Stitch handoff](../../design/stitch/HANDOFF.md).
Behavior and types follow [CONTRACTS v1.0](../../docs/CONTRACTS.md).

## Run on Windows

Use Node.js 22.12+ (Node 24 was used for verification). Python 3.11+ is only needed
to regenerate the checked-in deterministic fixtures.

```powershell
cd 'C:\Users\admin\Desktop\File All\Demo project\Project\AI Asset Studio\interface\frontend'
npm ci
$env:VITE_API_MODE = 'mock'
npm run dev
```

Open http://127.0.0.1:5173. No `.env` file, backend, Kaggle account or GPU is needed.
Mock is the default even when `VITE_API_MODE` is unset.

## Try the workflows

- **Text → 2D:** enter a prompt and generate. A mock job advances through the
  documented states, then shows an actual PNG with a working download.
- **Image → 3D:** add two or more images. Roles are assigned from the selected
  model's required/supported roles and can be changed. For a quick test, select
  `tests/fixtures/artifacts/mock.png` twice and assign front and side.
  The multiview fixture passes at 768 × 768. Switch to Single Image→3D to see
  retained uploads flagged, then switch back to restore the compatible form.
- **Viewer:** drag to orbit, scroll to zoom, right-drag to pan. Focus the canvas
  and use arrow keys to orbit, Shift + arrows to pan, +/- to zoom. Camera presets,
  wireframe and reset are available. If WebGL is unavailable, download still works.
- **Library:** completed jobs supply gallery items. Search category/model/job ID,
  filter category/format, inspect an asset or download its PNG/GLB.
- **Jobs:** filter states, inspect timeline and logs, retry the seeded retryable
  failure, or delete a terminal job after confirmation.
- **Resources:** select any of the seven development scenarios. Sources,
  timestamps and freshness appear independently per metric group; GPU0 and GPU1
  retain separate utilization, VRAM and temperature values.
- **Text → 3D:** visibly planned and disabled. Its direct route also reports
  `PIPELINE_NOT_AVAILABLE`.

Prompts, uploads, roles and option values survive model changes and in-app
navigation. Unsupported option values are listed as retained and omitted from
the next model's request, as CONTRACTS §8.3 specifies. Unsupported prompts and
uploads remain visible, produce errors and block Generate.

## Verification

```powershell
npm run fixtures
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:e2e
npm audit
```

The browser tests verify actual image decoding, valid downloaded bytes, GLB camera
changes, mock pipelines, retry, scenarios, keyboard access, reduced motion,
overflow and axe accessibility at 1440 / 1024 / 390 pixels. Screenshots are written
to the gitignored `test-results/screenshots/` directory. Automated axe checks are
not a complete assistive-technology audit.

To inspect the production build:

```powershell
npm run build
npm run preview
```

Open http://127.0.0.1:4173.

## M1 boundaries and handoff

- Jobs, uploads and drafts live in browser memory and reset on full reload.
  Reload/close warns when draft inputs exist. Durable backend storage belongs to M2.
- All telemetry is explicitly MOCK. No Kaggle connections, credentials, real models
  or inference are used. The five model records are the documented mock registry.
- Outputs are fixed fixtures; they do not represent the submitted prompt/options.
  PNG dimensions and GLB complexity are reported from the actual fixture metadata.
  The small GLB is a textured box, not a reconstructed character.
- `tests/fixtures/generate_fixtures.py` uses only Python's standard library for
  the M1 fixture deliverable. D-016's Pillow rendering applies to the M2 runtime.
  The GLB embeds a PNG texture and needs no external textures or CDN resources.
- Contract JSON fixtures live in `interface/frontend/tests/fixtures/contracts/`,
  within this task's ownership. They can be reused for M2's shared Pydantic checks;
  no backend/shared-root test files were changed.
- The HTTP transport implements the documented `/api/v1` endpoints. To opt in
  later, use `VITE_API_MODE=http` and `VITE_API_BASE_URL` from `.env.example`.
  It has transport unit tests; a real M2 backend has not been integrated/tested.
- Hardware limits are provisional mock values. Unspecified image size limits use
  the global limit; null dimension constraints impose no extra limit. The single
  image fixture rejects WebP per V-12. No actual model selection was made.
- One narrow `minimatch` override pins the patched version used by the lint parser.
  All direct dependencies are exact versions; `package-lock.json` is checked in.
- Git was not initialized in the supplied workspace. No branch/rebase/commit was
  performed, and DF-13 remains with the owner. Milestone status documents and
  owner signoff remain unchanged.

See [IMPLEMENTATION.md](IMPLEMENTATION.md) for the file manifest, cleanup and final results.
