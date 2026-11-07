import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "../App";
import { api } from "../api/client";
import { ApiError } from "../api/errors";
import { MockApiClient } from "../api/MockApiClient";
import type { CreateJobRequest, UploadRecord } from "../api/types";
import { AUTO_RUN_KEY, readAutoRun } from "./generate/autoRun";
import { pastedImages } from "./generate/ImageInputs";

vi.mock("../components/GlbViewer", () => ({
  default: () => <div>Interactive GLB viewer</div>,
}));

function mount(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const request = (
  overrides: Partial<CreateJobRequest> = {},
): CreateJobRequest => ({
  contract_version: "1.0",
  client_request_id: crypto.randomUUID(),
  pipeline_type: "text_to_2d",
  asset_category: "weapon",
  model_id: "mock-t2d-basic",
  prompt: "Ornate frost greatsword",
  inputs: [],
  options: { seed: 1, width: 512, height: 512 },
  output_format: "png",
  compute: { profile_id: "default", accelerator_id: null },
  ...overrides,
});

const code = async (promise: Promise<unknown>) => {
  try {
    await promise;
  } catch (error) {
    if (error instanceof ApiError) return error.response.errors[0];
    throw error;
  }
  throw new Error("expected a refusal");
};

let index = 0;
beforeEach(() => {
  localStorage.clear();
  index = 0;
  vi.spyOn(api, "artifactContent").mockResolvedValue(new Blob(["fixture"]));
  vi.spyOn(api, "uploadContent").mockResolvedValue(new Blob(["fixture"]));
  vi.spyOn(api, "upload").mockImplementation(
    async (file) =>
      ({
        contract_version: "1.0",
        upload_id: `upl_${String(index++).padStart(32, "b")}`,
        filename: file.name,
        mime_type: file.type || "image/png",
        width: 1024,
        height: 1024,
        size_bytes: 1000,
        sha256: "b".repeat(64),
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400_000).toISOString(),
      }) satisfies UploadRecord,
  );
});
afterEach(() => vi.restoreAllMocks());

describe("mock API run control (CONTRACTS §14)", () => {
  it("holds a job with auto-run off until it is turned on", async () => {
    let now = Date.parse("2026-11-07T10:00:00Z");
    const mock = new MockApiClient(1000, false, () => now);
    const held = await mock.createJob(request({ auto_run: false }));
    expect(held.scheduling).toMatchObject({
      auto_run: false,
      queue_state: "held",
      queue_position: null,
      run_requested_at: null,
    });
    now += 10_000;
    expect((await mock.job(held.job_id)).status).toBe("created");
    const waiting = await mock.setAutoRun(held.job_id, true);
    expect(waiting.scheduling?.run_requested_at).not.toBeNull();
    await mock.job(held.job_id); // the next poll takes the session
    now += 10_000;
    expect((await mock.job(held.job_id)).status).not.toBe("created");
  });

  it("numbers waiting jobs in FIFO order and refuses changes once started", async () => {
    let now = Date.parse("2026-11-07T10:00:00Z");
    const mock = new MockApiClient(1000, false, () => now);
    const first = await mock.createJob(request());
    await mock.job(first.job_id); // takes the session
    now += 1500;
    const second = await mock.createJob(request());
    const third = await mock.createJob(request());
    expect((await mock.job(second.job_id)).scheduling?.queue_position).toBe(1);
    expect((await mock.job(third.job_id)).scheduling?.queue_position).toBe(2);
    const started = await code(mock.setAutoRun(first.job_id, false));
    expect(started.code).toBe("JOB_ALREADY_STARTED");
    const summary = (await mock.jobs()).jobs.find(
      (j) => j.job_id === third.job_id,
    );
    expect(summary?.scheduling?.queue_state).toBe("waiting");
  });

  it("checks run groups like the backend and refuses mock models without a known GPU need", async () => {
    let now = Date.parse("2026-11-07T10:00:00Z");
    const mock = new MockApiClient(1000, false, () => now);
    const gpu = { profile_id: "default", accelerator_id: "gpu_t4x2" };
    const a = await mock.createJob(request({ auto_run: false, compute: gpu }));
    const b = await mock.createJob(request({ auto_run: false, compute: gpu }));
    const vram = await code(mock.createRunGroup([a.job_id, b.job_id]));
    expect(vram).toMatchObject({
      code: "JOB_GROUP_INVALID",
      details: { reason: "vram" },
    });
    expect(
      (await code(mock.createRunGroup([a.job_id, a.job_id]))).details.reason,
    ).toBe("count");
    const c = await mock.createJob(request({ compute: gpu }));
    now += 10;
    const runningOrWaiting = await code(
      mock.createRunGroup([a.job_id, c.job_id]),
    );
    expect(["JOB_ALREADY_STARTED", "JOB_GROUP_INVALID"]).toContain(
      runningOrWaiting.code,
    );
  });

  it("bulk-deletes held and finished jobs and reports the rest", async () => {
    let now = Date.parse("2026-11-07T10:00:00Z");
    const mock = new MockApiClient(1000, false, () => now);
    const done = await mock.createJob(request());
    await mock.job(done.job_id);
    now += 10_000;
    expect((await mock.job(done.job_id)).status).toBe("completed");
    const running = await mock.createJob(request());
    await mock.job(running.job_id);
    now += 1500;
    const held = await mock.createJob(request({ auto_run: false }));
    const result = await mock.deleteJobs([
      done.job_id,
      held.job_id,
      running.job_id,
      "job_20261106T101500Z_a1b2c3",
    ]);
    expect(result.deleted).toEqual([done.job_id, held.job_id]);
    expect(result.refused).toEqual([
      { job_id: running.job_id, code: "JOB_NOT_TERMINAL" },
      { job_id: "job_20261106T101500Z_a1b2c3", code: "JOB_NOT_FOUND" },
    ]);
  });
});

