import { act, render, screen, waitFor, within } from "@testing-library/react";
import { readFileSync, readdirSync } from "node:fs";
import ts from "typescript";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { api } from "../../api/client";
import { ApiError, issue } from "../../api/errors";
import { sharedCharacterFixture as fixture } from "../../api/characterFixtures";
import type { CharacterWorkflow, StageDetail, StageId } from "../../api/characterTypes";
import { createI18n } from "../../i18n/core";
function mount(path: string) {
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={cache}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return cache;
}
beforeEach(() => {
  localStorage.clear();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});
async function character() {
  return api.createCharacter({
    contract_version: "1.1",
    client_request_id: crypto.randomUUID(),
    name: "DEMO form test",
  });
}
function mountStage(detail: StageDetail, workflow: CharacterWorkflow = fixture("character_workflow")) {
  vi.spyOn(api, "stage").mockResolvedValue(detail);
  vi.spyOn(api, "character").mockResolvedValue(workflow);
  const image = new Blob([], { type: "image/png" });
  vi.spyOn(api, "artifactContent").mockResolvedValue(image);
  vi.spyOn(api, "assetContent").mockResolvedValue(image);
  vi.spyOn(api, "referenceContent").mockResolvedValue(image);
  return mount(`/characters/${detail.character.character_id}/stages/${detail.config.stage_id}`);
}
describe("V2 shared stage shell", () => {
  it.each<StageId>(["s1", "s2", "s3", "s4", "s5", "s6", "s7"])(
    "%s uses the shared zones, read-only inputs and authoritative approval blockers",
    async (sid) => {
      const detail = fixture(`stage_detail_${sid}`);
      detail.state.pending_revision = 1;
      detail.state.blockers = [issue("STAGE_CONTENT_INCOMPLETE", null, "Incomplete content", "error", { rule: "required_content" })];
      const cache = mountStage(detail);
      await screen.findByRole("heading", { level: 1, name: new RegExp(sid.toUpperCase()) });
      const inputs = document.querySelector(".character-inputs")!;
      expect(within(inputs as HTMLElement).getByRole("heading", { name: "Inputs & references", exact: true })).toBeVisible();
      expect(inputs.querySelectorAll("input,textarea,select")).toHaveLength(0);
      expect(document.querySelector(".character-working")).toBeVisible();
      expect(within(document.querySelector(".character-approval") as HTMLElement).getByText("STAGE_CONTENT_INCOMPLETE")).toBeVisible();
      expect(screen.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
      if (detail.config.availability === "available") {
        await act(async () => cache.setQueryData(
          ["character-stage", detail.character.character_id, sid],
          { ...detail, state: { ...detail.state, blockers: [] } },
        ));
        expect(screen.getByRole("button", { name: "Approve", exact: true })).toBeEnabled();
      }
      cache.clear();
    },
  );
  it("keeps an unfinished reference form after saving and warns before navigation", async () => {
    const c = await character(), cache = mount(`/characters/${c.character_id}/stages/s1`), user = userEvent.setup();
    await user.type(await screen.findByRole("textbox", { name: "Raw idea" }), "Saved idea");
    await user.type(screen.getByRole("textbox", { name: "Reference title" }), "Unsubmitted reference");
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByRole("status", { name: "" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled());
    expect(screen.getByRole("textbox", { name: "Reference title" })).toHaveValue("Unsubmitted reference");
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.click(screen.getByRole("link", { name: "Next stage" }));
    expect(confirm).toHaveBeenCalled();
    expect(screen.getByRole("textbox", { name: "Reference title" })).toHaveValue("Unsubmitted reference"); cache.clear();
  });
  it("preserves unsaved text after a background API failure", async () => {
    const c = await character(),
      cache = mount(`/characters/${c.character_id}/stages/s1`),
      user = userEvent.setup();
    const input = await screen.findByRole("textbox", {
      name: "Raw idea",
    });
    await user.type(input, "Keep my unsaved text");
    vi.spyOn(api, "stage").mockRejectedValue(
      new Error("Temporary API failure"),
    );
    await act(() =>
      cache.invalidateQueries({
        queryKey: ["character-stage", c.character_id, "s1"],
      }),
    );
    expect(await screen.findByText("Temporary API failure")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "Raw idea" })).toHaveValue(
      "Keep my unsaved text",
    );
    expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled();
    cache.clear();
  });
  it("sends the original draft version and keeps text when saving returns 409", async () => {
    const c = await character(),
      cache = mount(`/characters/${c.character_id}/stages/s1`),
      user = userEvent.setup();
    await user.type(
      await screen.findByRole("textbox", { name: "Raw idea" }),
      "Still here",
    );
    const save = vi.spyOn(api, "saveStage").mockRejectedValue(
      new ApiError(
        {
          contract_version: "1.1",
          errors: [
            issue("STAGE_DRAFT_CONFLICT", null, "Conflict", "error", {
              current_draft_version: 2,
            }),
          ],
          warnings: [],
        },
        409,
      ),
    );
    await user.click(screen.getByRole("button", { name: "Save draft" }));
    await screen.findByText("STAGE_DRAFT_CONFLICT");
    expect(save).toHaveBeenCalledWith(
      c.character_id,
      "s1",
      expect.objectContaining({
        expected_draft_version: 0,
        content: expect.objectContaining({ idea: "Still here" }),
      }),
    );
    expect(screen.getByRole("textbox", { name: "Raw idea" })).toHaveValue(
      "Still here",
    );
    expect(
      screen.getByRole("button", { name: "Reload latest data" }),
    ).toBeEnabled();
    const latest = await api.stage(c.character_id, "s1");
    latest.draft.draft_version = 2;
    if (latest.draft.content.stage_id === "s1") latest.draft.content.idea = "Latest saved idea";
    vi.spyOn(api, "stage").mockResolvedValue(latest);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.click(screen.getByRole("button", { name: "Reload latest data" }));
    expect(screen.getByRole("textbox", { name: "Raw idea" })).toHaveValue("Still here");
    confirm.mockReturnValue(true);
    await user.click(screen.getByRole("button", { name: "Reload latest data" }));
    await waitFor(() => expect(screen.getByRole("textbox", { name: "Raw idea" })).toHaveValue("Latest saved idea"));
    expect(screen.queryByText("STAGE_DRAFT_CONFLICT")).not.toBeInTheDocument();
    cache.clear();
  });
  it("does not silently save an invalid options editor", async () => {
    const c = await character(),
      cache = mount(`/characters/${c.character_id}/stages/s4`),
      user = userEvent.setup();
    await waitFor(() =>
      expect(
        screen
          .getByRole("combobox", { name: "Model" })
          .querySelector('option[value="mock-t2d-basic"]'),
      ).not.toBeNull(),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Model" }),
      "mock-t2d-basic",
    );
    const options = screen.getByRole("textbox", {
      name: "Options (JSON)",
    });
    await user.clear(options);
    await user.type(options, "invalid JSON");
    expect(screen.getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(await screen.findByRole("alert")).toBeVisible();
    await user.clear(options);
    await user.type(options, "{{}");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save draft" })).toBeEnabled(),
    );
    cache.clear();
  });
  it.each(["s6", "s7"])(
    "keeps %s read only and preserves existing navigation",
    async (sid) => {
      const c = await character(),
        cache = mount(`/characters/${c.character_id}/stages/${sid}`);
      await screen.findByRole("heading", {
        level: 1,
        name: new RegExp(sid.toUpperCase()),
      });
      for (const name of ["Save draft", "Submit for review", "Approve"])
        expect(screen.getByRole("button", { name })).toBeDisabled();
      for (const control of document.querySelectorAll<HTMLButtonElement | HTMLInputElement | HTMLTextAreaElement>(
        ".character-working button,.character-working input,.character-working textarea,.character-approval input,.character-approval textarea,.character-approval .character-actions button",
      )) expect(control.disabled).toBe(true);
      expect(document.querySelector(".character-planned")).toHaveTextContent("Planned · read only");
      // One labelled sidebar since D-039 (the icon shelf duplicate is gone).
      expect(
        screen.getAllByRole("link", { name: "Generate studio" }),
      ).toHaveLength(1);
      expect(
        screen.getByRole("link", { name: "Back to workspace" }),
      ).toHaveAttribute("href", `/characters/${c.character_id}?node=${sid}`);
      cache.clear();
    },
  );
});

