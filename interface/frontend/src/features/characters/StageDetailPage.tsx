import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import { ApiError } from "../../api/errors";
import type {
  StageContent,
  StageDetail,
  StageDraft,
  StageId,
  StageRevision,
  StageDecisionRequest,
} from "../../api/characterTypes";
import { Badge, Failure, Loading, Panel } from "../../components/ui";
import {
  CharacterMode,
  ContentSummary,
  History,
  ImageAsset,
  Modal,
  StageFacts,
  StageInputs,
  StageLinks,
  stageIds,
  useCharacterText,
  useStage,
} from "./shared";
import { Field, StageContentRenderer } from "./StageContentRenderer";
function useUnsaved(dirty: boolean, message: string) {
  useEffect(() => {
    if (!dirty) return;
    const unload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    const click = (e: MouseEvent) => {
      const a = (e.target as Element).closest?.("a");
      if (
        a &&
        a.target !== "_blank" &&
        !a.download &&
        !e.ctrlKey &&
        !e.metaKey &&
        !e.shiftKey &&
        e.button === 0 &&
        a.href !== window.location.href &&
        (a.pathname !== window.location.pathname ||
          a.search !== window.location.search) &&
        !window.confirm(message)
      ) {
        e.preventDefault();
        e.stopImmediatePropagation();
      }
    };
    let index = window.history.state?.idx ?? 0;
    let restoring = false;
    const pop = (e: PopStateEvent) => {
      const next = e.state?.idx ?? 0;
      if (restoring) {
        restoring = false;
        e.stopImmediatePropagation();
        return;
      }
      if (next !== index && !window.confirm(message)) {
        e.stopImmediatePropagation();
        restoring = true;
        window.history.go(index - next);
      } else index = next;
    };
    window.addEventListener("beforeunload", unload);
    document.addEventListener("click", click, true);
    window.addEventListener("popstate", pop, true);
    return () => {
      window.removeEventListener("beforeunload", unload);
      document.removeEventListener("click", click, true);
      window.removeEventListener("popstate", pop, true);
    };
  }, [dirty, message]);
}
export function StageDetailPage() {
  const { characterId = "", stageId = "" } = useParams();
  const { t } = useCharacterText();
  if (!stageIds.includes(stageId as StageId))
    return (
      <div className="characters-feature">
        <h1>{t("copy.pageNotFound")}</h1>
        <Link to={`/characters/${characterId}`}>{t("char.back")}</Link>
      </div>
    );
  return (
    <StageLoader
      key={`${characterId}/${stageId}`}
      id={characterId}
      sid={stageId as StageId}
    />
  );
}
function StageLoader({ id, sid }: { id: string; sid: StageId }) {
  const query = useStage(id, sid);
  return !query.data ? (
    query.error ? (
      <Failure error={query.error} />
    ) : (
      <Loading />
    )
  ) : (
    <>
      {query.error && <Failure error={query.error} />}
      <StageForm
        detail={query.data}
        reload={async () => {
          const result = await query.refetch();
          if (result.data) return result.data;
          throw result.error;
        }}
      />
    </>
  );
}
function StageForm({
  detail,
  reload,
}: {
  detail: StageDetail;
  reload: () => Promise<StageDetail>;
}) {
  const { t, text, label } = useCharacterText(),
    cache = useQueryClient();
  const [draft, setDraft] = useState<StageDraft>(() =>
      structuredClone(detail.draft),
    ),
    baseline = useRef(JSON.stringify(detail.draft)),
    [fieldErrors, setFieldErrors] = useState<Record<string, string>>({}),
    [note, setNote] = useState(""),
    [feedback, setFeedback] = useState(""),
    [revision, setRevision] = useState<StageRevision | null>(null);
  const dirty = JSON.stringify(draft) !== baseline.current,
    available = detail.config.availability === "available";
  const [localDirty, setLocalDirty] = useState<Record<string, boolean>>({});
  const [editorEpoch, setEditorEpoch] = useState(0);
  const navigationDirty =
    dirty ||
    Object.keys(fieldErrors).length > 0 ||
    Object.values(localDirty).some(Boolean) ||
    !!note.trim();
  useUnsaved(navigationDirty, t("char.unsaved"));
  const refresh = (value: StageDetail) => {
    setDraft(structuredClone(value.draft));
    baseline.current = JSON.stringify(value.draft);
    cache.setQueryData(
      [
        "character-stage",
        detail.character.character_id,
        detail.config.stage_id,
      ],
      value,
    );
    void cache.invalidateQueries({
      queryKey: ["character", detail.character.character_id],
    });
    void cache.invalidateQueries({ queryKey: ["characters"] });
    void cache.invalidateQueries({
      queryKey: ["character-history", detail.character.character_id],
    });
  };
  const save = useMutation({
    mutationFn: () =>
      api.saveStage(detail.character.character_id, detail.config.stage_id, {
        contract_version: "1.1",
        expected_draft_version: draft.draft_version,
        content: draft.content,
        checklist: draft.checklist,
      }),
    onSuccess: (value) => {
      refresh(value);
      setFeedback(t("char.saved"));
    },
  });
  const decide = useMutation({
    mutationFn: (action: StageDecisionRequest["action"]) =>
      api.decideStage(detail.character.character_id, detail.config.stage_id, {
        contract_version: "1.1",
        expected_draft_version: draft.draft_version,
        action,
        revision: detail.state.pending_revision,
        note: note || null,
      }),
    onSuccess: (value) => {
      refresh(value);
      setFeedback(t("char.decisionSaved"));
      setNote("");
    },
  });
  const oldRevision = useMutation({
    mutationFn: (n: number) =>
      api.stageRevision(
        detail.character.character_id,
        detail.config.stage_id,
        n,
      ),
    onSuccess: setRevision,
  });
  const reloadData = useMutation({
    mutationFn: reload,
    onSuccess: (value) => {
      refresh(value);
      save.reset();
      decide.reset();
      setFieldErrors({});
      setLocalDirty({});
      setEditorEpoch((n) => n + 1);
      setNote("");
      setFeedback("");
    },
  });
  const pending = save.isPending || decide.isPending || reloadData.isPending;
  const error = save.error ?? decide.error ?? reloadData.error;
  const conflict = error instanceof ApiError && error.status === 409;
  const change = (content: StageContent) => {
    setDraft((d) => ({ ...d, content }));
    setFeedback("");
  };
  return (
    <div className="characters-feature">
      <div className="breadcrumb">
        <Link to="/characters">{t("char.characters")}</Link> /{" "}
        <Link
          to={`/characters/${detail.character.character_id}?node=${detail.config.stage_id}`}
        >
          {detail.character.name}
        </Link>{" "}
        / {detail.config.stage_id.toUpperCase()}
      </div>
      <div className="page-heading">
        <div>
          <h1>
            {detail.config.stage_id.toUpperCase()} ·{" "}
            {text(detail.config.title_key)}
          </h1>
          <CharacterMode />
        </div>
        <StageLinks
          id={detail.character.character_id}
          stage={detail.config.stage_id}
        />
      </div>
      <div className="character-stage-bar">
        <Badge>
          {t("char.draftVersion", { version: draft.draft_version })}
        </Badge>
        {navigationDirty && <Badge tone="warning">{t("char.dirty")}</Badge>}
        {!available && <Badge tone="warning">{t("char.planned")}</Badge>}
        <button
          disabled={
            !available ||
            pending ||
            Object.keys(fieldErrors).length > 0 ||
            !dirty
          }
          onClick={() => save.mutate()}
        >
          {t("char.save")}
        </button>
        <button
          disabled={
            !available ||
            dirty ||
            pending ||
            !draft.draft_version ||
            !!detail.state.pending_revision
          }
          onClick={() => decide.mutate("submit")}
        >
          {t("char.submit")}
        </button>
        <button
          className="primary"
          disabled={
            !available ||
            dirty ||
            pending ||
            !detail.state.pending_revision ||
            detail.state.blockers.length > 0
          }
          onClick={() => decide.mutate("approve")}
        >
          {t("char.approve")}
        </button>
        <span role="status">{feedback}</span>
      </div>
      {error && <Failure error={error} />}{" "}
      {conflict && <p className="notice warning">{t("char.conflict")}</p>}
      <button
        disabled={pending}
        onClick={() => {
          if (!navigationDirty || window.confirm(t("char.unsaved")))
            reloadData.mutate();
        }}
      >
        {t("char.reload")}
      </button>
      {Object.values(fieldErrors).map((message, i) => (
        <p key={i} className="notice danger" role="alert">
          {message}
        </p>
      ))}
      <div className="character-stage-layout">
        <Panel title={t("char.inputs")} className="character-inputs">
          <div className="panel-body">
            <StageInputs detail={detail} />
          </div>
        </Panel>
        <Panel title={t("char.working")} className="character-working">
          <div className="panel-body">
            <StageContentRenderer
              key={`${detail.config.stage_id}-${editorEpoch}`}
              content={draft.content}
              detail={detail}
              dirty={dirty}
              setLocalDirty={(key, value) =>
                setLocalDirty((state) => ({ ...state, [key]: value }))
              }
              change={change}
              setError={(key, message) =>
                setFieldErrors((errors) => {
                  const next = { ...errors };
                  if (message) next[key] = message;
                  else delete next[key];
                  return next;
                })
              }
            />
          </div>
        </Panel>
        <Panel title={t("char.checklist")} className="character-approval">
          <div className="panel-body">
            <StageFacts detail={detail} />
            <h3>{t("char.checklist")}</h3>
            <div className="character-stack">
              {detail.config.checklist.map((c) => (
                <label className="character-checkbox" key={c.item_id}>
                  <input
                    type="checkbox"
                    disabled={
                      !available || pending || !!detail.state.pending_revision
                    }
                    checked={draft.checklist.items.some(
                      (i) => i.item_id === c.item_id && i.checked,
                    )}
                    onChange={(e) =>
                      setDraft((d) => ({
                        ...d,
                        checklist: {
                          items: [
                            ...d.checklist.items.filter(
                              (i) => i.item_id !== c.item_id,
                            ),
                            {
                              item_id: c.item_id,
                              checked: e.target.checked,
                              note: null,
                            },
                          ],
                        },
                      }))
                    }
                  />
                  <span>
                    {text(c.label_key)}{" "}
                    {c.required && <small>({t("char.required")})</small>}
                  </span>
                </label>
              ))}
            </div>
            <Field title={t("char.note")}>
              <textarea
                maxLength={2000}
                disabled={!available}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </Field>
            <div className="character-actions">
              <button
                disabled={
                  !available ||
                  dirty ||
                  pending ||
                  (!detail.state.pending_revision && !detail.state.approved)
                }
                onClick={() => decide.mutate("request_revision")}
              >
                {t("char.requestRevision")}
              </button>
              <button
                disabled={
                  !available ||
                  dirty ||
                  pending ||
                  !detail.state.pending_revision
                }
                onClick={() => decide.mutate("withdraw")}
              >
                {t("char.withdraw")}
              </button>
            </div>
            <h3>
              {t("char.revision", {
                revision: detail.state.latest_revision ?? 0,
              })}
            </h3>
            {detail.revisions.map((r) => (
              <button
                className="character-revision"
                key={r.revision}
                onClick={() => oldRevision.mutate(r.revision)}
              >
                {t("char.revision", { revision: r.revision })} ·{" "}
                {label("revisionDecision", r.decision)}
              </button>
            ))}
            {oldRevision.error && <Failure error={oldRevision.error} />}
            <h3>{t("char.outputs")}</h3>
            {detail.approved_revision?.frozen_assets.map((a) => (
              <ImageAsset
                key={a.asset_id}
                characterId={detail.character.character_id}
                asset={a}
                showCover
              />
            ))}
            <h3>{t("char.history")}</h3>
            <History
              id={detail.character.character_id}
              stage={detail.config.stage_id}
            />
          </div>
        </Panel>
      </div>
      {revision && (
        <Modal
          title={t("char.revision", { revision: revision.revision })}
          onClose={() => setRevision(null)}
        >
          <ContentSummary content={revision.content} />
          <button onClick={() => setRevision(null)}>{t("char.close")}</button>
        </Modal>
      )}
    </div>
  );
}