describe("auto-run preference", () => {
  it("is remembered and survives blocked storage", () => {
    expect(readAutoRun()).toBe(true);
    localStorage.setItem(AUTO_RUN_KEY, "false");
    expect(readAutoRun()).toBe(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readAutoRun()).toBe(true);
  });

  it("is sent with the job and stored when switched off", async () => {
    const create = vi.spyOn(api, "createJob");
    mount("/generate/text-to-2d");
    await screen.findByRole("combobox", { name: "Model" });
    await userEvent.type(
      document.querySelector<HTMLTextAreaElement>('textarea[name="prompt"]')!,
      "A frost blade",
    );
    const toggle = await screen.findByRole("switch", { name: /auto-run/i });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(localStorage.getItem(AUTO_RUN_KEY)).toBe("false");
    const generate = await screen.findByRole("button", { name: /generate/i });
    await waitFor(() => expect(generate).toBeEnabled());
    await userEvent.click(generate);
    await waitFor(() => expect(create).toHaveBeenCalled());
    expect(create.mock.calls[0][0].auto_run).toBe(false);
  });
});

describe("style images (CONTRACTS §14.9)", () => {
  it("reads only image files from a paste", () => {
    const image = new File(["x"], "a.png", { type: "image/png" });
    const data = {
      files: [image, new File(["t"], "t.txt", { type: "text/plain" })],
      items: [],
    };
    expect(pastedImages(data as unknown as DataTransfer)).toEqual([image]);
    expect(pastedImages(null)).toEqual([]);
  });

  it("labels the area, hints the prompt and uploads a pasted image", async () => {
    mount("/generate/text-to-2d");
    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: "Model" }),
      "mock-t2d-styleref",
    );
    expect(await screen.findByText("Style images")).toBeInTheDocument();
    expect(
      screen.getByText(/use only the style of the reference images/i),
    ).toBeInTheDocument();
    const image = new File(["png"], "style.png", { type: "image/png" });
    const event = new Event("paste", { bubbles: true, cancelable: true });
    Object.assign(event, { clipboardData: { files: [image], items: [] } });
    fireEvent(window, event);
    await waitFor(() => expect(api.upload).toHaveBeenCalledWith(image));
    expect(await screen.findByText("style.png")).toBeInTheDocument();
  });

  it("shows the style strength slider only once a style image is added", async () => {
    const response = await api.models();
    const styleref = response.models.find(
      (m) => m.model_id === "mock-t2d-styleref",
    )!;
    vi.spyOn(api, "models").mockResolvedValue({
      ...response,
      models: response.models.map((m) =>
        m.model_id === "mock-t2d-styleref"
          ? {
              ...styleref,
              options_schema: {
                ...styleref.options_schema,
                style_strength: {
                  type: "number",
                  minimum: 0,
                  maximum: 1,
                  default: 0.6,
                },
              },
            }
          : m,
      ),
    });
    mount("/generate/text-to-2d");
    await userEvent.selectOptions(
      await screen.findByRole("combobox", { name: "Model" }),
      "mock-t2d-styleref",
    );
    await screen.findByText("Style images");
    expect(
      screen.queryByRole("slider", { name: /style strength/i }),
    ).toBeNull();
    expect(
      screen.queryByText(/use only the style of the reference images/i),
    ).toBeNull();
    await userEvent.upload(
      screen.getByLabelText(/upload reference images/i),
      new File(["png"], "style.png", { type: "image/png" }),
    );
    expect(await screen.findByText("style.png")).toBeInTheDocument();
    expect(
      await screen.findByRole("slider", { name: /style strength/i }),
    ).toHaveValue("0.6");
  });
});