describe("V2 preview and production gates", () => {
  it("keeps Quick Preview disabled with S2 blockers, then labels candidates with the payload model", async () => {
    const detail = fixture("stage_detail_s3");
    detail.inputs.find((i) => i.stage_id === "s2")!.revision = null;
    detail.state.blockers = [issue("STAGE_BLOCKED", "stage_id", "Approve S2", "error", { stage_id: "s2" })];
    const cache = mountStage(detail), create = vi.spyOn(api, "createPreviewBatch");
    await screen.findByText("STAGE_BLOCKED");
    expect(screen.getByRole("button", { name: "Generate Quick Preview" })).toBeDisabled();
    expect(document.querySelector(".character-gallery")).toHaveTextContent(`Model: ${detail.batches[0].target_model_id}`);
    const ready = fixture("stage_detail_s3");
    await act(async () => cache.setQueryData(["character-stage", detail.character.character_id, "s3"], ready));
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate Quick Preview" })).toBeEnabled());
    expect(create).not.toHaveBeenCalled();
    cache.clear();
  });

  it.each([null, 354])("renders S4 manifest tasks, loads, labelled estimate %s and fit from payload without linking its placeholder", async (seconds) => {
    const detail = fixture("stage_detail_s4"), batch = detail.manifest_preview!;
    batch.expected_model_loads = 3;
    batch.groups[0].estimated_runtime_seconds = seconds;
    detail.resource_plans[0].fit = "unknown";
    const cache = mountStage(detail);
    await screen.findByText("Expected model loads: 3");
    expect(screen.getByText(`Estimated time: ${createI18n("en").duration(seconds)}`, { exact: true })).toBeVisible();
    expect(document.querySelector('[data-fit="unknown"]')).toBeVisible();
    for (const task of batch.tasks) {
      expect(screen.getByText(new RegExp(`${task.task_id} ·`))).toHaveTextContent(`${task.width} × ${task.height}`);
    }
    expect(document.querySelector('a[href*="bat_000000000000"]')).toBeNull();
    cache.clear();
  });

  it.each(["current", "stale s2", "stale s4", "missing s2", "missing s4", "changed s2", "changed s4", "submitted"])(
    "S5 submit gate checks the current manifest and approvals: %s",
    async (scenario) => {
      const detail = fixture("stage_detail_s5"), workflow = fixture("character_workflow"), batch = fixture("batch_manifest_ready");
      detail.batches = [batch];
      for (const sid of ["s2", "s4"] as const) {
        const state = workflow.stages.find((s) => s.config.stage_id === sid)!.state;
        if (scenario === `stale ${sid}`) state.approved!.stale = true;
        if (scenario === `missing ${sid}`) state.approved = null;
        if (scenario === `changed ${sid}`) state.approved!.revision++;
      }
      if (scenario === "submitted") batch.status = "submitted";
      const cache = mountStage(detail, workflow), submit = vi.spyOn(api, "submitCharacterBatch");
      const button = await screen.findByRole("button", { name: "Submit production batch" });
      await waitFor(() => expect(screen.getByRole("combobox", { name: "Compute profile" })).toHaveValue("default"));
      if (scenario === "current") await waitFor(() => expect(button).toBeEnabled());
      else {
        expect(button).toBeDisabled();
        if (scenario !== "submitted") expect(await screen.findByText("Review S2 and S4 before production.")).toBeVisible();
      }
      expect(submit).not.toHaveBeenCalled();
      cache.clear();
    },
  );

  it.each<StageId>(["s3", "s5"])("%s retries the existing batch only when retryable IDs are provided", async (sid) => {
    const detail = fixture(`stage_detail_${sid}`), batch = fixture("batch_manifest_partially_completed");
    if (sid === "s3") batch.kind = "preview";
    detail.batches = [batch];
    const retry = vi.spyOn(api, "retryCharacterBatch").mockResolvedValue(batch),
      create = vi.spyOn(api, "createPreviewBatch"),
      submit = vi.spyOn(api, "submitCharacterBatch"),
      cache = mountStage(detail), user = userEvent.setup();
    const button = await screen.findByRole("button", { name: "Retry failed tasks" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await waitFor(() => expect(retry).toHaveBeenCalledWith(detail.character.character_id, batch.manifest_id, expect.objectContaining({ compute: { profile_id: "default", accelerator_id: "auto" } })));
    expect(create).not.toHaveBeenCalled();
    expect(submit).not.toHaveBeenCalled();
    await act(async () => cache.setQueryData(["character-stage", detail.character.character_id, sid], { ...detail, batches: [{ ...batch, retryable_task_ids: [] }] }));
    expect(screen.queryByRole("button", { name: "Retry failed tasks" })).not.toBeInTheDocument();
    cache.clear();
  });

  it("shows v1 job status, per-task errors and provenance without fabricating progress", async () => {
    const detail = fixture("stage_detail_s5"), batch = fixture("batch_manifest_partially_completed"),
      job = fixture("job_batch_partial");
    detail.batches = [batch];
    vi.spyOn(api, "jobStatus").mockResolvedValue({ ...job, status: "running", progress: { ...job.progress, percent: null, message: null } });
    const cache = mountStage(detail);
    await screen.findByText("Progress: Unknown");
    expect(screen.getByText("Running", { exact: true })).toBeVisible();
    expect(document.querySelector("progress[value]")).toBeNull();
    for (const result of batch.results) {
      const card = screen.getByRole("heading", { name: result.task_id, exact: true }).closest("article")!;
      expect(card).toHaveTextContent(createI18n("en").label("taskStatus", result.status));
      expect(card).toHaveTextContent(batch.target_model_id);
      if (result.error) expect(card).toHaveTextContent(result.error.code);
      const task = batch.tasks.find((t) => t.task_id === result.task_id)!;
      await userEvent.click(within(card).getByText("Provenance", { exact: true }));
      expect(card).toHaveTextContent(task.prompt);
      expect(card).toHaveTextContent(JSON.stringify(task.options));
      if (result.sha256) expect(card).toHaveTextContent(result.sha256);
      if (result.job_id) expect(within(card).getByRole("link", { name: result.job_id })).toHaveAttribute("href", `/jobs/${result.job_id}`);
    }
    const id = batch.attempts[0].job_id;
    vi.mocked(api.jobStatus).mockResolvedValue({ ...job, progress: { ...job.progress, percent: 37, message: null } });
    await act(() => cache.invalidateQueries({ queryKey: ["character-job-status", id] }));
    expect(await screen.findByText("Progress: 37%")).toBeVisible();
    cache.clear();
  });

  it("requires every S5 purpose before final approval", async () => {
    const original = fixture("stage_detail_s5"), id = original.character.character_id;
    if (original.draft.content.stage_id !== "s5") throw new Error("Expected S5 content");
    const complete = original.draft.content;
    const saved = await api.saveStage(id, "s5", {
      contract_version: "1.1", expected_draft_version: original.draft.draft_version,
      content: { ...complete, items: complete.items.filter((i) => i.purpose !== "back") },
      checklist: original.draft.checklist,
    });
    await api.decideStage(id, "s5", { contract_version: "1.1", expected_draft_version: saved.draft.draft_version, action: "submit", revision: null, note: null });
    const cache = mount(`/characters/${id}/stages/s5`);
    await screen.findByText("STAGE_CONTENT_INCOMPLETE");
    expect(screen.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
    expect(document.querySelector(".character-working")).toHaveTextContent("Multiview consistency requires manual review.");
    await userEvent.click(screen.getByRole("button", { name: "Withdraw review" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Submit for review" })).toBeEnabled());
    const latest = await api.stage(id, "s5");
    const restored = await api.saveStage(id, "s5", { contract_version: "1.1", expected_draft_version: latest.draft.draft_version, content: complete, checklist: latest.draft.checklist });
    await api.decideStage(id, "s5", { contract_version: "1.1", expected_draft_version: restored.draft.draft_version, action: "submit", revision: null, note: null });
    await act(() => cache.invalidateQueries({ queryKey: ["character-stage", id, "s5"] }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve", exact: true })).toBeEnabled());
    cache.clear();
  });
});

it("keeps character UI free of hard-coded telemetry, runtime estimates and similarity values (5.9)", () => {
  const root = "src/features/characters";
  for (const name of readdirSync(root).filter((name) => /\.tsx?$/.test(name) && !name.includes(".test."))) {
    const source = readFileSync(`${root}/${name}`, "utf8"), tree = ts.createSourceFile(name, source, ts.ScriptTarget.Latest, true);
    const violations: string[] = [];
    const visit = (node: ts.Node) => {
      if ((ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) &&
        /(?:\b(?:T4|P100|V100|A100|H100|RTX\s*\d+)\b|\d+(?:\.\d+)?\s*(?:%|GiB|GB|MiB|MB|°C|seconds?|minutes?|s\/image)\b|similarity\s*[:=]?\s*\d)/i.test(node.text)) violations.push(node.text);
      if (ts.isPropertyAssignment(node) && /^(?:percent|temperature_c|vram_gib|memory_total_gib|memory_used_gib|estimated_runtime_seconds|required_seconds|similarity|similarity_score)$/.test(node.name.getText(tree)) &&
        (ts.isNumericLiteral(node.initializer) || ts.isStringLiteral(node.initializer))) violations.push(node.getText(tree));
      ts.forEachChild(node, visit);
    };
    visit(tree);
    expect(violations, name).toEqual([]);
  }
});
