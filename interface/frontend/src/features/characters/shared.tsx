import { useEffect, useRef, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, isMock } from "../../api/client";
import type {
  ArtifactReference,
  EditorialStatus,
  ReferenceAsset,
  StageDetail,
  StageId,
} from "../../api/characterTypes";
import type { TranslationKey } from "../../i18n/en";
import { useI18n } from "../../i18n";
import { Badge, Failure, Issues, Loading } from "../../components/ui";
import { useBlobUrl } from "../../components/ArtifactPreview";
export const stageIds: StageId[] = ["s1", "s2", "s3", "s4", "s5", "s6", "s7"];
export const stageUrl = (id: string, sid: StageId) =>
  `/characters/${id}/stages/${sid}`;
export function FrozenThumbnail({
  characterId,
  assetId,
  alt,
}: {
  characterId: string;
  assetId: string;
  alt: string;
}) {
  const query = useQuery({
    queryKey: ["character-image", characterId, assetId],
    queryFn: () => api.assetContent(characterId, assetId),
    staleTime: Infinity,
  });
  const url = useBlobUrl(query.data);
  return query.error ? (
    <Failure error={query.error} />
  ) : url ? (
    <img src={url} alt={alt} />
  ) : null;
}
export function useStage(id: string, sid: StageId) {
  return useQuery({
    queryKey: ["character-stage", id, sid],
    queryFn: () => api.stage(id, sid),
  });
}
export function useCharacterText() {
  const i18n = useI18n();
  return { ...i18n, text: (key: string) => i18n.t(key as TranslationKey) };
}
export function CharacterMode() {
  const { t } = useI18n();
  return (
    <div className="character-mode">
      <Badge tone="info">
        {isMock ? t("char.demo") : t("char.productionHelp")}
      </Badge>
      {isMock && <span>{t("char.demoHelp")}</span>}
    </div>
  );
}
export function EditorialStatus({ status }: { status: EditorialStatus }) {
  const { label } = useI18n();
  return (
    <Badge
      tone={
        status === "approved"
          ? "success"
          : status === "needs_revision" || status === "blocked"
            ? "warning"
            : "info"
      }
    >
      <span aria-hidden="true">
        {status === "approved" ? "✓" : status === "blocked" ? "!" : "○"}
      </span>
      {label("editorial", status)}
    </Badge>
  );
}
export function ImageAsset({
  characterId,
  asset,
  reference = false,
  showCover = false,
}: {
  characterId: string;
  asset: ArtifactReference | ReferenceAsset;
  reference?: boolean;
  showCover?: boolean;
}) {
  const { t, label } = useI18n();
  const cache = useQueryClient();
  const cover = useMutation({
    mutationFn: async () => {
      const workflow = await api.character(characterId);
      return api.updateCharacter(characterId, {
        contract_version: "1.1",
        expected_version: workflow.character.version,
        cover_asset_id: "asset_id" in asset ? asset.asset_id : undefined,
      });
    },
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ["character", characterId] });
      void cache.invalidateQueries({ queryKey: ["characters"] });
    },
  });
  const aid = "asset_id" in asset ? asset.asset_id : asset.reference_id;
  const query = useQuery({
    queryKey: ["character-image", characterId, aid],
    queryFn: () =>
      reference
        ? api.referenceContent(characterId, aid)
        : api.assetContent(characterId, aid),
    staleTime: Infinity,
  });
  const url = useBlobUrl(query.data);
  return (
    <figure className="character-image">
      {query.error ? (
        <Failure error={query.error} />
      ) : url ? (
        <a
          href={url}
          target="_blank"
          rel="noreferrer"
          title={t("char.viewImage")}
        >
          <img
            src={url}
            alt={
              reference && "title" in asset
                ? asset.title
                : label("purpose", asset.purpose)
            }
          />
        </a>
      ) : (
        <Loading />
      )}
      <figcaption>
        <span>
          {reference ? t("char.reference") : t("char.frozen")} ·{" "}
          {label("purpose", asset.purpose)}
        </span>
        {url && (
          <a href={url} download={`${aid}.png`}>
            {t("char.download")}
          </a>
        )}
      </figcaption>
      {!reference && showCover && (
        <button disabled={cover.isPending} onClick={() => cover.mutate()}>
          {t("char.setCover")}
        </button>
      )}
      {cover.error && <Failure error={cover.error} />}
      {"source" in asset && asset.source && (
        <details>
          <summary>{t("char.provenance")}</summary>
          <dl className="properties">
            <dt>{t("char.model")}</dt>
            <dd>{asset.source.model_id}</dd>
            <dt>{t("char.seed")}</dt>
            <dd>{asset.source.seed ?? t("common.unknown")}</dd>
            <dt>{t("char.width")}</dt>
            <dd>{asset.source.width}</dd>
            <dt>{t("char.height")}</dt>
            <dd>{asset.source.height}</dd>
          </dl>
          <code className="break-word">
            {asset.source.job_id}
            <br />
            {asset.sha256}
          </code>
          <p>{asset.source.prompt}</p>
        </details>
      )}
    </figure>
  );
}
export function StageInputs({ detail }: { detail: StageDetail }) {
  const { t, text } = useCharacterText();
  return (
    <div className="character-stack">
      {detail.inputs.length === 0 && <p className="muted">{t("char.none")}</p>}
      {detail.inputs.map((input) => (
        <section className="character-inset" key={input.stage_id}>
          <h3>
            {input.stage_id.toUpperCase()} ·{" "}
            {text(`stage.${input.stage_id}.title`)}
          </h3>
          <p>
            {input.revision
              ? t("char.revision", { revision: input.revision })
              : t("char.missingInput")}
          </p>
          {input.content && (
            <details>
              <summary>{t("char.inputs")}</summary>
              <ContentSummary content={input.content} />
            </details>
          )}
          {input.frozen_assets.map((asset) => (
            <ImageAsset
              key={asset.asset_id}
              characterId={detail.character.character_id}
              asset={asset}
            />
          ))}
        </section>
      ))}
      {detail.references.map((ref) =>
        ref.kind === "image" ? (
          <ImageAsset
            key={ref.reference_id}
            characterId={detail.character.character_id}
            asset={ref}
            reference
          />
        ) : (
          <div className="character-inset" key={ref.reference_id}>
            <a href={ref.url ?? undefined} target="_blank" rel="noreferrer">
              {ref.title}
            </a>
            <p className="break-word">{ref.url}</p>
          </div>
        ),
      )}
    </div>
  );
}
export function ContentSummary({
  content,
}: {
  content: StageDetail["draft"]["content"];
}) {
  const { t, label } = useI18n();
  switch (content.stage_id) {
    case "s1":
      return (
        <>
          <p>{content.idea}</p>
          <ul>
            {content.directions.map((d, i) => (
              <li key={i}>{d}</li>
            ))}
          </ul>
          <p>{content.notes}</p>
        </>
      );
    case "s2":
      return (
        <>
          <p>{content.summary}</p>
          {content.attributes.map((a) => (
            <p key={a.attribute_id}>
              <strong>{a.label}</strong> · {label("lock", a.lock)}
              <br />
              {a.value}
            </p>
          ))}
        </>
      );
    case "s3":
      return (
        <>
          <p>{content.preview_prompt}</p>
          <p>{content.review_notes}</p>
        </>
      );
    case "s4":
      return (
        <>
          {content.entries.map((e) => (
            <section key={e.purpose}>
              <h3>{label("purpose", e.purpose)}</h3>
              <p>{e.canonical_prompt}</p>
            </section>
          ))}
        </>
      );
    case "s5":
      return <p>{content.consistency_notes ?? t("char.none")}</p>;
    default:
      return <p>{content.notes ?? t("char.planned")}</p>;
  }
}
export function History({ id, stage }: { id: string; stage?: StageId }) {
  const { t, label, date } = useI18n();
  const q = useQuery({
    queryKey: ["character-history", id],
    queryFn: () => api.characterHistory(id),
  });
  return (
    <div className="character-history">
      {q.error ? (
        <Failure error={q.error} />
      ) : (
        q.data?.events
          .filter(
            (e) =>
              !stage ||
              e.stage_id === stage ||
              e.affected_stages.includes(stage),
          )
          .slice(0, 12)
          .map((e) => (
            <div key={e.seq}>
              <span>
                {label("historyAction", e.action)}{" "}
                {e.revision ? t("char.revision", { revision: e.revision }) : ""}
              </span>
              <small>{date(e.at)}</small>
              {e.note && <p>{e.note}</p>}
            </div>
          ))
      )}
      {q.data && !q.data.events.some((e) => !stage || e.stage_id === stage) && (
        <p className="muted">{t("char.none")}</p>
      )}
    </div>
  );
}
export function StageFacts({ detail }: { detail: StageDetail }) {
  const { t, text } = useCharacterText();
  return (
    <>
      <h3>{t("char.objective")}</h3>
      <p>{text(detail.config.objective_key)}</p>
      <EditorialStatus status={detail.state.editorial_status} />
      <p>
        {t("char.draftVersion", { version: detail.state.draft_version })}
        {detail.state.approved
          ? ` · ${t("char.revision", { revision: detail.state.approved.revision })}`
          : ""}
      </p>
      {detail.state.approved?.stale_reasons.map((r) => (
        <p className="notice warning" key={r.upstream_stage_id}>
          {t("char.stale", {
            stage: r.upstream_stage_id.toUpperCase(),
            used: r.used_revision,
            current: r.current_revision,
          })}
        </p>
      ))}
      <h3>{t("char.blockers")}</h3>
      <Issues items={detail.state.blockers} />
      {!detail.state.blockers.length && <p>{t("char.none")}</p>}
    </>
  );
}
export function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current!;
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute("open", "");
    return () => {
      dialog.close?.();
    };
  }, []);
  return (
    <dialog
      className="character-dialog"
      ref={ref}
      aria-label={title}
      onCancel={onClose}
    >
      <h2>{title}</h2>
      {children}
    </dialog>
  );
}
export function StageLinks({ id, stage }: { id: string; stage: StageId }) {
  const { t } = useI18n();
  const index = stageIds.indexOf(stage);
  return (
    <div className="character-actions">
      {index > 0 && (
        <Link className="button" to={stageUrl(id, stageIds[index - 1])}>
          {t("char.prev")}
        </Link>
      )}
      <Link className="button" to={`/characters/${id}?node=${stage}`}>
        {t("char.back")}
      </Link>
      {index < 6 && (
        <Link className="button" to={stageUrl(id, stageIds[index + 1])}>
          {t("char.next")}
        </Link>
      )}
    </div>
  );
}
