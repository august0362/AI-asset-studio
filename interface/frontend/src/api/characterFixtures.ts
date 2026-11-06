import type {
  BatchManifest,
  StageDetail,
  Character,
  CharacterList,
  CharacterWorkflow,
  ReferenceAsset,
  StageRevision,
  CreateCharacterRequest,
  SaveDraftRequest,
  CharacterApi,
} from "./characterTypes";
import type { GenerationResult, ErrorResponse } from "./types";
import { ApiError, issue } from "./errors";
import fixture0 from "../../tests/fixtures/contracts/v2/batch_manifest_completed.json";
import fixture1 from "../../tests/fixtures/contracts/v2/batch_manifest_failed.json";
import fixture2 from "../../tests/fixtures/contracts/v2/batch_manifest_partially_completed.json";
import fixture3 from "../../tests/fixtures/contracts/v2/batch_manifest_ready.json";
import fixture4 from "../../tests/fixtures/contracts/v2/batch_manifest_submitted.json";
import fixture5 from "../../tests/fixtures/contracts/v2/character.json";
import fixture6 from "../../tests/fixtures/contracts/v2/character_list.json";
import fixture7 from "../../tests/fixtures/contracts/v2/character_workflow.json";
import fixture8 from "../../tests/fixtures/contracts/v2/character_workflow_in_progress.json";
import fixture9 from "../../tests/fixtures/contracts/v2/error_approval_blocked.json";
import fixture10 from "../../tests/fixtures/contracts/v2/error_transition_invalid.json";
import fixture11 from "../../tests/fixtures/contracts/v2/example_batch_manifest.json";
import fixture12 from "../../tests/fixtures/contracts/v2/example_character.json";
import fixture13 from "../../tests/fixtures/contracts/v2/example_character_list.json";
import fixture14 from "../../tests/fixtures/contracts/v2/example_create_character_request.json";
import fixture15 from "../../tests/fixtures/contracts/v2/example_error_response.json";
import fixture16 from "../../tests/fixtures/contracts/v2/example_save_draft_request.json";
import fixture17 from "../../tests/fixtures/contracts/v2/history_page.json";
import fixture18 from "../../tests/fixtures/contracts/v2/job_batch_partial.json";
import fixture19 from "../../tests/fixtures/contracts/v2/outputs.json";
import fixture20 from "../../tests/fixtures/contracts/v2/reference_image.json";
import fixture21 from "../../tests/fixtures/contracts/v2/reference_url.json";
import fixture22 from "../../tests/fixtures/contracts/v2/stage_detail_s1.json";
import fixture23 from "../../tests/fixtures/contracts/v2/stage_detail_s2.json";
import fixture24 from "../../tests/fixtures/contracts/v2/stage_detail_s3.json";
import fixture25 from "../../tests/fixtures/contracts/v2/stage_detail_s4.json";
import fixture26 from "../../tests/fixtures/contracts/v2/stage_detail_s4_in_review.json";
import fixture27 from "../../tests/fixtures/contracts/v2/stage_detail_s5.json";
import fixture28 from "../../tests/fixtures/contracts/v2/stage_detail_s6.json";
import fixture29 from "../../tests/fixtures/contracts/v2/stage_detail_s7.json";
import fixture30 from "../../tests/fixtures/contracts/v2/stage_revision_s5.json";
import batchJobs from "../../tests/fixtures/contracts/v2/batch_jobs.json";
import fileIndex from "../../tests/fixtures/contracts/v2/files/index.json";

