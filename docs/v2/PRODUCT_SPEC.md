# V2 Product Specification — Character Production

> **Status: APPROVED by the owner on 2026-11-06 (D-035).** This extends [docs/PRODUCT_SPEC.md](../PRODUCT_SPEC.md). Its
> goals, non-functional requirements (NFR-1…8) and exclusions still apply unless this document says otherwise.

## 1. Goal

Give one local user a guided, approval-based way to turn a character idea into an approved 2D asset set that is ready
for 3D. It follows the owner's seven-stage workflow ([CHARACTER_WORKFLOW.md](CHARACTER_WORKFLOW.md)) and reuses the
existing generation, jobs and Kaggle features.

The cost goal is **Lightweight Preview → Human Approval → Batch Production**: cheap previews until the design is
right, then a single production batch per model in which the large model is loaded only once.

## 2. Scope

**In V2:**
- **Character Library:** create, rename, tag, search and filter.
- **Character Workspace:** a fixed seven-node graph with an inspector.
- **Stage Detail:** one layout with seven configurations.
- **S1–S5 working end to end,** each with drafts, immutable revisions, an approval checklist, history and downstream
  staleness.
- **References:** image uploads and URL text.
- **Quick preview batches** in S3, the **production batch manifest** in S4, and production batch runs with per-task
  results and per-task retry in S5.
- **Frozen copies** of the approved S3 concept and S5 set.
- **S6 and S7 visible as `planned`**, read-only.

**Not in V2 (non-goals):**
- An eighth stage, custom stages, editable graphs, or node creation, deletion or connection.
- Image→3D, rigging, animation and Unity in S6/S7. Rigging stays excluded from the product (PRODUCT_SPEC §7).
- Any AI assistant or agent. The S2 guided questions are static text (DF-10).
- Multi-user review, comments by other people, or accounts. Prototype "reviewers" become the owner's own notes.
- Automatic similarity, "consistency" or "prompt adherence" scores. No such metric exists.
- Fetching Pinterest or other URLs, thumbnails or pin counts.
- Export packages and forks (OD-04). Character deletion was added by the owner (D-038).
- Local preview inference (planned, OD-09). LoRA or trigger-token management.
- A new database, scheduler, queue, compute system or job states.
- Running the two T4s as one GPU.

## 3. User stories

| ID | As the owner, I want to… | So that… |
|---|---|---|
| US-1 | create a character and find it again by name, tag, stage or status | I can manage several characters |
| US-2 | see all seven stages, their status and what blocks each one, on one canvas | I know what to do next |
| US-3 | collect references with what I like and what not to copy, plus notes and a sketch | the spec is based on my intent |
| US-4 | answer guided questions and mark every attribute Locked, Preferred or Flexible | the identity stays fixed later |
| US-5 | make quick, cheap previews with a light model, compare them with the spec, revise and pick one | I validate the look before spending GPU time |
| US-6 | write canonical and model-specific prompts and review the production task list with its model loads, time and quota fit | the production run is predictable |
| US-7 | submit one production batch, watch the real job status, and see each task's result and error | a long run is efficient and transparent |
| US-8 | retry only the failed tasks | finished images are never regenerated |
| US-9 | approve the whole 2D set, multiview first, as one decision | S6 receives a consistent set |
| US-10 | change an approved stage without losing the old approval, and see which later stages need review | revisions are safe |
| US-11 | keep approved images even if I delete the jobs that made them | approvals are durable |

## 4. Functional requirements

| ID | Requirement |
|---|---|
| FR-C1 | Characters have an immutable `character_id`. The name, summary, tags and cover can change |
| FR-C2 | The library lists characters with their current stage, approved count and per-stage status, and supports search and filters |
| FR-C3 | Exactly seven stages in a fixed order and dependency graph, served by the backend (`StageConfig`) |
| FR-C4 | Each stage has a draft (save at any time), immutable revisions (submit), and an owner decision (approve, request revision, withdraw) |
| FR-C5 | Approval requires the stage to be available, its hard dependencies approved and unchanged, every required checklist item checked, and its content rules met |
| FR-C6 | Approving an upstream revision keeps every downstream snapshot and flags the affected downstream stages as needing review. Nothing is deleted or regenerated |
| FR-C7 | `editorial_status`, `feature_availability` and job/task/batch statuses are separate fields |
| FR-C8 | References come from v1 uploads (copied into the character) or from URLs (stored as text, never fetched) |
| FR-C9 | S3 runs preview batches with a preview profile. Previews are labelled with their model and never presented as predicting the production model |
| FR-C10 | S4 approval freezes a batch manifest bound to the S2 and S4 revisions, listing its tasks, groups, expected model loads and estimate |
| FR-C11 | S5 submits the manifest as one v1 job per group, only while its revisions are current. The model loads once per job |
| FR-C12 | Per-task results, errors and provenance are stored; partial results are kept; retry covers failed and not-run tasks only |
| FR-C13 | S3 and S5 approval copy the selected images into the character (frozen assets), with provenance |
| FR-C14 | Optimistic concurrency on every write; a conflict never overwrites data |
| FR-C15 | S6 and S7 are visible, read-only and labelled *Planned* |
| FR-C16 | Selecting a node, opening its Stage Detail and going back keeps the same node selected |
| FR-C17 | Everything works in VI/EN and in all four themes (UI.md); new terms are added to the glossary |

## 5. Acceptance criteria (V2 done)

- AC-1: Every route and status in CONTRACTS.md v1.1 is implemented, and its fixtures validate on both sides.
- AC-2: A character can be taken from S1 to an approved S5 set in mock mode. The S5 set holds `full_body`, `front`,
  `side` and `back` (OD-03).
- AC-3: Re-approving S2 marks S3, S4 and S5 as `needs_revision`, and their frozen assets stay downloadable.
- AC-4: A production batch with several tasks for one model runs as one job with one model load. A partial failure
  keeps the finished images, and *Retry* creates a job with only the unfinished tasks.
- AC-5: Production cannot be submitted before S2 and S4 are approved, or after they were re-approved
  (`BATCH_MANIFEST_STALE`).
- AC-6: Deleting the source job of an approved image does not affect the approval or the frozen file.
- AC-7: No screen shows a number that is absent from a payload: no fake GPU, VRAM, progress or similarity values.
- AC-8: S6/S7 cannot be drafted or approved (`STAGE_NOT_AVAILABLE`).
- AC-9: Every v1 test still passes (V-01…V-20 included); v1 endpoints behave as before for non-batch jobs.
- AC-10: The owner signs off.

## 6. Non-functional additions

| ID | Requirement |
|---|---|
| NFR-V1 | Local API < 500 ms for every V2 read (≤ 100 characters, ≤ 60 tasks per manifest), excluding image transfer |
| NFR-V2 | No data loss on crash: atomic writes, exclusive-create revisions, append-only history |
| NFR-V3 | No GPU work without an explicit click; never more than one job per task group per click |
| NFR-V4 | Keyboard access to the canvas (focus, arrow-key selection, zoom keys); status never shown by colour alone |
