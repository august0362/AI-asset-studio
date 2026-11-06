import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { makeSnapshot } from "../../api/fixtures";
import { scenarios } from "../../api/types";
import { SnapshotDashboard } from "./ResourcesPage";
describe("resource snapshot UI", () => {
  it("V-08 keeps GPU0 and GPU1 independent", () => {
    render(<SnapshotDashboard snapshot={makeSnapshot("gpu_split")} />);
    expect(
      screen.getByRole("meter", { name: "GPU0 utilization" }),
    ).toHaveAttribute("aria-valuenow", "97");
    expect(
      screen.getByRole("meter", { name: "GPU1 utilization" }),
    ).toHaveAttribute("aria-valuenow", "23");
    expect(
      screen.getByRole("meter", { name: "GPU0 VRAM used" }),
    ).toHaveAttribute("aria-valuenow", "12.5");
    expect(
      screen.getByRole("meter", { name: "GPU1 VRAM used" }),
    ).toHaveAttribute("aria-valuenow", "3");
  });
  it("V-10 labels stale telemetry and retains last values", () => {
    render(<SnapshotDashboard snapshot={makeSnapshot("telemetry_stale")} />);
    expect(screen.getAllByText("stale")).toHaveLength(3);
    expect(screen.getByText("COMPUTE_TELEMETRY_STALE · host")).toBeVisible();
    expect(
      screen.getByRole("meter", { name: "GPU0 utilization" }),
    ).toBeVisible();
    expect(screen.queryByText(/live/i)).not.toBeInTheDocument();
  });
  it("V-10 unavailable telemetry shows no CPU/GPU numeric gauges", () => {
    render(
      <SnapshotDashboard snapshot={makeSnapshot("telemetry_unavailable")} />,
    );
    expect(
      screen.queryByRole("meter", { name: "CPU utilization" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("meter", { name: "GPU0 utilization" }),
    ).not.toBeInTheDocument();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThan(2);
  });
  it.each(scenarios)(
    "renders %s with provenance and an explicit mock label",
    (scenario) => {
      render(<SnapshotDashboard snapshot={makeSnapshot(scenario)} />);
      expect(screen.getAllByText(/MOCK/).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Source:/).length).toBeGreaterThanOrEqual(4);
      expect(
        screen.getByText("TPU telemetry · Unsupported in M1"),
      ).toBeVisible();
    },
  );
  it("no session is not represented as zero utilization", () => {
    render(<SnapshotDashboard snapshot={makeSnapshot("no_session")} />);
    expect(screen.getByText("No active session")).toBeVisible();
    expect(
      screen.queryByRole("meter", { name: "CPU utilization" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("No session · GPU telemetry is not applicable."),
    ).toBeVisible();
  });
  it("missing quota never assumes a weekly total", () => {
    render(<SnapshotDashboard snapshot={makeSnapshot("quota_missing")} />);
    const panel = screen
      .getByRole("heading", { name: "Weekly compute quota" })
      .closest("section")!;
    expect(within(panel).queryByText(/30/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("meter", { name: "GPU quota used" }),
    ).not.toBeInTheDocument();
  });
});