const fileUrls = import.meta.glob<string>(
  "../../tests/fixtures/contracts/v2/files/**/*.png",
  { query: "?url", import: "default", eager: true },
);
/** Bundled bytes from the same backend run as the JSON, never an API request. */
export async function sharedCharacterContent(path: string): Promise<Blob> {
  const missing = () =>
    new ApiError(
      {
        contract_version: path.startsWith("/api/v1/characters/")
          ? "1.1"
          : "1.0",
        errors: [issue("ARTIFACT_NOT_FOUND", null, "Artifact not found.")],
        warnings: [],
      },
      404,
    );
  const entry = Object.hasOwn(fileIndex, path)
    ? (fileIndex as Record<string, { file: string; mime_type: string }>)[path]
    : undefined;
  if (!entry) throw missing();
  const url = fileUrls[`../../tests/fixtures/contracts/v2/files/${entry.file}`];
  if (!url) throw missing();
  const response = await fetch(url);
  if (!response.ok) throw missing();
  const blob = await response.blob();
  return blob.slice(0, blob.size, entry.mime_type);
}

export interface SharedCharacterFixtureModels {
  batch_jobs: GenerationResult[];
  batch_manifest_completed: BatchManifest;
  batch_manifest_failed: BatchManifest;
  batch_manifest_partially_completed: BatchManifest;
  batch_manifest_ready: BatchManifest;
  batch_manifest_submitted: BatchManifest;
  character: Character;
  character_list: CharacterList;
  character_workflow: CharacterWorkflow;
  character_workflow_in_progress: CharacterWorkflow;
  error_approval_blocked: ErrorResponse;
  error_transition_invalid: ErrorResponse;
  example_batch_manifest: BatchManifest;
  example_character: Character;
  example_character_list: CharacterList;
  example_create_character_request: CreateCharacterRequest;
  example_error_response: ErrorResponse;
  example_save_draft_request: SaveDraftRequest;
  history_page: Awaited<ReturnType<CharacterApi["characterHistory"]>>;
  job_batch_partial: GenerationResult;
  outputs: Awaited<ReturnType<CharacterApi["characterOutputs"]>>;
  reference_image: ReferenceAsset;
  reference_url: ReferenceAsset;
  stage_detail_s1: StageDetail;
  stage_detail_s2: StageDetail;
  stage_detail_s3: StageDetail;
  stage_detail_s4: StageDetail;
  stage_detail_s4_in_review: StageDetail;
  stage_detail_s5: StageDetail;
  stage_detail_s6: StageDetail;
  stage_detail_s7: StageDetail;
  stage_revision_s5: StageRevision;
}
const fixtures = {
  batch_jobs: batchJobs,
  batch_manifest_completed: fixture0,
  batch_manifest_failed: fixture1,
  batch_manifest_partially_completed: fixture2,
  batch_manifest_ready: fixture3,
  batch_manifest_submitted: fixture4,
  character: fixture5,
  character_list: fixture6,
  character_workflow: fixture7,
  character_workflow_in_progress: fixture8,
  error_approval_blocked: fixture9,
  error_transition_invalid: fixture10,
  example_batch_manifest: fixture11,
  example_character: fixture12,
  example_character_list: fixture13,
  example_create_character_request: fixture14,
  example_error_response: fixture15,
  example_save_draft_request: fixture16,
  history_page: fixture17,
  job_batch_partial: fixture18,
  outputs: fixture19,
  reference_image: fixture20,
  reference_url: fixture21,
  stage_detail_s1: fixture22,
  stage_detail_s2: fixture23,
  stage_detail_s3: fixture24,
  stage_detail_s4: fixture25,
  stage_detail_s4_in_review: fixture26,
  stage_detail_s5: fixture27,
  stage_detail_s6: fixture28,
  stage_detail_s7: fixture29,
  stage_revision_s5: fixture30,
};

export type SharedCharacterFixtureName = keyof SharedCharacterFixtureModels;
/** Exact backend-validated snapshots. Every JSON name is mapped by test_contract_v2.py. */
export function sharedCharacterFixture<N extends SharedCharacterFixtureName>(
  name: N,
): SharedCharacterFixtureModels[N] {
  return structuredClone(
    fixtures[name],
  ) as unknown as SharedCharacterFixtureModels[N];
}
export const sharedCharacterFixtureNames = Object.keys(
  fixtures,
) as SharedCharacterFixtureName[];
