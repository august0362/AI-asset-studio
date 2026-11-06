import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";
import { DeleteCharacterDialog } from "./DeleteCharacterDialog";
import { api } from "../../api/client";
import { ApiError, issue } from "../../api/errors";
import { I18nProvider } from "../../i18n";
import { canvasKey } from "./canvasLayout";

const character = { character_id: "chr_012345abcdef", name: "Ranger" };
beforeEach(() => localStorage.clear());
function mount() {
  const cache = new QueryClient(), onClose = vi.fn();
  cache.setQueryData(["characters"], { characters: [character] });
  cache.setQueryData(["character", character.character_id], character);
  render(<QueryClientProvider client={cache}><I18nProvider><MemoryRouter initialEntries={["/workspace"]}><Routes>
    <Route path="/workspace" element={<DeleteCharacterDialog character={character} onClose={onClose} />} />
    <Route path="/characters" element={<h1>Library refreshed</h1>} />
  </Routes></MemoryRouter></I18nProvider></QueryClientProvider>);
  return { cache, onClose };
}
it("names the character, explains permanent removal and retained jobs, and cancel makes no request", async () => {
  const remove = vi.spyOn(api, "deleteCharacter"), { onClose, cache } = mount();
  expect(screen.getByRole("dialog", { name: "Delete Ranger?" })).toBeVisible();
  expect(screen.getByText(/References, revisions, approved images and history are removed permanently/)).toHaveTextContent("Kaggle jobs stay in Jobs.");
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(remove).not.toHaveBeenCalled();
  expect(onClose).toHaveBeenCalledOnce();
  cache.clear();
});
it("deletes once, invalidates the library, removes the saved layout and navigates", async () => {
  const remove = vi.spyOn(api, "deleteCharacter").mockResolvedValue();
  localStorage.setItem(canvasKey(character.character_id), "saved");
  localStorage.setItem(canvasKey("other"), "other layout");
  const { cache, onClose } = mount();
  await userEvent.click(screen.getByRole("button", { name: "Delete character" }));
  await screen.findByRole("heading", { name: "Library refreshed" });
  expect(remove).toHaveBeenCalledExactlyOnceWith(character.character_id);
  expect(onClose).toHaveBeenCalledOnce();
  expect(cache.getQueryState(["characters"])?.isInvalidated).toBe(true);
  expect(cache.getQueryData(["character", character.character_id])).toBeUndefined();
  expect(localStorage.getItem(canvasKey(character.character_id))).toBeNull();
  expect(localStorage.getItem(canvasKey("other"))).toBe("other layout");
  cache.clear();
});
it.each(["en", "vi"])("keeps the dialog and layout after a localized running attempt error in %s", async (locale) => {
  localStorage.setItem("aas.locale", locale);
  localStorage.setItem(canvasKey(character.character_id), "saved");
  vi.spyOn(api, "deleteCharacter").mockRejectedValue(new ApiError({ contract_version: "1.1", errors: [issue("BATCH_ATTEMPT_RUNNING", null, "Backend English message", "error", { manifest_ids: ["bat_012345abcdef"] })], warnings: [] }, 409));
  const { cache, onClose } = mount();
  await userEvent.click(screen.getByRole("button", { name: locale === "en" ? "Delete character" : "Xóa nhân vật" }));
  await waitFor(() => expect(screen.getByText(locale === "en" ? "Wait for the running attempt to finish." : "Hãy chờ lần chạy hiện tại kết thúc.")).toBeVisible());
  expect(screen.getByText("BATCH_ATTEMPT_RUNNING")).toBeVisible();
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(onClose).not.toHaveBeenCalled();
  expect(localStorage.getItem(canvasKey(character.character_id))).toBe("saved");
  cache.clear();
});
