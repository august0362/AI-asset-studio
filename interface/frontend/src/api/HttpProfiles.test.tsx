import {
  cleanup,
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
import { catalog, makeSnapshot, models, profiles } from "./fixtures";
import { issue } from "./errors";
import type { ComputeProfile } from "./types";

// Exercise the pages through the real HTTP client, with no backend or Kaggle calls.
vi.mock("./client", async () => {
  const { HttpApiClient } = await import("./HttpApiClient");
  return { api: new HttpApiClient("/api/v1"), isMock: false };
});

const routes = [
  ["Studio", "/generate/text-to-2d", "Compute profile · Explicit selection"],
  ["Resources", "/resources", "Authorized profile"],
] as const;
let configured: ComputeProfile[];
let unavailable: Set<string>;
let fetchMock: ReturnType<
  typeof vi.fn<(input: string, init?: RequestInit) => Promise<Response>>
>;
const clients: QueryClient[] = [];

function mount(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
function snapshotRequests() {
  return fetchMock.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.includes("/snapshot"));
}
beforeEach(() => {
  localStorage.clear();
  configured = [
    {
      ...profiles[0],
      profile_id: "atume",
      display_name: "ATUME",
      enabled: false,
    },
    {
      ...profiles[0],
      profile_id: "sunny",
      display_name: "SUNNY",
      enabled: true,
    },
    { ...profiles[0], profile_id: "duma", display_name: "DUMA", enabled: true },
  ].map((profile) => ({ ...profile, mode: "kaggle" }));
  unavailable = new Set();
  fetchMock = vi.fn(async (input: string) => {
    const url = new URL(input, "http://localhost");
    const path = url.pathname.replace("/api/v1", "");
    let body: unknown;
    let status = 200;
    if (path === "/catalog") body = catalog;
    else if (path === "/models") body = { models };
    else if (path === "/compute/profiles") body = { profiles: configured };
    else if (path === "/jobs") body = { jobs: [], next_cursor: null };
    else if (path === "/validate")
      body = {
        contract_version: "1.0",
        valid: false,
        errors: [
          issue(
            "REQUEST_FIELD_INVALID",
            "prompt",
            "Transport test: no job submitted.",
          ),
        ],
        warnings: [],
        resource_plan: null,
      };
    else if (/^\/compute\/profiles\/[^/]+\/snapshot$/.test(path)) {
      const id = decodeURIComponent(path.split("/")[3]);
      if (
        !configured.some((p) => p.profile_id === id && p.enabled) ||
        unavailable.has(id)
      ) {
        status = 404;
        body = {
          contract_version: "1.0",
          errors: [
            issue(
              "COMPUTE_PROFILE_NOT_FOUND",
              "compute.profile_id",
              `Unknown compute profile: ${id}.`,
            ),
          ],
          warnings: [],
        };
      } else body = { ...makeSnapshot("fresh"), compute_profile_id: id };
    } else throw new Error(`Unexpected HTTP request: ${input}`);
    return new Response(JSON.stringify(body), { status });
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
  vi.unstubAllGlobals();
});

describe("HTTP compute profiles on Studio and Resources", () => {
  it.each(routes)(
    "%s starts with the first enabled profile even without default",
    async (_name, path, label) => {
      mount(path);
      const select = await screen.findByRole("combobox", { name: label });
      await waitFor(() => expect(select).toHaveValue("sunny"));
      await waitFor(() =>
        expect(snapshotRequests()).toEqual([
          "/api/v1/compute/profiles/sunny/snapshot?refresh=0",
        ]),
      );
      expect(within(select).getAllByRole("option")).toHaveLength(3);
      expect(
        within(select).getByRole("option", { name: /^ATUME/ }),
      ).toBeDisabled();
      expect(
        within(select).getByRole("option", { name: /^SUNNY/ }),
      ).toBeEnabled();
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      if (path.startsWith("/generate")) {
        await userEvent.type(
          screen.getByRole("textbox", { name: /^Prompt/ }),
          "A bronze sword",
        );
        await waitFor(() =>
          expect(
            screen.getByRole("button", { name: "Generate 2D image" }),
          ).toBeEnabled(),
        );
      } else
        expect(
          await screen.findByRole("heading", { name: "Host resources" }),
        ).toBeVisible();
    },
  );

  it.each(routes)(
    "%s keeps its selector usable after a snapshot 404",
    async (_name, path, label) => {
      unavailable.add("sunny");
      mount(path);
      const select = await screen.findByRole("combobox", { name: label });
      expect(
        await screen.findByText(
          "COMPUTE_PROFILE_NOT_FOUND · compute.profile_id",
        ),
      ).toBeVisible();
      expect(select).toBeVisible();
      if (path.startsWith("/generate"))
        expect(
          screen.getByRole("button", { name: "Generate 2D image" }),
        ).toBeDisabled();
      await userEvent.selectOptions(select, "duma");
      await waitFor(() =>
        expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
      );
      expect(select).toHaveValue("duma");
      expect(snapshotRequests()).toEqual([
        "/api/v1/compute/profiles/sunny/snapshot?refresh=0",
        "/api/v1/compute/profiles/duma/snapshot?refresh=0",
      ]);
      if (path.startsWith("/generate")) {
        await userEvent.type(
          screen.getByRole("textbox", { name: /^Prompt/ }),
          "A bronze sword",
        );
        await waitFor(() =>
          expect(
            screen.getByRole("button", { name: "Generate 2D image" }),
          ).toBeEnabled(),
        );
      } else
        expect(
          await screen.findByRole("heading", { name: "Host resources" }),
        ).toBeVisible();
    },
  );

  it.each(routes)(
    "%s shows an empty state when every profile is disabled",
    async (_name, path, label) => {
      configured = configured.map((p) => ({ ...p, enabled: false }));
      mount(path);
      expect(
        await screen.findByRole("heading", {
          name: "No enabled compute profiles",
        }),
      ).toBeVisible();
      const select = screen.getByRole("combobox", { name: label });
      expect(
        within(select).getByRole("option", { name: /^SUNNY/ }),
      ).toBeDisabled();
      expect(snapshotRequests()).toEqual([]);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      if (path.startsWith("/generate"))
        expect(
          screen.getByRole("button", { name: "Generate 2D image" }),
        ).toBeDisabled();
    },
  );

  it.each(routes)(
    "%s shows an empty state for an empty profiles list",
    async (_name, path, label) => {
      configured = [];
      mount(path);
      expect(
        await screen.findByRole("heading", {
          name: "No enabled compute profiles",
        }),
      ).toBeVisible();
      expect(screen.getByRole("combobox", { name: label })).toHaveValue("");
      expect(snapshotRequests()).toEqual([]);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    },
  );

  it("waits for the profiles response before requesting any snapshot", async () => {
    const transport = fetchMock.getMockImplementation()!;
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    fetchMock.mockImplementation(async (input: string) => {
      if (input.endsWith("/compute/profiles")) await pending;
      return transport(input);
    });
    mount("/generate/text-to-2d");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/compute/profiles",
        expect.anything(),
      ),
    );
    expect(snapshotRequests()).toEqual([]);
    release();
    await waitFor(() =>
      expect(snapshotRequests()).toEqual([
        "/api/v1/compute/profiles/sunny/snapshot?refresh=0",
      ]),
    );
  });

  it("preserves an explicit Resources profile override", async () => {
    mount("/resources?profile=duma");
    expect(
      await screen.findByRole("combobox", { name: "Authorized profile" }),
    ).toHaveValue("duma");
    expect(
      await screen.findByRole("heading", { name: "Host resources" }),
    ).toBeVisible();
    expect(snapshotRequests()).toEqual([
      "/api/v1/compute/profiles/duma/snapshot?refresh=0",
    ]);
  });

  it("sends the selected configured profile in HTTP validation requests", async () => {
    mount("/generate/text-to-2d");
    const select = await screen.findByRole("combobox", {
      name: "Compute profile · Explicit selection",
    });
    await userEvent.selectOptions(select, "duma");
    await userEvent.type(
      screen.getByRole("textbox", { name: /^Prompt/ }),
      "A bronze sword",
    );
    const generate = screen.getByRole("button", { name: "Generate 2D image" });
    await waitFor(() => expect(generate).toBeEnabled());
    await userEvent.click(generate);
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/v1/validate",
        expect.objectContaining({ method: "POST" }),
      ),
    );
    const [, init] = fetchMock.mock.calls.find(
      ([url]) => url === "/api/v1/validate",
    )!;
    expect(JSON.parse(init!.body as string).compute).toEqual({
      profile_id: "duma",
      accelerator_id: null,
    });
  });

  it("keeps a stale Resources override visible and lets the user recover", async () => {
    mount("/resources?profile=missing");
    expect(
      await screen.findByText("COMPUTE_PROFILE_NOT_FOUND · compute.profile_id"),
    ).toBeVisible();
    const select = screen.getByRole("combobox", { name: "Authorized profile" });
    expect(select).toHaveValue("missing");
    await userEvent.selectOptions(select, "sunny");
    expect(
      await screen.findByRole("heading", { name: "Host resources" }),
    ).toBeVisible();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(select).toHaveValue("sunny");
  });

  it("keeps the Studio's explicit profile when navigating away and back", async () => {
    mount("/generate/text-to-2d");
    const select = await screen.findByRole("combobox", {
      name: "Compute profile · Explicit selection",
    });
    await userEvent.selectOptions(select, "duma");
    await userEvent.click(
      screen.getAllByRole("link", { name: "Kaggle resources" })[0],
    );
    expect(
      await screen.findByRole("combobox", { name: "Authorized profile" }),
    ).toHaveValue("sunny");
    await userEvent.click(
      screen.getAllByRole("link", { name: "Generate studio" })[0],
    );
    expect(
      await screen.findByRole("combobox", {
        name: "Compute profile · Explicit selection",
      }),
    ).toHaveValue("duma");
  });
});
