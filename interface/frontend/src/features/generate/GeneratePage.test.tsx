import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../../App";
import { api } from "../../api/client";
import type { UploadRecord } from "../../api/types";
vi.mock("../../components/GlbViewer", () => ({
  default: () => <div>Interactive GLB viewer</div>,
}));
function mount(path = "/generate/image-to-3d") {
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
        upload_id: `upl_${String(index++).padStart(32, "a")}`,
        filename: file.name,
        mime_type: file.type,
        width: 1024,
        height: 1536,
        size_bytes: 1000,
        sha256: "a".repeat(64),
        created_at: new Date().toISOString(),
        expires_at: new Date(Date.now() + 86400_000).toISOString(),
      }) satisfies UploadRecord,
  );
});
describe("dynamic studio form", () => {
  it.each(["en", "vi"])(
    "shows real model times and tooltips in the %s picker without translating names",
    async (locale) => {
      localStorage.setItem("aas.locale", locale);
      const response = await api.models();
      const base = response.models.find(
        (m) => m.model_id === "mock-t2d-basic",
      )!;
      vi.spyOn(api, "models").mockResolvedValue({
        ...response,
        models: [
          ...response.models,
          ...[25, 89, 90, 354, null].map((seconds, index) => ({
            ...base,
            model_id: `real-${index}`,
            display_name: `Original model ${index}`,
            is_mock: false,
            supported_asset_categories: base.supported_asset_categories.filter(
              (category) => category === "character",
            ),
            runtime: { ...base.runtime, estimated_runtime_seconds: seconds },
          })),
        ],
      });
      mount("/generate/text-to-2d");
      const select = await screen.findByRole("combobox", {
        name: locale === "vi" ? "Mô hình" : "Model",
      });
      expect(select).not.toHaveAttribute("title");
      const tooltip =
        locale === "vi"
          ? "Thời gian trung bình mỗi ảnh đo trên Kaggle T4; không bao gồm thiết lập và tải xuống."
          : "Mean time per image measured on a Kaggle T4; excludes setup and download.";
      for (const [index, count, minutes] of [
        [0, 25, false],
        [1, 89, false],
        [2, 2, true],
        [3, 6, true],
      ] as const) {
        const unit =
          locale === "vi"
            ? minutes
              ? "phút/ảnh"
              : "giây/ảnh"
            : minutes
              ? "min/image"
              : "s/image";
        expect(
          screen.getByRole("option", {
            name: `Original model ${index} (~${count} ${unit})`,
          }),
        ).toHaveAttribute("title", tooltip);
      }
      expect(
        screen.getByRole("option", { name: "Original model 4" }),
      ).not.toHaveAttribute("title");
      const user = userEvent.setup();
      await user.selectOptions(select, "real-0");
      expect(select).toHaveAttribute("title", tooltip);
      await user.selectOptions(select, "real-4");
      expect(select).not.toHaveAttribute("title");
      await user.selectOptions(select, "real-0");
      // A retained, incompatible selection must keep its estimate as well.
      await user.selectOptions(
        screen.getByRole("combobox", {
          name: locale === "vi" ? "Loại tài sản" : "Asset category",
        }),
        "weapon",
      );
      expect(select).toHaveValue("real-0");
      expect(
        screen.getByRole("option", { name: /Original model 0/ }),
      ).toHaveTextContent(
        locale === "vi"
          ? "Original model 0 (~25 giây/ảnh)"
          : "Original model 0 (~25 s/image)",
      );
    },
  );
  it("keeps request fields and option values in English when the UI is Vietnamese", async () => {
    const user = userEvent.setup();
    const created = vi.spyOn(api, "createJob");
    mount("/generate/text-to-2d");
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Language" }),
      "vi",
    );
    await user.type(
      await screen.findByRole("textbox", { name: /^Prompt · Bắt buộc/ }),
      "English request content",
    );
    await user.selectOptions(screen.getByLabelText("Loại tài sản"), "weapon");
    await user.selectOptions(screen.getByLabelText("Chiều rộng"), "768");
    await user.click(screen.getByRole("button", { name: "Tạo ảnh 2D" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(created.mock.calls[0][0]).toMatchObject({
      pipeline_type: "text_to_2d",
      asset_category: "weapon",
      model_id: "mock-t2d-basic",
      prompt: "English request content",
      output_format: "png",
      options: { width: 768 },
      compute: { profile_id: "default", accelerator_id: null },
    });
    localStorage.removeItem("aas.locale");
  });
  it("renders options from capabilities and keeps planned Text → 3D disabled", async () => {
    mount();
    expect(await screen.findByRole("combobox", { name: "Model" })).toHaveValue(
      "mock-i3d-multiview",
    );
    expect(
      screen.getByRole("combobox", { name: "texture resolution" }),
    ).toBeVisible();
    expect(
      screen.queryByRole("textbox", { name: /Prompt/ }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Text → 3D/ })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Generate 3D asset" }),
    ).toBeDisabled();
  });
  it("V-19 retains all three uploads and marks count/role errors on model switch", async () => {
    const user = userEvent.setup();
    mount();
    const input = await screen.findByLabelText("Upload reference images");
    await user.upload(
      input,
      ["front", "side", "back"].map(
        (n) => new File(["image"], `${n}.png`, { type: "image/png" }),
      ),
    );
    expect(await screen.findByText("back.png")).toBeVisible();
    expect(
      screen.getAllByRole("button", { name: /Remove .*png/ }),
    ).toHaveLength(3);
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Generate 3D asset" }),
      ).toBeEnabled(),
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Model" }),
      "mock-i3d-single",
    );
    expect(
      screen.getAllByRole("button", { name: /Remove .*png/ }),
    ).toHaveLength(3);
    expect(
      screen.getByText("MODEL_INPUT_COUNT_EXCEEDED · inputs"),
    ).toBeVisible();
    expect(screen.getAllByText(/MODEL_IMAGE_ROLE_UNSUPPORTED/)).toHaveLength(2);
    expect(
      screen.getByRole("button", { name: "Generate 3D asset" }),
    ).toBeDisabled();
  });
  it("preserves a non-default option and restores it without sending it to other models", async () => {
    const user = userEvent.setup();
    mount();
    await screen.findByRole("combobox", { name: "texture resolution" });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "texture resolution" }),
      "2048",
    );
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Model" }),
      "mock-i3d-single",
    );
    expect(
      screen.queryByRole("combobox", { name: "texture resolution" }),
    ).not.toBeInTheDocument();
    expect(screen.getByText("texture resolution: 2,048")).toBeVisible();
    await user.selectOptions(
      screen.getByRole("combobox", { name: "Model" }),
      "mock-i3d-multiview",
    );
    expect(
      screen.getByRole("combobox", { name: "texture resolution" }),
    ).toHaveValue("2048");
  });
  it("retains prompt and uploaded references when changing pipeline", async () => {
    const user = userEvent.setup();
    mount("/generate/text-to-2d");
    await screen.findByRole("textbox", { name: /Prompt/ });
    await user.type(
      screen.getByRole("textbox", { name: /Prompt/ }),
      "Cyan box",
    );
    await user.click(screen.getByRole("button", { name: "Image → 3D" }));
    expect(
      screen.getByRole("textbox", { name: /Retained prompt · Unsupported/ }),
    ).toHaveValue("Cyan box");
    expect(
      screen.getByText("MODEL_PROMPT_NOT_SUPPORTED · prompt"),
    ).toBeVisible();
  });
  it("a direct planned route reports PIPELINE_NOT_AVAILABLE", async () => {
    mount("/generate/text-to-3d");
    await screen.findByRole("combobox", { name: "Model" });
    expect(
      screen.getAllByText("PIPELINE_NOT_AVAILABLE · pipeline_type").length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("button", { name: "Generate 3D asset" }),
    ).toBeDisabled();
  });
  it("navigation works and keeps the studio draft", async () => {
    const user = userEvent.setup();
    mount("/generate/text-to-2d");
    await user.type(
      await screen.findByRole("textbox", { name: /Prompt/ }),
      "Retained draft",
    );
    await user.click(screen.getAllByRole("link", { name: "Asset library" })[0]);
    expect(
      await screen.findByRole("heading", { name: "Asset library", level: 1 }),
    ).toBeVisible();
    await user.click(screen.getAllByRole("link", { name: "Jobs & logs" })[0]);
    expect(
      await screen.findByRole("heading", { name: "Jobs & logs", level: 1 }),
    ).toBeVisible();
    await user.click(
      screen.getAllByRole("link", { name: "Generate studio" })[0],
    );
    expect(await screen.findByRole("textbox", { name: /Prompt/ })).toHaveValue(
      "Retained draft",
    );
  });
});