describe("jobs page selection", () => {
  it("runs two selected held jobs together", async () => {
    const gpu = { profile_id: "default", accelerator_id: "gpu_t4x2" };
    const a = await api.createJob(request({ auto_run: false, compute: gpu }));
    const b = await api.createJob(request({ auto_run: false, compute: gpu }));
    const group = vi.spyOn(api, "createRunGroup").mockResolvedValue({
      contract_version: "1.0",
      group_id: "grp_0123456789ab",
      job_ids: [a.job_id, b.job_id],
      run_requested_at: new Date().toISOString(),
    });
    mount("/jobs");
    const together = await screen.findByRole("button", {
      name: "Run together",
    });
    expect(together).toBeDisabled();
    expect((await screen.findAllByText("Held")).length).toBeGreaterThanOrEqual(
      2,
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: `Select ${a.job_id}` }),
    );
    await userEvent.click(
      screen.getByRole("checkbox", { name: `Select ${b.job_id}` }),
    );
    await waitFor(() => expect(together).toBeEnabled());
    await userEvent.click(together);
    await waitFor(() =>
      expect(group).toHaveBeenCalledWith([a.job_id, b.job_id]),
    );
    expect(
      await screen.findByText(/Run group grp_0123456789ab created/),
    ).toBeInTheDocument();
    await api.deleteJobs([a.job_id, b.job_id]);
  });

  it("selects all completed jobs, deletes them after one confirmation and lists refusals", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const remove = vi.spyOn(api, "deleteJobs").mockResolvedValue({
      contract_version: "1.0",
      deleted: [],
      refused: [
        { job_id: "job_20261106T101500Z_a1b2c3", code: "JOB_NOT_TERMINAL" },
      ],
    });
    mount("/jobs");
    await userEvent.click(
      await screen.findByRole("button", { name: "Select all completed" }),
    );
    const completed = (await api.jobs()).jobs.filter(
      (j) => j.status === "completed",
    );
    expect(
      screen.getByText(`${completed.length} selected`),
    ).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: "Delete selected" }),
    );
    expect(confirm).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(remove).toHaveBeenCalled());
    expect(remove.mock.calls[0][0].sort()).toEqual(
      completed.map((j) => j.job_id).sort(),
    );
    const refused = await screen.findByText("Not deleted");
    expect(
      within(refused.parentElement!).getByText(/already started/),
    ).toBeInTheDocument();
  });
});

describe("asset library", () => {
  it("labels only mock-model assets as mock and deletes an asset's job after confirming", async () => {
    const response = await api.models();
    vi.spyOn(api, "models").mockResolvedValue({
      ...response,
      models: response.models.map((m) =>
        m.model_id === "mock-t2d-basic" ? { ...m, is_mock: false } : m,
      ),
    });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const remove = vi.spyOn(api, "deleteJob").mockResolvedValue(undefined);
    mount("/library");
    const cards = await screen.findAllByRole("article");
    const png = cards.find((c) => within(c).queryByText("mock-t2d-basic"))!;
    await waitFor(() =>
      expect(within(png).getByText("PNG")).toBeInTheDocument(),
    );
    expect(within(png).queryByText(/MOCK/)).toBeNull();
    const glb = cards.find((c) => within(c).queryByText("mock-i3d-single"))!;
    await waitFor(() =>
      expect(within(glb).getByText("GLB · MOCK")).toBeInTheDocument(),
    );
    await userEvent.click(
      within(png).getByRole("button", { name: /Delete the asset of job/ }),
    );
    expect(confirm.mock.calls[0][0]).toMatch(
      /Delete job job_\S+ and its 1 image\(s\)\?/,
    );
    await waitFor(() => expect(remove).toHaveBeenCalled());
  });
});
