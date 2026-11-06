# Stitch V2 handoff — Character Production

> **Status: APPROVED by the owner on 2026-11-06 (D-035).** These exports are **design references, not source code**.
> Behaviour and data follow [docs/v2/CONTRACTS.md](../../../docs/v2/CONTRACTS.md); colours and wording follow
> [docs/UI.md](../../../docs/UI.md).

The exports were extracted unchanged from `interface/frontend/AI_Asset_Studio_V2_Stitch_11_Exports_Handoff.zip`. All
33 files match the SHA-256 values in [MANIFEST.json](MANIFEST.json). No HTML was executed. The 11 `DESIGN.md` files are
byte-identical copies.

## 1. 11 exports → 3 page templates

| Export | Template | Use |
|---|---|---|
| `01-character-library` | `CharacterLibraryPage` (`/characters`) | Layout of the summary strip, filters, card grid and the "new character" card |
| `05-workspace-canvas-a` | `CharacterWorkspacePage` (`/characters/:id`) | Candidate A, compared below |
| `08-workspace-inspector-b` | `CharacterWorkspacePage` | **Candidate B: chosen base** |
| `11-workspace-overview-c` | `CharacterWorkspacePage` | Candidate C, used for the identity header and inspector sections |
| `06-stage-s1-concept-exploration` | `StageDetailPage` with S1 content | Stage content reference |
| `03-stage-s2-character-specification` | `StageDetailPage` with S2 content | Stage content reference |
| `09-stage-s3-concept-validation` | `StageDetailPage` with S3 content | Stage content reference |
| `07-stage-s4-prompt-engineering` | `StageDetailPage` with S4 content | Stage content reference |
| `02-stage-s5-2d-production` | `StageDetailPage` with S5 content | Stage content reference |
| `04-stage-s6-3d-planned` | `StageDetailPage` with S6 content (planned) | Read-only planned view |
| `10-stage-s7-rigging-planned` | `StageDetailPage` with S7 content (planned) | Read-only planned view |

## 2. Workspace: A vs B vs C

| | A (canvas) | B (canvas + inspector) | C (overview) |
|---|---|---|---|
| Graph | 7 nodes in 3 rows; ports barely visible | 7 nodes; **visible INPUT/OUTPUT ports**; pan tool, zoom, fit view | **Horizontal stepper, not a node canvas** |
| Inspector | Objective, inputs, multiview list, checklist, blocker, actions | Same as A, plus **numbered sections** (1 inputs, 2 multiview, 3 checklist) and a node history strip | Objective, inputs, outputs, checklist, blocker; the clearest section labels |
| Header | Compact breadcrumb + progress | Same as A | **Large identity card** with portrait and summary tiles |
| Problems | Fake telemetry footer, P100, worker node card | Same fake footer, worker node card, "ComfyUI engine" label | Fake GPU session ring, LoRA config, % renders |

**Chosen:** B as the base (the canvas with ports, pan, zoom and fit view, plus the numbered inspector). It takes from
C a **compact** identity header (name, tags, cover, approved count, current stage) and C's inspector section order
(objective → inputs → outputs → checklist → blockers → actions). Nothing else from C: its stepper does not meet the
node-canvas requirement, and its large hero card takes space from the graph. A and C stay only as archived references.

Merged Workspace, top to bottom: breadcrumb · `CharacterIdentityHeader` · `WorkflowCanvas` (left, with the toolbar
*zoom in / zoom out / fit view / pan*) · `FlowInspector` (right).

## 3. Stage Detail shared layout (common to exports 02, 03, 04, 06, 07, 09, 10)

- **Header:** breadcrumb (Character Production › name › stage), status chip, the source → current → target chain, and
  actions *Back to workspace* · *Save draft* · *Submit* · *Approve* · *Next stage*.
- **Left, `StageInputZone`:** read-only upstream inputs.
- **Centre, `StageWorkingArea`:** the stage editor.
- **Right, `StageApprovalZone`:** objective, gate checklist, blockers, history.

## 4. Stage content references

