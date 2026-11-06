import { describe, expect, it } from "vitest";
import type { ApprovedSnapshot, StageId, WorkflowStage } from "../../api/characterTypes";
import { flowsData } from "./WorkflowCanvas";

const approved = (over: Partial<ApprovedSnapshot> = {}): ApprovedSnapshot => ({
  revision: 1,
  approved_at: "2026-11-06T00:00:00Z",
  source_revisions: {},
  stale: false,
  stale_reasons: [],
  ...over,
});
const stage = (id: StageId, snapshot: ApprovedSnapshot | null) =>
  ({ config: { stage_id: id }, state: { stage_id: id, approved: snapshot } }) as unknown as WorkflowStage;

describe("data flow on canvas edges (D-039)", () => {
  it("flows only when the upstream stage has an approved revision", () => {
    expect(flowsData(stage("s1", approved()), stage("s2", null), "s1")).toBe(true);
    expect(flowsData(stage("s1", null), stage("s2", null), "s1")).toBe(false);
    expect(flowsData(undefined, stage("s2", null), "s1")).toBe(false);
  });
  it("does not flow from a stale upstream approval", () => {
    expect(flowsData(stage("s2", approved({ stale: true })), stage("s3", null), "s2")).toBe(false);
    const reason = { upstream_stage_id: "s1" as const, used_revision: 1, current_revision: 2 };
    expect(flowsData(stage("s2", approved({ stale_reasons: [reason] })), stage("s3", null), "s2")).toBe(false);
  });
  it("does not flow into a downstream end marked stale by that upstream", () => {
    const reason = { upstream_stage_id: "s1" as const, used_revision: 1, current_revision: 2 };
    expect(flowsData(stage("s1", approved({ revision: 2 })), stage("s2", approved({ stale: true, stale_reasons: [reason] })), "s1")).toBe(false);
    const other = { ...reason, upstream_stage_id: "s3" as const };
    expect(flowsData(stage("s1", approved()), stage("s4", approved({ stale: true, stale_reasons: [other] })), "s1")).toBe(true);
  });
});
