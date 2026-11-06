import { useState } from "react";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { Plus, UserRound } from "lucide-react";
import { api } from "../../api/client";
import type { EditorialStatus, StageId } from "../../api/characterTypes";
import { useI18n } from "../../i18n";
import { Empty, Failure, Loading } from "../../components/ui";
import {
  CharacterMode,
  FrozenThumbnail,
  EditorialStatus as Status,
  Modal,
  stageIds,
} from "./shared";
export function CharacterLibraryPage() {
  const { t, label, date, number } = useI18n(),
    nav = useNavigate(),
    cache = useQueryClient();
  const [q, setQ] = useState(""),
    [stage, setStage] = useState(""),
    [status, setStatus] = useState(""),
    [tag, setTag] = useState(""),
    [creating, setCreating] = useState(false),
    [name, setName] = useState(""),
    [tags, setTags] = useState(""),
    [summary, setSummary] = useState(""),
    [list, setList] = useState(false);
  const data = useInfiniteQuery({
    queryKey: ["characters", q, stage, status],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      api.characters({
        q,
        stage: (stage as StageId) || undefined,
        status: (status as EditorialStatus) || undefined,
        cursor: pageParam,
      }),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
  });
  const rows = data.data?.pages.flatMap((p) => p.characters) ?? [],
    visible = rows.filter((c) => !tag || c.tags.includes(tag));
  const create = useMutation({
    mutationFn: () =>
      api.createCharacter({
        contract_version: "1.1",
        client_request_id: crypto.randomUUID(),
        name,
        summary: summary || null,
        tags: tags
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      }),
    onSuccess: (c) => {
      void cache.invalidateQueries({ queryKey: ["characters"] });
      nav(`/characters/${c.character_id}`);
    },
  });
  return (
    <div className="characters-feature">
      <div className="page-heading">
        <div>
          <h1>{t("char.characters")}</h1>
          <CharacterMode />
        </div>
        <button className="primary" onClick={() => setCreating(true)}>
          <Plus size={16} />
          {t("char.create")}
        </button>
      </div>
      <div className="character-summary">
        <span>
          {t("char.characters")} <strong>{number(rows.length, 0)}</strong>
        </span>
        <span>
          {label("editorial", "draft")}{" "}
          <strong>
            {number(
              rows.filter((c) => c.stage_statuses[c.current_stage] === "draft")
                .length,
              0,
            )}
          </strong>
        </span>
        <span>
          {label("editorial", "in_review")}{" "}
          <strong>
            {number(
              rows.filter(
                (c) => c.stage_statuses[c.current_stage] === "in_review",
              ).length,
              0,
            )}
          </strong>
        </span>
      </div>
      <div className="character-filters">
        <label>
          {t("char.search")}
          <input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        <label>
          {t("char.style")}
          <select value={tag} onChange={(e) => setTag(e.target.value)}>
            <option value="">{t("char.all")}</option>
            {[...new Set(rows.flatMap((c) => c.tags))].sort().map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
        <label>
          {t("char.stage")}
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">{t("char.all")}</option>
            {stageIds.map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()} · {label("stage", `${s}.title`)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t("char.status")}
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">{t("char.all")}</option>
            {[
              "not_started",
              "draft",
              "in_review",
              "approved",
              "needs_revision",
              "blocked",
            ].map((s) => (
              <option key={s} value={s}>
                {label("editorial", s)}
              </option>
            ))}
          </select>
        </label>
        <button aria-pressed={list} onClick={() => setList((v) => !v)}>
          {list ? t("char.grid") : t("char.list")}
        </button>
      </div>
      {data.isPending ? (
        <Loading />
      ) : data.error ? (
        <Failure error={data.error} />
      ) : !visible.length ? (
        <Empty title={t("char.empty")}>{t("char.emptyHelp")}</Empty>
      ) : (
        <div className={`character-library ${list ? "as-list" : ""}`}>
          {visible.map((c) => (
            <article className="character-card" key={c.character_id}>
              <Link
                to={`/characters/${c.character_id}`}
                className="character-cover"
                aria-label={`${t("char.open")}: ${c.name} · ${c.current_stage.toUpperCase()}`}
              >
                {c.cover_url ? (
                  <FrozenThumbnail
                    characterId={c.character_id}
                    assetId={
                      c.cover_url.split("/assets/")[1]?.split("/")[0] ?? ""
                    }
                    alt={c.name}
                  />
                ) : (
                  <UserRound size={64} aria-hidden="true" />
                )}
                <span>{c.current_stage.toUpperCase()}</span>
              </Link>
              <div className="character-card-body">
                <h2>
                  <Link to={`/characters/${c.character_id}`}>{c.name}</Link>
                </h2>
                <code>{c.character_id}</code>
                <div className="character-tags">
                  {c.tags.map((s) => (
                    <span key={s}>{s}</span>
                  ))}
                </div>
                <Status status={c.stage_statuses[c.current_stage]} />
                <p>{t("char.approvedCount", { count: c.approved_count })}</p>
                <div className="character-progress" aria-hidden="true">
                  {stageIds.map((s) => (
                    <span
                      key={s}
                      data-approved={c.stage_statuses[s] === "approved"}
                    />
                  ))}
                </div>
                <small>{t("char.updated", { date: date(c.updated_at) })}</small>
                <Link className="button" to={`/characters/${c.character_id}`}>
                  {t("char.open")}
                </Link>
              </div>
            </article>
          ))}
        </div>
      )}
      {data.hasNextPage && (
        <button
          onClick={() => void data.fetchNextPage()}
          disabled={data.isFetchingNextPage}
        >
          {t("char.more")}
        </button>
      )}
      {creating && (
        <Modal title={t("char.create")} onClose={() => setCreating(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <label className="field">
              {t("char.name")}
              <input
                autoFocus
                required
                maxLength={80}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              {t("char.summary")}
              <textarea
                maxLength={2000}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
              />
            </label>
            <label className="field">
              {t("char.tags")}
              <input value={tags} onChange={(e) => setTags(e.target.value)} />
            </label>
            {create.error && <Failure error={create.error} />}
            <div className="character-actions">
              <button type="button" onClick={() => setCreating(false)}>
                {t("char.cancel")}
              </button>
              <button disabled={create.isPending || !name.trim()}>
                {t("char.create")}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
