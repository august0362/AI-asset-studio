# AI Asset Studio V2 — Google Stitch Design Handoff (11 exports)

## Scope
This is a **design reference archive**, not production source code. Do NOT put these exported `code.html` files directly in React `src/` and do not assume the HTML prototype's buttons perform real API calls.

**Exactly THREE production page templates**:
1. `CharacterLibraryPage` — `/characters`
2. `CharacterWorkspacePage` — `/characters/:character_id` — graph of 7 fixed sequential nodes plus `FlowInspector`
3. `StageDetailPage` — `/characters/:character_id/stages/:stage_id` — one reusable shell with 7 data/tool configurations.

11 exports = 1 Library + 3 versions of the SAME Workspace + S1..S7 stage content references. Not 11 React pages. No 4th business module, DB, generic workflow editor, or extra navigation.

## Mapping
| Folder | Source ZIP upload name | Purpose |
|---|---|---|
| `01-character-library/` | `stitch_character_studio_production_pipeline (1)(1).zip` | Library — Main template |
| `02-stage-s5-2d-production/` | `stitch_character_studio_production_pipeline (2)(1).zip` | Stage Detail S5 — Content variant |
| `03-stage-s2-character-specification/` | `stitch_character_studio_production_pipeline (3)(1).zip` | Stage Detail S2 — Content variant |
| `04-stage-s6-3d-planned/` | `stitch_character_studio_production_pipeline (4)(1).zip` | Stage Detail S6 — Content variant (PLANNED) |
| `05-workspace-canvas-a/` | `stitch_character_studio_production_pipeline (5)(1).zip` | Workspace candidate A — Compare, not extra page |
| `06-stage-s1-concept-exploration/` | `stitch_character_studio_production_pipeline (6)(1).zip` | Stage Detail S1 — Content variant |
| `07-stage-s4-prompt-engineering/` | `stitch_character_studio_production_pipeline (7)(1).zip` | Stage Detail S4 — Content variant |
| `08-workspace-inspector-b/` | `stitch_character_studio_production_pipeline (8)(1).zip` | Workspace candidate B — Compare inspector behavior |
| `09-stage-s3-concept-validation/` | `stitch_character_studio_production_pipeline (9).zip` | Stage Detail S3 — Content variant |
| `10-stage-s7-rigging-planned/` | `stitch_character_studio_production_pipeline (10).zip` | Stage Detail S7 — Content variant (PLANNED) |
| `11-workspace-overview-c/` | `stitch_character_studio_production_pipeline(1).zip` | Workspace candidate C — Compare, not extra page |

## Decision rules
- Claude: read existing repo docs and these designs; draft additive V2 docs/contracts, keep old `docs/CONTRACTS.md` unchanged; document any discrepancy instead of treating Stitch mock info as production truth. No code edits.
- Owner reviews docs and approves contract.
- Codex: use these files as references for styling, component behavior and visuals, but implement reusable typed React components and actual API adapters only after contract approval.
- Compare Workspace A/B/C and pick/merge the best node graph + inspector into ONE Workspace page; keep previous variants only as archived design references.
- Preserve Coffee (Latte/Caffe) and Green (Mint/Matcha) theme semantics and VI/EN support from the existing repo.
- `S6` and `S7`: planned until backend capability is verified. Job progress and hardware telemetry must not be invented. Prototype values, character names, IDs, status and mock artworks are DEMO unless verified by actual existing backend data.
- Some Stitch HTML references external fonts/images/framework CDNs and may contain placeholder interactions; inventory these dependencies and replace/handle as appropriate before integrating. Review asset licensing.
- All 7 S1..S7 content references exist here; do not request new Stitch screens merely because there are only 3 production page templates.

## Source and integrity
Each folder contains the exact `code.html`, `screen.png`, `DESIGN.md` extracted unchanged from its corresponding uploaded ZIP. The original ZIP filenames are retained in the table and manifest. No HTML was executed during extraction.
