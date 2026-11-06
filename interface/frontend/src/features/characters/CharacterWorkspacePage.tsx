import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { Badge, Failure, Loading, Panel } from "../../components/ui";
import { WorkflowCanvas } from "./WorkflowCanvas";
import {
  CharacterMode,
  EditorialStatus,
  History,
  ImageAsset,
  Modal,
  StageFacts,
  StageInputs,
  stageIds,
  stageUrl,
  useCharacterText,
  useStage,
} from "./shared";
import type { StageId } from "../../api/characterTypes";
export function CharacterWorkspacePage() {
  const { characterId = "" } = useParams(),
    [params, setParams] = useSearchParams(),
    { t, text } = useCharacterText(),
    cache = useQueryClient();
  const query = useQuery({
    queryKey: ["character", characterId],
    queryFn: () => api.character(characterId),
  });
  const [rename, setRename] = useState(false),
    [name, setName] = useState("");
  const update = useMutation({
    mutationFn: () =>
      api.updateCharacter(characterId, {
        contract_version: "1.1",
        expected_version: query.data!.character.version,
        name,
      }),
    onSuccess: () => {
      setRename(false);
      void cache.invalidateQueries({ queryKey: ["character", characterId] });
      void cache.invalidateQueries({ queryKey: ["characters"] });
    },
  });
  if (query.error) return <Failure error={query.error} />;
  if (!query.data) return <Loading />;
  const { character, stages } = query.data;
  const node = params.get("node"),
    selected = stageIds.includes(node as StageId)
      ? (node as StageId)
      : (stages.find((s) => s.state.editorial_status !== "approved")?.config
          .stage_id ?? "s1");
  return (
    <div className="characters-feature">
      <div className="breadcrumb">
        <Link to="/characters">{t("char.characters")}</Link> / {character.name}
      </div>
      <div className="character-identity">
        <div>
          <CharacterMode />
          <h1>{character.name}</h1>
          <code>{character.character_id}</code>
          <p>{character.summary}</p>
          <div className="character-tags">
            {character.tags.map((tag) => (
              <span key={tag}>{tag}</span>
            ))}
          </div>
        </div>
        <div>
          <Badge>
            {t("char.approvedCount", {
              count: stages.filter(
                (s) => s.state.editorial_status === "approved",
              ).length,
            })}
          </Badge>
          <div className="character-actions">
            <button
              onClick={() => {
                setName(character.name);
                setRename(true);
              }}
            >
              {t("char.rename")}
            </button>
            <Link className="button" to="/generate/text-to-2d">
              {t("copy.generateStudio")}
            </Link>
            <Link
              className="button primary"
              to={stageUrl(characterId, selected)}
            >
              {t("char.openStage")}
            </Link>
          </div>
        </div>
      </div>
      <div className="character-workspace">
        <WorkflowCanvas
          characterId={characterId}
          outputs={query.data.approved_outputs}
          stages={stages}
          selected={selected}
          onSelect={(sid) => {
            const next = new URLSearchParams(params);
            next.set("node", sid);
            setParams(next, { replace: true, preventScrollReset: true });
          }}
        />
        <FlowInspector id={characterId} stage={selected} />
      </div>
      {rename && (
        <Modal title={t("char.rename")} onClose={() => setRename(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              update.mutate();
            }}
          >
            <label className="field">
              {t("char.name")}
              <input
                autoFocus
                value={name}
                maxLength={80}
                required
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            {update.error && <Failure error={update.error} />}
            <div className="character-actions">
              <button type="button" onClick={() => setRename(false)}>
                {t("char.cancel")}
              </button>
              <button disabled={update.isPending || !name.trim()}>
                {t("char.rename")}
              </button>
            </div>
          </form>
        </Modal>
      )}
      <span className="sr-only">{text(`stage.${selected}.title`)}</span>
    </div>
  );
}
function FlowInspector({ id, stage }: { id: string; stage: StageId }) {
  const { t, text } = useCharacterText(),
    data = useStage(id, stage);
  return (
    <Panel
      title={t("char.inspector")}
      className="flow-inspector"
      extra={<Badge>{stage.toUpperCase()}</Badge>}
    >
      <div
        className="panel-body"
        data-testid="flow-inspector"
        data-stage={stage}
      >
        {data.error ? (
          <Failure error={data.error} />
        ) : !data.data ? (
          <Loading />
        ) : (
          <>
            <h2>{text(data.data.config.title_key)}</h2>
            <StageFacts detail={data.data} />
            <h3>{t("char.inputs")}</h3>
            <StageInputs detail={data.data} />
            <h3>{t("char.outputs")}</h3>
            {data.data.approved_revision?.frozen_assets.map((a) => (
              <ImageAsset key={a.asset_id} characterId={id} asset={a} />
            ))}
            {!data.data.approved_revision?.frozen_assets.length && (
              <p>{t("char.noOutput")}</p>
            )}
            <h3>{t("char.checklist")}</h3>
            <ul className="character-checklist">
              {data.data.config.checklist.map((c) => (
                <li key={c.item_id}>
                  <span aria-hidden="true">
                    {data.data!.draft.checklist.items.some(
                      (i) => i.item_id === c.item_id && i.checked,
                    )
                      ? "✓"
                      : "○"}
                  </span>
                  {text(c.label_key)}
                </li>
              ))}
            </ul>
            <h3>{t("char.history")}</h3>
            <History id={id} stage={stage} />
            <Link className="button" to={stageUrl(id, stage)}>
              {t("char.openStage")}
            </Link>
            {stage !== "s7" && (
              <p>
                {t("char.next")}:{" "}
                {text(`stage.${stageIds[stageIds.indexOf(stage) + 1]}.title`)}
              </p>
            )}
            <EditorialStatus status={data.data.state.editorial_status} />
          </>
        )}
      </div>
    </Panel>
  );
}
