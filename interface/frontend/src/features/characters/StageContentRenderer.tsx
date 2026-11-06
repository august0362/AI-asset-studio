import { useState, type ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../../api/client";
import type {
  AssetPurpose,
  CharacterSpecification,
  ConceptContent,
  ConceptValidationContent,
  ProductionReviewContent,
  PromptSet,
  StageContent,
  StageDetail,
  SpecAttribute,
  ReferenceAsset,
  ConceptCandidate,
  ProductionItem,
} from "../../api/characterTypes";
import type { OptionValue } from "../../api/types";
import { useI18n } from "../../i18n";
import { Badge, Failure } from "../../components/ui";
import { ImageAsset, useCharacterText } from "./shared";
import { BatchControls, LinkedImage, ManifestReview } from "./BatchPanel";
import { formatModelTime } from "../generate/modelTime";
export function Field({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <label className="field">
      <span>{title}</span>
      {children}
    </label>
  );
}
const groups: SpecAttribute["group"][] = [
  "identity",
  "face",
  "hair",
  "eyes",
  "body",
  "outfit",
  "accessories",
  "color",
  "style",
  "pose",
  "other",
];
const purposes: AssetPurpose[] = [
  "full_body",
  "portrait",
  "key_visual",
  "front",
  "side",
  "back",
  "three_quarter",
  "detail",
  "chibi",
];
interface Props<T extends StageContent> {
  content: T;
  change: (content: T) => void;
  detail: StageDetail;
  dirty: boolean;
  setError: (key: string, message: string | null) => void;
  setLocalDirty: (key: string, value: boolean) => void;
}
export function StageContentRenderer(props: Props<StageContent>) {
  const { content } = props;
  switch (content.stage_id) {
    case "s1":
      return <ConceptEditor {...props} content={content} />;
    case "s2":
      return <SpecificationEditor {...props} content={content} />;
    case "s3":
      return <ValidationEditor {...props} content={content} />;
    case "s4":
      return <PromptEditor {...props} content={content} />;
    case "s5":
      return <ProductionEditor {...props} content={content} />;
    default:
      return <PlannedEditor {...props} content={content} />;
  }
}
function ConceptEditor({
  content,
  change,
  detail,
  setError,
  setLocalDirty,
}: Props<ConceptContent>) {
  const { t, label } = useI18n();
  const [palette, setPalette] = useState(content.palette.join(", "));
  return (
    <>
      <Field title={t("char.idea")}>
        <textarea
          rows={4}
          maxLength={4000}
          value={content.idea ?? ""}
          onChange={(e) => change({ ...content, idea: e.target.value })}
        />
      </Field>
      <Field title={t("char.directions")}>
        <textarea
          rows={3}
          value={content.directions.join("\n")}
          onChange={(e) =>
            change({ ...content, directions: e.target.value.split("\n") })
          }
        />
      </Field>
      <Field title={t("char.notes")}>
        <textarea
          rows={4}
          maxLength={8000}
          value={content.notes ?? ""}
          onChange={(e) => change({ ...content, notes: e.target.value })}
        />
      </Field>
      <Field title={t("char.palette")}>
        <input
          value={palette}
          onChange={(e) => {
            setPalette(e.target.value);
            const values = e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);
            const valid =
              values.length <= 12 &&
              values.every((s) => /^#[0-9a-f]{6}$/i.test(s));
            setError("palette", valid ? null : t("char.invalidPalette"));
            if (valid) change({ ...content, palette: values });
          }}
        />
      </Field>
      <ReferenceForm
        onDirty={(value) => setLocalDirty("reference", value)}
        detail={detail}
        onAdded={(ref) =>
          change({
            ...content,
            references: [
              ...content.references,
              {
                reference_id: ref.reference_id,
                aspects: [],
                likes: null,
                do_not_copy: null,
              },
            ],
          })
        }
      />
      {detail.references.map((ref) => {
        const note = content.references.find(
          (r) => r.reference_id === ref.reference_id,
        );
        return (
          <section className="character-inset" key={ref.reference_id}>
            <h3>{ref.title}</h3>
            {ref.kind === "image" ? (
              <ImageAsset
                characterId={detail.character.character_id}
                asset={ref}
                reference
              />
            ) : (
              <a href={ref.url ?? undefined} target="_blank" rel="noreferrer">
                {ref.url}
              </a>
            )}
            <label className="character-checkbox">
              <input
                type="checkbox"
                checked={!!note}
                onChange={(e) =>
                  change({
                    ...content,
                    references: e.target.checked
                      ? [
                          ...content.references,
                          {
                            reference_id: ref.reference_id,
                            aspects: [],
                            likes: null,
                            do_not_copy: null,
                          },
                        ]
                      : content.references.filter(
                          (n) => n.reference_id !== ref.reference_id,
                        ),
                  })
                }
              />
              {t("char.reference")}
            </label>
            {note && (
              <>
                <Field title={t("char.aspects")}>
                  <select
                    multiple
                    value={note.aspects}
                    onChange={(e) =>
                      change({
                        ...content,
                        references: content.references.map((n) =>
                          n.reference_id === ref.reference_id
                            ? {
                                ...n,
                                aspects: Array.from(
                                  e.target.selectedOptions,
                                  (v) => v.value as SpecAttribute["group"],
                                ),
                              }
                            : n,
                        ),
                      })
                    }
                  >
                    {groups.map((g) => (
                      <option key={g} value={g}>
                        {label("specGroup", g)}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field title={t("char.likes")}>
                  <textarea
                    value={note.likes ?? ""}
                    onChange={(e) =>
                      change({
                        ...content,
                        references: content.references.map((n) =>
                          n.reference_id === ref.reference_id
                            ? { ...n, likes: e.target.value }
                            : n,
                        ),
                      })
                    }
                  />
                </Field>
                <Field title={t("char.doNotCopy")}>
                  <textarea
                    value={note.do_not_copy ?? ""}
                    onChange={(e) =>
                      change({
                        ...content,
                        references: content.references.map((n) =>
                          n.reference_id === ref.reference_id
                            ? { ...n, do_not_copy: e.target.value }
                            : n,
                        ),
                      })
                    }
                  />
                </Field>
              </>
            )}
          </section>
        );
      })}
    </>
  );
}
function ReferenceForm({
  detail,
  onAdded,
  onDirty,
}: {
  detail: StageDetail;
  onAdded: (ref: ReferenceAsset) => void;
  onDirty: (value: boolean) => void;
}) {
  const { t, label } = useI18n(),
    cache = useQueryClient();
  const [title, setTitle] = useState(""),
    [url, setUrl] = useState(""),
    [note, setNote] = useState(""),
    [purpose, setPurpose] = useState<ReferenceAsset["purpose"]>("moodboard");
  const add = useMutation({
    mutationFn: async (file?: File) => {
      const upload = file ? await api.upload(file) : null;
      return api.createReference(detail.character.character_id, {
        contract_version: "1.1",
        client_request_id: crypto.randomUUID(),
        kind: file ? "image" : "url",
        purpose,
        title: title || file?.name || url,
        url: file ? null : url,
        upload_id: upload?.upload_id ?? null,
        source_note: note || null,
      });
    },
    onSuccess: (r) => {
      onAdded(r);
      setTitle("");
      setUrl("");
      onDirty(false);
      void cache.invalidateQueries({
        queryKey: ["character-stage", detail.character.character_id],
      });
      void cache.invalidateQueries({
        queryKey: ["character-history", detail.character.character_id],
      });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api.deleteReference(detail.character.character_id, id),
    onSuccess: () => {
      void cache.invalidateQueries({
        queryKey: ["character-stage", detail.character.character_id],
      });
    },
  });
  return (
    <section className="character-inset" onChange={() => onDirty(true)}>
      <h3>{t("char.references")}</h3>
      <Field title={t("char.referenceTitle")}>
        <input
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
        />
      </Field>
      <Field title={t("char.referencePurpose")}>
        <select
          value={purpose}
          onChange={(e) =>
            setPurpose(e.target.value as ReferenceAsset["purpose"])
          }
        >
          {["moodboard", "sketch", "concept"].map((p) => (
            <option key={p} value={p}>
              {label("purpose", p)}
            </option>
          ))}
        </select>
      </Field>
      <Field title={t("char.sourceNote")}>
        <input
          value={note}
          maxLength={500}
          onChange={(e) => setNote(e.target.value)}
        />
      </Field>
      <Field title={t("char.url")}>
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
        />
      </Field>
      <button
        disabled={add.isPending || !url}
        onClick={() => add.mutate(undefined)}
      >
        {t("char.addUrl")}
      </button>
      <Field title={t("char.upload")}>
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          disabled={add.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) add.mutate(file);
            e.target.value = "";
          }}
        />
      </Field>
      {detail.references.map((ref) => (
        <div className="character-actions" key={ref.reference_id}>
          <span>{ref.title}</span>
          <button
            disabled={remove.isPending}
            onClick={() => remove.mutate(ref.reference_id)}
          >
            {t("char.remove")}
          </button>
        </div>
      ))}
      {add.error && <Failure error={add.error} />}{" "}
      {remove.error && <Failure error={remove.error} />}
    </section>
  );
}
function SpecificationEditor({
  content,
  change,
  detail,
}: Props<CharacterSpecification>) {
  const { t, label, text } = useCharacterText();
  const [guided, setGuided] = useState(true);
  const questions = [...detail.config.guided_questions].sort(
    (a, b) => Number(b.core) - Number(a.core),
  );
  const unanswered = questions.filter(
    (q) => !content.answers.some((a) => a.question_id === q.question_id),
  );
  const visible = unanswered.slice(0, 5);
  const edit = (id: string, patch: Partial<SpecAttribute>) =>
    change({
      ...content,
      attributes: content.attributes.map((a) =>
        a.attribute_id === id ? { ...a, ...patch } : a,
      ),
    });
  return (
    <>
      <div className="character-actions">
        <button aria-pressed={guided} onClick={() => setGuided(true)}>
          {t("char.guided")}
        </button>
        <button aria-pressed={!guided} onClick={() => setGuided(false)}>
          {t("char.specSheet")}
        </button>
      </div>
      <Field title={t("char.summary")}>
        <textarea
          value={content.summary ?? ""}
          onChange={(e) => change({ ...content, summary: e.target.value })}
        />
      </Field>
      {guided && (
        <section className="character-inset">
          <h3>
            {t("char.guided")} · {content.answers.length}/{questions.length}
          </h3>
          {[
            ...questions.filter((q) =>
              content.answers.some((a) => a.question_id === q.question_id),
            ),
            ...visible,
          ].map((q) => {
            const answer = content.answers.find(
              (a) => a.question_id === q.question_id,
            );
            const patch = (
              status: "answered" | "unknown" | "skipped",
              value: string | null,
            ) =>
              change({
                ...content,
                answers: [
                  ...content.answers.filter(
                    (a) => a.question_id !== q.question_id,
                  ),
                  {
                    question_id: q.question_id,
                    status,
                    answer: status === "answered" ? value : null,
                  },
                ],
              });
            return (
              <section className="character-inset" key={q.question_id}>
                <Field title={text(q.label_key)}>
                  <textarea
                    value={answer?.answer ?? ""}
                    onChange={(e) => patch("answered", e.target.value)}
                  />
                </Field>
                <Field title={t("char.answerState")}>
                  <select
                    value={answer?.status ?? ""}
                    onChange={(e) =>
                      patch(
                        e.target.value as "answered" | "unknown" | "skipped",
                        answer?.answer ?? "",
                      )
                    }
                  >
                    <option value="" disabled>
                      {t("char.answer")}
                    </option>
                    {["answered", "unknown", "skipped"].map((s) => (
                      <option key={s} value={s}>
                        {label("answer", s)}
                      </option>
                    ))}
                  </select>
                </Field>
              </section>
            );
          })}
        </section>
      )}
      <h3>{t("char.attributes")}</h3>
      {content.attributes.map((a) => (
        <section className="character-inset" key={a.attribute_id}>
          <div className="character-field-grid">
            <Field title={t("char.attributeLabel")}>
              <input
                value={a.label}
                onChange={(e) =>
                  edit(a.attribute_id, { label: e.target.value })
                }
              />
            </Field>
            <Field title={t("char.group")}>
              <select
                value={a.group}
                onChange={(e) =>
                  edit(a.attribute_id, {
                    group: e.target.value as SpecAttribute["group"],
                  })
                }
              >
                {groups.map((g) => (
                  <option key={g} value={g}>
                    {label("specGroup", g)}
                  </option>
                ))}
              </select>
            </Field>
          </div>
          <Field title={t("char.value")}>
            <textarea
              value={a.value}
              onChange={(e) => edit(a.attribute_id, { value: e.target.value })}
            />
          </Field>
          <Field title={t("char.lock")}>
            <select
              value={a.lock}
              onChange={(e) =>
                edit(a.attribute_id, {
                  lock: e.target.value as SpecAttribute["lock"],
                })
              }
            >
              {["locked", "preferred", "flexible"].map((g) => (
                <option key={g} value={g}>
                  {label("lock", g)}
                </option>
              ))}
            </select>
          </Field>
          <Field title={t("char.references")}>
            <select
              multiple
              value={a.reference_ids}
              onChange={(e) =>
                edit(a.attribute_id, {
                  reference_ids: Array.from(
                    e.target.selectedOptions,
                    (o) => o.value,
                  ),
                })
              }
            >
              {detail.references.map((r) => (
                <option key={r.reference_id} value={r.reference_id}>
                  {r.title}
                </option>
              ))}
            </select>
          </Field>
          <button
            onClick={() =>
              change({
                ...content,
                attributes: content.attributes.filter(
                  (v) => v.attribute_id !== a.attribute_id,
                ),
              })
            }
          >
            {t("char.remove")}
          </button>
        </section>
      ))}
      <button
        onClick={() =>
          change({
            ...content,
            attributes: [
              ...content.attributes,
              {
                attribute_id: `attr_${crypto.randomUUID().replaceAll("-", "").slice(0, 8)}`,
                group: "identity",
                label: "",
                value: "",
                lock: "locked",
                reference_ids: [],
              },
            ],
          })
        }
      >
        {t("char.addAttribute")}
      </button>
      <Field title={t("char.openQuestions")}>
        <textarea
          value={content.open_questions.join("\n")}
          onChange={(e) =>
            change({ ...content, open_questions: e.target.value.split("\n") })
          }
        />
      </Field>
      <Field title={t("char.rejectionCriteria")}>
        <textarea
          value={content.rejection_criteria.join("\n")}
          onChange={(e) =>
            change({
              ...content,
              rejection_criteria: e.target.value.split("\n"),
            })
          }
        />
      </Field>
    </>
  );
}
function ModelSelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  const i18n = useI18n(),
    q = useQuery({ queryKey: ["models"], queryFn: () => api.models() });
  const selected = q.data?.models.find((m) => m.model_id === value);
  return (
    <Field title={i18n.t("char.model")}>
      <select
        title={selected ? formatModelTime(selected, i18n)?.tooltip : undefined}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="" disabled>
          {i18n.t("char.model")}
        </option>
        {q.data?.models
          .filter(
            (m) =>
              m.supported_pipeline_types.includes("text_to_2d") &&
              m.supported_asset_categories.includes("character"),
          )
          .map((m) => (
            <option
              key={m.model_id}
              value={m.model_id}
              title={formatModelTime(m, i18n)?.tooltip}
              disabled={!["available", "experimental"].includes(m.availability)}
            >
              {m.display_name}
              {formatModelTime(m, i18n)
                ? ` ${formatModelTime(m, i18n)!.label}`
                : ""}
            </option>
          ))}
      </select>
      {q.error && <Failure error={q.error} />}
    </Field>
  );
}
function OptionsEditor({
  value,
  onChange,
  setError,
  id,
}: {
  value: Record<string, OptionValue>;
  onChange: (v: Record<string, OptionValue>) => void;
  setError: Props<StageContent>["setError"];
  id: string;
}) {
  const { t } = useI18n();
  const [raw, setRaw] = useState(JSON.stringify(value, null, 2));
  return (
    <Field title={t("char.options")}>
      <textarea
        value={raw}
        rows={3}
        onChange={(e) => {
          setRaw(e.target.value);
          try {
            const parsed: unknown = JSON.parse(e.target.value);
            if (
              !parsed ||
              typeof parsed !== "object" ||
              Array.isArray(parsed) ||
              !Object.values(parsed).every(
                (v) =>
                  v === null ||
                  ["string", "number", "boolean"].includes(typeof v),
              )
            )
              throw new Error();
            setError(id, null);
            onChange(parsed as Record<string, OptionValue>);
          } catch {
            setError(id, t("char.invalidJson"));
          }
        }}
      />
    </Field>
  );
}
function JobPicker({ onLink }: { onLink: (id: string) => void }) {
  const { t } = useI18n();
  const q = useQuery({
    queryKey: ["character-link-jobs"],
    queryFn: () =>
      api.jobs({ status: "completed", pipeline_type: "text_to_2d", limit: 50 }),
  });
  const [id, setId] = useState("");
  return (
    <section className="character-inset">
      <Field title={t("char.job")}>
        <select value={id} onChange={(e) => setId(e.target.value)}>
          <option value="">{t("char.job")}</option>
          {q.data?.jobs
            .filter((j) => j.primary_artifact?.format === "png")
            .map((j) => (
              <option key={j.job_id} value={j.job_id}>
                {j.model_id} · {j.job_id}
              </option>
            ))}
        </select>
      </Field>
      <button disabled={!id} onClick={() => onLink(id)}>
        {t("char.linkJob")}
      </button>
      {q.error && <Failure error={q.error} />}
      <LinkStudio />
    </section>
  );
}
function LinkStudio() {
  const { t } = useI18n();
  return (
    <a className="button" href="/generate/text-to-2d">
      {t("copy.generateStudio")}
    </a>
  );
}
function ValidationEditor({
  content,
  change,
  detail,
  dirty,
  setError,
}: Props<ConceptValidationContent>) {
  const { t, label } = useI18n();
  const [compare, setCompare] = useState<string[]>([]);
  const profile = content.preview_profile;
  const patchProfile = (patch: Partial<NonNullable<typeof profile>>) =>
    change({
      ...content,
      preview_profile: {
        model_id: "",
        compute_target: "kaggle",
        variations: 1,
        width: 768,
        height: 768,
        options: {},
        ...profile,
        ...patch,
      },
    });
  const add = (patch: Partial<ConceptCandidate>) => {
    const next =
      Math.max(
        0,
        ...content.candidates.map((c) => Number(c.candidate_id.slice(5))),
      ) + 1;
    change({
      ...content,
      candidates: [
        ...content.candidates,
        {
          candidate_id: `cand_${String(next).padStart(2, "0")}`,
          source: "job_artifact",
          manifest_id: null,
          task_id: null,
          job: null,
          reference_id: null,
          verdict: "undecided",
          matches: [],
          mismatches: [],
          feedback: null,
          ...patch,
        },
      ],
    });
  };
  const patchCandidate = (id: string, patch: Partial<ConceptCandidate>) =>
    change({
      ...content,
      candidates: content.candidates.map((c) =>
        c.candidate_id === id
          ? { ...c, ...patch }
          : patch.verdict === "selected"
            ? {
                ...c,
                verdict: c.verdict === "selected" ? "undecided" : c.verdict,
              }
            : c,
      ),
      selected_candidate_id:
        patch.verdict === "selected"
          ? id
          : content.selected_candidate_id === id && patch.verdict
            ? null
            : content.selected_candidate_id,
    });
  const attrs = detail.inputs.flatMap((i) =>
    i.content?.stage_id === "s2"
      ? i.content.attributes.filter((a) => a.lock === "locked")
      : [],
  );
  return (
    <>
      <p className="notice info">{t("char.previewWarning")}</p>
      <ModelSelect
        value={profile?.model_id ?? ""}
        onChange={(model_id) => patchProfile({ model_id })}
      />
      <div className="character-field-grid">
        {(["variations", "width", "height"] as const).map((key) => (
          <Field key={key} title={t(`char.${key}`)}>
            <input
              type="number"
              min={1}
              value={profile?.[key] ?? (key === "variations" ? 1 : 768)}
              onChange={(e) => patchProfile({ [key]: Number(e.target.value) })}
            />
          </Field>
        ))}
      </div>
      <OptionsEditor
        id="preview-options"
        value={profile?.options ?? {}}
        setError={setError}
        onChange={(options) => patchProfile({ options })}
      />
      <Field title={t("char.previewPrompt")}>
        <textarea
          rows={5}
          maxLength={4000}
          value={content.preview_prompt ?? ""}
          onChange={(e) =>
            change({ ...content, preview_prompt: e.target.value })
          }
        />
      </Field>
      <BatchControls detail={detail} dirty={dirty} />
      <JobPicker
        onLink={(job_id) =>
          add({ source: "job_artifact", job: { job_id, artifact_id: null } })
        }
      />
      <div className="character-actions">
        {detail.references
          .filter((r) => r.kind === "image")
          .map((ref) => (
            <button
              key={ref.reference_id}
              onClick={() =>
                add({ source: "reference", reference_id: ref.reference_id })
              }
            >
              {t("char.linkReference")}: {ref.title}
            </button>
          ))}
      </div>
      {detail.batches.flatMap((b) =>
        b.results
          .filter((r) => r.status === "succeeded")
          .map((r) => (
            <button
              key={`${b.manifest_id}-${r.task_id}`}
              disabled={content.candidates.some(
                (c) =>
                  c.manifest_id === b.manifest_id && c.task_id === r.task_id,
              )}
              onClick={() =>
                add({
                  source: "batch_task",
                  manifest_id: b.manifest_id,
                  task_id: r.task_id,
                })
              }
            >
              {t("char.preview")}: {r.task_id}
            </button>
          )),
      )}
      <h3>{t("char.candidates")}</h3>
      <div className="character-actions">
        {content.candidates.map((c) => (
          <label className="character-checkbox" key={c.candidate_id}>
            <input
              type="checkbox"
              checked={compare.includes(c.candidate_id)}
              disabled={
                compare.length >= 3 && !compare.includes(c.candidate_id)
              }
              onChange={(e) =>
                setCompare(
                  e.target.checked
                    ? [...compare, c.candidate_id]
                    : compare.filter((id) => id !== c.candidate_id),
                )
              }
            />
            {c.candidate_id}
          </label>
        ))}
      </div>
      <div className="character-gallery">
        {content.candidates
          .filter((c) => !compare.length || compare.includes(c.candidate_id))
          .map((c) => (
            <section className="character-inset" key={c.candidate_id}>
              <h3>{c.candidate_id}</h3>
              <CandidateImage candidate={c} detail={detail} />
              <Field title={t("char.verdict")}>
                <select
                  value={c.verdict}
                  onChange={(e) =>
                    patchCandidate(c.candidate_id, {
                      verdict: e.target.value as ConceptCandidate["verdict"],
                    })
                  }
                >
                  {["undecided", "selected", "rejected"].map((v) => (
                    <option value={v} key={v}>
                      {label("verdict", v)}
                    </option>
                  ))}
                </select>
              </Field>
              {attrs.map((a) => (
                <div key={a.attribute_id}>
                  <strong>
                    {a.label}: {a.value}
                  </strong>
                  {(["matches", "mismatches"] as const).map((key) => (
                    <label className="character-checkbox" key={key}>
                      <input
                        type="checkbox"
                        checked={c[key].includes(a.attribute_id)}
                        onChange={(e) =>
                          patchCandidate(c.candidate_id, {
                            [key]: e.target.checked
                              ? [...c[key], a.attribute_id]
                              : c[key].filter((id) => id !== a.attribute_id),
                          })
                        }
                      />
                      {t(`char.${key}`)}
                    </label>
                  ))}
                </div>
              ))}
              <Field title={t("char.feedback")}>
                <textarea
                  value={c.feedback ?? ""}
                  onChange={(e) =>
                    patchCandidate(c.candidate_id, { feedback: e.target.value })
                  }
                />
              </Field>
              <button
                onClick={() =>
                  change({
                    ...content,
                    candidates: content.candidates.filter(
                      (v) => v.candidate_id !== c.candidate_id,
                    ),
                    selected_candidate_id:
                      content.selected_candidate_id === c.candidate_id
                        ? null
                        : content.selected_candidate_id,
                  })
                }
              >
                {t("char.remove")}
              </button>
            </section>
          ))}
      </div>
      <Field title={t("char.notes")}>
        <textarea
          value={content.review_notes ?? ""}
          onChange={(e) => change({ ...content, review_notes: e.target.value })}
        />
      </Field>
    </>
  );
}
function CandidateImage({
  candidate: c,
  detail,
}: {
  candidate: ConceptCandidate;
  detail: StageDetail;
}) {
  const { t } = useI18n();
  const r = detail.references.find((r) => r.reference_id === c.reference_id),
    batch = detail.batches.find((b) => b.manifest_id === c.manifest_id),
    result = batch?.results.find((r) => r.task_id === c.task_id);
  return (
    <>
      {r && r.kind === "image" ? (
        <ImageAsset
          characterId={detail.character.character_id}
          asset={r}
          reference
        />
      ) : c.job ? (
        <LinkedImage jobId={c.job.job_id} artifactId={c.job.artifact_id} />
      ) : result?.job_id ? (
        <LinkedImage jobId={result.job_id} artifactId={result.artifact_id} />
      ) : null}
      {c.job && (
        <p>
          {t("char.model")}:{" "}
          {detail.resolved_jobs.find((j) => j.job_id === c.job?.job_id)
            ?.model_id ?? t("common.unknown")}
        </p>
      )}
      {batch && (
        <p>
          {t("char.model")}: {batch.target_model_id}
        </p>
      )}
    </>
  );
}
function PromptEditor({ content, change, detail, setError }: Props<PromptSet>) {
  const { t, label } = useI18n();
  const [purpose, setPurpose] = useState<AssetPurpose>("full_body"),
    [diff, setDiff] = useState(false),
    [copied, setCopied] = useState(false),
    [copyError, setCopyError] = useState<unknown>();
  const entry = content.entries.find((e) => e.purpose === purpose);
  const modelPrompt =
    content.tasks.find((task) => task.purpose === purpose)?.prompt ??
    entry?.canonical_prompt;
  const edit = (patch: Partial<NonNullable<typeof entry>>) =>
    change({
      ...content,
      entries: entry
        ? content.entries.map((e) =>
            e.purpose === purpose ? { ...e, ...patch } : e,
          )
        : [
            ...content.entries,
            {
              purpose,
              canonical_prompt: "",
              negative_prompt: null,
              notes: null,
              ...patch,
            },
          ],
    });
  return (
    <>
      <ModelSelect
        value={content.production_profile?.target_model_id ?? ""}
        onChange={(target_model_id) =>
          change({
            ...content,
            production_profile: {
              target_model_id,
              compute_target: "kaggle",
              options: content.production_profile?.options ?? {},
            },
          })
        }
      />
      <OptionsEditor
        id="production-options"
        value={content.production_profile?.options ?? {}}
        setError={setError}
        onChange={(options) =>
          change({
            ...content,
            production_profile: {
              target_model_id:
                content.production_profile?.target_model_id ?? "",
              compute_target: "kaggle",
              options,
            },
          })
        }
      />
      <Field title={t("char.references")}>
        <select
          multiple
          value={content.reference_asset_ids}
          onChange={(e) =>
            change({
              ...content,
              reference_asset_ids: Array.from(
                e.target.selectedOptions,
                (o) => o.value,
              ),
            })
          }
        >
          {detail.inputs.flatMap((i) =>
            i.frozen_assets.map((a) => (
              <option key={a.asset_id} value={a.asset_id}>
                {label("purpose", a.purpose)} · {a.asset_id}
              </option>
            )),
          )}
          {detail.references.map((r) => (
            <option key={r.reference_id} value={r.reference_id}>
              {r.title}
            </option>
          ))}
        </select>
      </Field>
      <div className="character-purpose-tabs">
        {purposes.map((p) => (
          <button
            key={p}
            aria-pressed={purpose === p}
            onClick={() => setPurpose(p)}
          >
            {label("purpose", p)}
          </button>
        ))}
      </div>
      <Field title={t("char.canonical")}>
        <textarea
          rows={5}
          value={entry?.canonical_prompt ?? ""}
          maxLength={4000}
          onChange={(e) => edit({ canonical_prompt: e.target.value })}
        />
      </Field>
      <Field title={t("char.negative")}>
        <textarea
          value={entry?.negative_prompt ?? ""}
          maxLength={1000}
          onChange={(e) => edit({ negative_prompt: e.target.value || null })}
        />
      </Field>
      <Field title={t("char.notes")}>
        <textarea
          value={entry?.notes ?? ""}
          onChange={(e) => edit({ notes: e.target.value || null })}
        />
      </Field>
      <div className="character-actions">
        <button
          disabled={!modelPrompt}
          onClick={() => {
            void navigator.clipboard
              .writeText(modelPrompt!)
              .then(() => setCopied(true))
              .catch(setCopyError);
          }}
        >
          {copied ? t("char.copied") : t("char.copy")}
        </button>
        <button aria-pressed={diff} onClick={() => setDiff((v) => !v)}>
          {t("char.diff")}
        </button>
      </div>
      {copyError && <Failure error={copyError} />}{" "}
      {diff && (
        <div className="character-field-grid">
          <section className="character-inset">
            <h3>
              {t("char.revision", {
                revision: detail.approved_revision?.revision ?? 0,
              })}
            </h3>
            <p>
              {detail.approved_revision?.content.stage_id === "s4"
                ? detail.approved_revision.content.entries.find(
                    (e) => e.purpose === purpose,
                  )?.canonical_prompt
                : t("char.none")}
            </p>
          </section>
          <section className="character-inset">
            <h3>{t("char.canonical")}</h3>
            <p>{entry?.canonical_prompt}</p>
          </section>
        </div>
      )}
      <h3>{t("char.tasks")}</h3>
      {content.tasks.map((task, i) => {
        const patch = (v: Partial<typeof task>) =>
          change({
            ...content,
            tasks: content.tasks.map((t, n) => (n === i ? { ...t, ...v } : t)),
          });
        return (
          <section key={task.task_id} className="character-inset">
            <code>{task.task_id}</code>
            <Field title={t("char.purpose")}>
              <select
                value={task.purpose}
                onChange={(e) =>
                  patch({ purpose: e.target.value as AssetPurpose })
                }
              >
                {purposes.map((p) => (
                  <option key={p} value={p}>
                    {label("purpose", p)}
                  </option>
                ))}
              </select>
            </Field>
            <Field title={t("char.modelPrompt")}>
              <textarea
                value={task.prompt}
                maxLength={4000}
                onChange={(e) => patch({ prompt: e.target.value })}
              />
            </Field>
            <Field title={t("char.negative")}>
              <textarea
                value={task.negative_prompt ?? ""}
                onChange={(e) =>
                  patch({ negative_prompt: e.target.value || null })
                }
              />
            </Field>
            <div className="character-field-grid">
              {(["seed", "width", "height"] as const).map((k) => (
                <Field key={k} title={t(`char.${k}`)}>
                  <input
                    type="number"
                    min={k === "seed" ? 0 : 1}
                    value={task[k] ?? ""}
                    onChange={(e) =>
                      patch({
                        [k]:
                          e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  />
                </Field>
              ))}
            </div>
            <OptionsEditor
              id={`task-${task.task_id}`}
              value={task.options}
              setError={setError}
              onChange={(options) => patch({ options })}
            />
            <button
              onClick={() => {
                setError(`task-${task.task_id}`, null);
                change({
                  ...content,
                  tasks: content.tasks.filter((_, n) => n !== i),
                });
              }}
            >
              {t("char.remove")}
            </button>
          </section>
        );
      })}
      <button
        onClick={() =>
          change({
            ...content,
            tasks: [
              ...content.tasks,
              {
                task_id: `task_${crypto.randomUUID().slice(0, 8)}`,
                purpose,
                prompt: entry?.canonical_prompt ?? "",
                negative_prompt: entry?.negative_prompt ?? null,
                seed: crypto.getRandomValues(new Uint32Array(1))[0],
                width: 768,
                height: 768,
                options: {},
              },
            ],
          })
        }
      >
        {t("char.addTask")}
      </button>
      <ManifestReview detail={detail} />
      <LinkStudio />
    </>
  );
}
function ProductionEditor({
  content,
  change,
  detail,
  dirty,
}: Props<ProductionReviewContent>) {
  const { t, label } = useI18n();
  const [purpose, setPurpose] = useState<AssetPurpose>("full_body");
  const add = (patch: Partial<ProductionItem>) => {
    const n =
      Math.max(0, ...content.items.map((i) => Number(i.item_id.slice(5)))) + 1;
    change({
      ...content,
      items: [
        ...content.items,
        {
          item_id: `item_${String(n).padStart(3, "0")}`,
          purpose,
          manifest_id: null,
          task_id: null,
          job: null,
          selected: false,
          note: null,
          ...patch,
        },
      ],
    });
  };
  return (
    <>
      <p className="notice warning">{t("char.consistency")}</p>
      <BatchControls detail={detail} dirty={dirty} />
      <ManifestReview detail={detail} />
      <Field title={t("char.purpose")}>
        <select
          value={purpose}
          onChange={(e) => setPurpose(e.target.value as AssetPurpose)}
        >
          {purposes.map((p) => (
            <option key={p} value={p}>
              {label("purpose", p)}
            </option>
          ))}
        </select>
      </Field>
      <JobPicker
        onLink={(job_id) => add({ job: { job_id, artifact_id: null } })}
      />
      {detail.batches.flatMap((b) =>
        b.results
          .filter((r) => r.status === "succeeded")
          .map((r) => (
            <button
              key={`${b.manifest_id}-${r.task_id}`}
              disabled={content.items.some(
                (i) =>
                  i.manifest_id === b.manifest_id && i.task_id === r.task_id,
              )}
              onClick={() =>
                add({
                  purpose: b.tasks.find((t) => t.task_id === r.task_id)!
                    .purpose,
                  manifest_id: b.manifest_id,
                  task_id: r.task_id,
                })
              }
            >
              {t("char.production")}: {r.task_id}
            </button>
          )),
      )}
      <div className="character-gallery">
        {content.items.map((item) => {
          const result = detail.batches
            .find((b) => b.manifest_id === item.manifest_id)
            ?.results.find((r) => r.task_id === item.task_id);
          return (
            <section key={item.item_id} className="character-inset">
              <h3>{label("purpose", item.purpose)}</h3>
              {item.job ? (
                <LinkedImage
                  jobId={item.job.job_id}
                  artifactId={item.job.artifact_id}
                />
              ) : result?.job_id ? (
                <LinkedImage
                  jobId={result.job_id}
                  artifactId={result.artifact_id}
                />
              ) : null}
              <label className="character-checkbox">
                <input
                  type="checkbox"
                  checked={item.selected}
                  onChange={(e) =>
                    change({
                      ...content,
                      items: content.items.map((i) =>
                        i.item_id === item.item_id
                          ? { ...i, selected: e.target.checked }
                          : i,
                      ),
                    })
                  }
                />
                {t("char.selectImage")}
              </label>
              <Field title={t("char.note")}>
                <textarea
                  value={item.note ?? ""}
                  onChange={(e) =>
                    change({
                      ...content,
                      items: content.items.map((i) =>
                        i.item_id === item.item_id
                          ? { ...i, note: e.target.value }
                          : i,
                      ),
                    })
                  }
                />
              </Field>
              <button
                onClick={() =>
                  change({
                    ...content,
                    items: content.items.filter(
                      (i) => i.item_id !== item.item_id,
                    ),
                  })
                }
              >
                {t("char.remove")}
              </button>
            </section>
          );
        })}
      </div>
      <Field title={t("char.notes")}>
        <textarea
          value={content.consistency_notes ?? ""}
          onChange={(e) =>
            change({ ...content, consistency_notes: e.target.value })
          }
        />
      </Field>
    </>
  );
}
function PlannedEditor({ content, detail }: Props<StageContent>) {
  const { t, text } = useCharacterText();
  return (
    <div className="character-planned">
      <Badge tone="warning">{t("char.planned")}</Badge>
      <h2>{text(detail.config.title_key)}</h2>
      <p>{text(detail.config.objective_key)}</p>
      <p>{t("char.plannedHelp")}</p>
      <ul>
        {detail.config.checklist.map((i) => (
          <li key={i.item_id}>{text(i.label_key)}</li>
        ))}
      </ul>
      {(content.stage_id === "s6" || content.stage_id === "s7") &&
        content.notes && <p>{content.notes}</p>}
      <button disabled>{t("char.planned")}</button>
    </div>
  );
}
