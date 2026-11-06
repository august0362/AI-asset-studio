import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { api } from "../../api/client";
import { ApiError, issue } from "../../api/errors";
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
describe("V2 shared stage shell", () => {
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