| Stage | Keep from the export | Replace or remove |
|---|---|---|
| S1 (06) | Idea card with tags; URL sources list; reference classification (face, hair, body, outfit, accessories, palette); sketch + notes area; moodboard cards with "why chosen"; direction notes; gate checklist; palette swatches | Pin counts, board previews and other fetched data (URLs are never fetched); "Creative Lead" approver; the "S3 Base Generation & LoRA" stage names in the side list (use the real stage names) |
| S2 (03) | Three spec sections (identity, outfit/details, personality); Guided Q&A tab with a progress count; Spec sheet tab; draft history; "Lock spec" action | "Open JSON spec" as a file (use the revision view); locked traits as Pantone codes (palette is hex only) |
| S3 (09) | S2 locked spec next to the candidates; S1 moodboard context; reviewer-notes area (the owner's notes); version history; candidate list with *approved / candidate*; approve + hand-off | Candidate percentages (96 %, 84 %, 79 %): no score exists. Add the **preview batch** controls (*Generate Quick Preview*, *Preview Gallery*, *Compare Candidates*, *Revise Prompt*) |
| S4 (07) | S2 spec input; S3 key visual; purpose tabs (Full-body, Portrait, Key Visual, Multiview, Chibi); canonical prompt; model-specific prompt; negative prompt; *Copy model prompt*; *Diff compare*; version history; hand-off; *Open Generate Studio* | Trigger tokens, LoRA weights, "prompt sensitivity 0.94", "4/4 test renders > 95 %", the "77 tokens" limit text (token limits depend on the model). Add the **Production Task List**, **Review Batch Manifest** (model loads, estimate, plan fit) and **Ready for Production** |
| S5 (02) | Target identity card; approved prompt input; multiview cards (front / side 3/4 / back) with seed and size; zoom; S5 gate checklist; blocker banner; history & notes; save / approve set | Face-Lock, ArcFace score, "prompt adherence 93.8 %", the height-delta "consistency" chart, LoRA stack, EXR pack, "Mana Pipeline Agent" messages, Kaggle P100 node card, elapsed-time bars that are not from the job. Add **Submit Production Batch**, **Batch Job Status** (v1 status only), **Per-task Results** and **Retry Failed Tasks** |
| S6 (04) | "Handoff data from S5" (the frozen S5 set); objective; responsibility rule (S6 never edits S5); *Request S5 revision* | Mesh target specs, "Blender/NeRF", topology wireframe simulation, GPU notification subscription, Blender download pack: everything is read-only and *Planned* |
| S7 (10) | Objective and future checklist | "Pipeline configuration", humanoid skeleton / 52 blendshapes / SpringBone / FBX/VRM specs: shown only as *Planned* text |
| Library (01) | Summary strip, search, style/stage/status filters, grid/list toggle, card with stage chip and progress segments, "new character" card | "V2.4 PRO", "Tokyo Engine", "Mana Core", style templates ("Xianzhou / Genshin"), "LoRA + Multi-ControlNet", "Tạo Slot Trống", star ratings, demo cards and IDs |

## 5. What the prototypes show that is not real

Do not implement any of these as working features. Values not backed by a payload must not appear.

- **Telemetry and compute:**
  - the footer "Latency 24 ms · Memory cache · GPU quota" bar;
  - the "Environment: Sandbox V2 / Mana Engine 4.8 GFLOPS" card;
  - "Worker Node Kaggle P100" cards, GPU temperature, load and VRAM tiles;
  - "Kaggle T4x2 / P100": P100 is not offered (D-031).
  Quota and session data live on the existing Resources page.
- **Models and training:** LoRA stacks, trigger tokens, fine-tunes, "Tokyo Anime Engine", ControlNet, Face-Lock.
- **Scores:** similarity, consistency, adherence and "sensitivity" percentages.
- **People:** "Senior Artist", "Tech Lead", "Creative Lead", reviewer avatars, AI agent messages. V2 has one user and
  no agent.
- **Actions out of scope:** Fork, Export Character Package, EXR packs, GPU notifications, auto-sync with Kaggle Hub,
  version tags such as `v2.3-release` and branch names.
- **Demo data:** every character name, ID (`#CHR-0042` …), image, timestamp and count.
- **Navigation:** the sidebar sub-items "Character Workspace" and "Stage Detail" need a character, so the sidebar gets
  a single **Characters** entry.

## 6. Technical notes for Codex

- **Dependencies in the HTML:**
  - `cdn.tailwindcss.com` (Tailwind via CDN, plus plugins in 08);
  - Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`);
  - images from `lh3.googleusercontent.com`;
  - 2–3 inline scripts per file.
  None of these is used in the app: styling comes from the existing CSS and tokens, the fonts from the local
  `@fontsource/inter`, and the images from the API. The licences of the demo images are unknown, so they are never
  copied into the repository.
- **Colours:** the Stitch `DESIGN.md` defines its own "Atelier Latte & Matcha" palette, including a purple accent.
  [UI.md](../../../docs/UI.md) §1–§4 (22 tokens, the four themes Latte/Caffe/Mint/Matcha) take precedence. Map the
  Stitch roles to existing tokens; do not add colours outside the token blocks.
- **Typography, spacing and radii:** follow `design/stitch/DESIGN.md` (v1) and the v2 `DESIGN.md` where they agree.
- **Interactions:** the HTML prototypes' buttons do not call any API. Wire real behaviour only to the routes in
  CONTRACTS §6. Anything else stays disabled and labelled **DEMO** or **Planned**.
