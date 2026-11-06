import type {
  CharacterApi,
  CharacterFilters,
  CharacterList,
  Character,
  CharacterWorkflow,
  StageDetail,
  StageId,
  StageRevision,
  StageHistory,
  ReferenceAsset,
  ArtifactReference,
  BatchManifest,
  CreateCharacterRequest,
  UpdateCharacterRequest,
  SaveDraftRequest,
  StageDecisionRequest,
  CreateReferenceRequest,
  CreatePreviewBatchRequest,
  SubmitBatchRequest,
} from "./characterTypes";
import type { ErrorResponse } from "./types";
import { ApiError } from "./errors";
const idPath = (id: string) => `/characters/${encodeURIComponent(id)}`;
const stagePath = (id: string, stage: StageId) =>
  `${idPath(id)}/stages/${encodeURIComponent(stage)}`;
export class HttpCharacterApi implements CharacterApi {
  constructor(private characterBase = "http://127.0.0.1:8000/api/v1") {}
  private async characterRequest<T>(
    path: string,
    method = "GET",
    body?: unknown,
    bytes = false,
  ): Promise<T> {
    const response = await fetch(`${this.characterBase}${path}`, {
      method,
      headers:
        body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok)
      throw new ApiError(
        (await response.json()) as ErrorResponse,
        response.status,
      );
    return response.status === 204
      ? (undefined as T)
      : bytes
        ? ((await response.blob()) as T)
        : (response.json() as Promise<T>);
  }
  characters(filters: CharacterFilters = {}) {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([k, v]) => {
      if (v !== undefined && v !== "") params.set(k, String(v));
    });
    return this.characterRequest<CharacterList>(`/characters?${params}`);
  }
  createCharacter(body: CreateCharacterRequest) {
    return this.characterRequest<Character>("/characters", "POST", body);
  }
  character(id: string) {
    return this.characterRequest<CharacterWorkflow>(idPath(id));
  }
  deleteCharacter(id: string) {
    return this.characterRequest<void>(idPath(id), "DELETE");
  }
  updateCharacter(id: string, body: UpdateCharacterRequest) {
    return this.characterRequest<Character>(idPath(id), "PATCH", body);
  }
  stage(id: string, stage: StageId) {
    return this.characterRequest<StageDetail>(stagePath(id, stage));
  }
  saveStage(id: string, stage: StageId, body: SaveDraftRequest) {
    return this.characterRequest<StageDetail>(
      `${stagePath(id, stage)}/draft`,
      "PUT",
      body,
    );
  }
  decideStage(id: string, stage: StageId, body: StageDecisionRequest) {
    return this.characterRequest<StageDetail>(
      `${stagePath(id, stage)}/decisions`,
      "POST",
      body,
    );
  }
  stageRevision(id: string, stage: StageId, revision: number) {
    return this.characterRequest<StageRevision>(
      `${stagePath(id, stage)}/revisions/${revision}`,
    );
  }
  characterHistory(id: string, limit = 100, cursor = "") {
    return this.characterRequest<{
      contract_version: "1.1";
      events: StageHistory[];
      next_cursor: string | null;
    }>(
      `${idPath(id)}/history?${new URLSearchParams({ limit: String(limit), cursor })}`,
    );
  }
  createReference(id: string, body: CreateReferenceRequest) {
    return this.characterRequest<ReferenceAsset>(
      `${idPath(id)}/references`,
      "POST",
      body,
    );
  }
  referenceContent(id: string, reference: string) {
    return this.characterRequest<Blob>(
      `${idPath(id)}/references/${encodeURIComponent(reference)}/content`,
      "GET",
      undefined,
      true,
    );
  }
  deleteReference(id: string, reference: string) {
    return this.characterRequest<void>(
      `${idPath(id)}/references/${encodeURIComponent(reference)}`,
      "DELETE",
    );
  }
  characterOutputs(id: string) {
    return this.characterRequest<{
      contract_version: "1.1";
      outputs: ArtifactReference[];
    }>(`${idPath(id)}/outputs`);
  }
  assetContent(id: string, asset: string, download = false) {
    return this.characterRequest<Blob>(
      `${idPath(id)}/assets/${encodeURIComponent(asset)}/content?download=${download ? 1 : 0}`,
      "GET",
      undefined,
      true,
    );
  }
  createPreviewBatch(id: string, body: CreatePreviewBatchRequest) {
    return this.characterRequest<BatchManifest>(
      `${idPath(id)}/batches`,
      "POST",
      body,
    );
  }
  characterBatch(id: string, manifest: string) {
    return this.characterRequest<BatchManifest>(
      `${idPath(id)}/batches/${encodeURIComponent(manifest)}`,
    );
  }
  submitCharacterBatch(id: string, manifest: string, body: SubmitBatchRequest) {
    return this.characterRequest<BatchManifest>(
      `${idPath(id)}/batches/${encodeURIComponent(manifest)}/submit`,
      "POST",
      body,
    );
  }
  retryCharacterBatch(id: string, manifest: string, body: SubmitBatchRequest) {
    return this.characterRequest<BatchManifest>(
      `${idPath(id)}/batches/${encodeURIComponent(manifest)}/retry`,
      "POST",
      body,
    );
  }
}
