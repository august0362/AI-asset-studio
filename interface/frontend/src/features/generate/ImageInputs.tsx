import { useI18n } from "../../i18n";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ClipboardPaste, ImagePlus, Trash2 } from "lucide-react";
import { api } from "../../api/client";
import type {
  ErrorItem,
  ImageRole,
  ModelCapabilities,
  UploadRecord,
} from "../../api/types";
import { api as client } from "../../api/client";
import { ApiError, errorMessage, issue } from "../../api/errors";
import { useBlobUrl } from "../../components/ArtifactPreview";
import { Badge, Issues } from "../../components/ui";

function Thumbnail({ record }: { record: UploadRecord }) {
  const data = useQuery({
    queryKey: ["upload", record.upload_id],
    queryFn: () => client.uploadContent(record.upload_id),
    staleTime: Infinity,
  });
  const url = useBlobUrl(data.data);
  return url ? (
    <img src={url} alt={record.filename} width={64} height={64} />
  ) : (
    <span className="thumbnail-placeholder">
      {record.mime_type.replace("image/", "").toUpperCase()}
    </span>
  );
}
/** Image files from a paste event (Ctrl+V). Text pastes are left alone. */
export function pastedImages(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files = Array.from(data.files ?? []).filter((f) =>
    f.type.startsWith("image/"),
  );
  if (files.length) return files;
  return Array.from(data.items ?? [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter((f): f is File => f !== null);
}
export function ImageInputs({
  style = false,
  uploads,
  roles,
  model,
  errors,
  onAdd,
  onRole,
  onRemove,
}: {
  /** Text→2D style images (CONTRACTS §14.9): the images give the style, the prompt the content. */
  style?: boolean;
  uploads: { record: UploadRecord; role: ImageRole }[];
  roles: ImageRole[];
  model: ModelCapabilities;
  errors: ErrorItem[];
  onAdd: (items: { record: UploadRecord; role: ImageRole }[]) => void;
  onRole: (index: number, role: ImageRole) => void;
  onRemove: (index: number) => void;
}) {
  const { t, label, number } = useI18n();
  const input = useRef<HTMLInputElement>(null),
    [busy, setBusy] = useState(false),
    [uploadErrors, setUploadErrors] = useState<ErrorItem[]>([]);
  async function upload(files: File[]) {
    if (!files.length) return;
    setBusy(true);
    setUploadErrors([]);
    const results = await Promise.allSettled(
      files.map((file) => api.upload(file)),
    );
    const used = new Set(uploads.map((u) => u.role));
    const added: { record: UploadRecord; role: ImageRole }[] = [],
      failures: ErrorItem[] = [];
    results.forEach((result, i) => {
      if (result.status === "fulfilled") {
        const role =
          model.inputs.required_image_roles.find((r) => !used.has(r)) ??
          model.inputs.supported_image_roles.find((r) => !used.has(r)) ??
          model.inputs.supported_image_roles[0] ??
          "front";
        used.add(role);
        added.push({ record: result.value, role });
      } else if (result.reason instanceof ApiError)
        failures.push(
          ...result.reason.response.errors.map((e) => ({
            ...e,
            message: `${files[i].name}: ${e.message}`,
            details: { ...e.details, filename: files[i].name },
          })),
        );
      else
        failures.push(
          issue(
            "UPLOAD_CORRUPT",
            "file",
            `${files[i].name}: ${errorMessage(result.reason)}`,
          ),
        );
    });
    onAdd(added);
    setUploadErrors(failures);
    setBusy(false);
    if (input.current) input.current.value = "";
  }
  const latest = useRef(upload);
  latest.current = upload;
  const accepts = model.inputs.max_images > 0;
  useEffect(() => {
    if (!accepts) return;
    const onPaste = (event: ClipboardEvent) => {
      const files = pastedImages(event.clipboardData);
      if (!files.length) return;
      event.preventDefault();
      void latest.current(files);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [accepts]);
  const canReadClipboard =
    typeof navigator !== "undefined" && !!navigator.clipboard?.read;
  async function pasteFromClipboard() {
    try {
      const items = await navigator.clipboard.read();
      const files: File[] = [];
      for (const item of items)
        for (const type of item.types.filter((t) => t.startsWith("image/")))
          files.push(
            new File([await item.getType(type)], `pasted.${type.slice(6)}`, {
              type,
            }),
          );
      if (files.length) await upload(files);
    } catch (error) {
      setUploadErrors([issue("UPLOAD_CORRUPT", "file", errorMessage(error))]);
    }
  }
  return (
    <>
      <div className="reference-summary">
        <span>{style ? t("style.title") : t("copy.referenceImages")}</span>
        <Badge>
          {t("images.supported", {
            count: number(uploads.length, 0),
            max: number(model.inputs.max_images, 0),
          })}
        </Badge>
      </div>
      {style && model.inputs.max_images > 0 && (
        <>
          <p className="muted small">{t("style.help")}</p>
          {!model.options_schema.style_strength && (
            <p className="notice style-hint small">
              {t("style.referenceHint")}
            </p>
          )}
        </>
      )}
      {model.inputs.max_images > 0 && (
        <p className="muted small">
          {model.inputs.required_image_roles.length
            ? t("images.required", {
                roles: model.inputs.required_image_roles
                  .map((role) => label("role", role))
                  .join(", "),
              })
            : t("copy.optionalReference")}
          {t("images.accepted", {
            formats: model.inputs.supported_mime_types
              ?.map((m) => m.replace("image/", "").toUpperCase())
              .join(", "),
            max: number(
              (model.inputs.maximum_file_size_bytes ?? 52428800) / 1024 ** 2,
            ),
          })}
        </p>
      )}
      <div className="upload-list">
        {uploads.map((u, i) => {
          const invalid = errors.filter((e) =>
            e.field?.startsWith(`inputs[${i}]`),
          );
          return (
            <div
              className={`upload-row ${invalid.length ? "invalid-row" : ""}`}
              key={u.record.upload_id}
            >
              <Thumbnail record={u.record} />
              <div className="upload-info">
                <span className="filename" title={u.record.filename}>
                  {u.record.filename}
                </span>
                <small>
                  {t("format.dimensions", {
                    width: number(u.record.width, 0),
                    height: number(u.record.height, 0),
                    size: number(u.record.size_bytes / 1024 ** 2),
                    unit: t("unit.mib"),
                  })}
                </small>
                <label>
                  <span className="sr-only">
                    {t("images.roleFor", { filename: u.record.filename })}
                  </span>
                  <select
                    name={`role-${i}`}
                    value={u.role}
                    aria-invalid={invalid.some((e) =>
                      e.field?.endsWith("role"),
                    )}
                    onChange={(e) => onRole(i, e.target.value as ImageRole)}
                  >
                    {roles.map((r) => (
                      <option key={r} value={r}>
                        {label("role", r)}
                        {model.inputs.supported_image_roles.includes(r)
                          ? ""
                          : t("images.unsupported")}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label={t("images.remove", { filename: u.record.filename })}
                onClick={() => onRemove(i)}
              >
                <Trash2 size={15} aria-hidden="true" />
              </button>
            </div>
          );
        })}
      </div>
      {model.inputs.max_images > 0 && (
        <>
          <input
            ref={input}
            name="reference-images"
            className="sr-only"
            tabIndex={-1}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            aria-label={t("copy.uploadReferenceImages")}
            onChange={(e) => void upload(Array.from(e.target.files ?? []))}
          />
          <button
            type="button"
            className="dropzone"
            disabled={busy}
            onClick={() => input.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              if (!busy) void upload(Array.from(e.dataTransfer.files));
            }}
          >
            <ImagePlus size={24} aria-hidden="true" />
            <strong>
              {busy
                ? t("copy.uploadingImages")
                : style
                  ? t("style.add")
                  : t("copy.addReferenceImages")}
            </strong>
            <span>
              {t("copy.dropFilesHereOrBrowseMultipleImagesSupported")}
            </span>
            <span className="small">{t("style.pasteHint")}</span>
          </button>
          {canReadClipboard && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void pasteFromClipboard()}
            >
              <ClipboardPaste size={14} aria-hidden="true" />
              {t("style.paste")}
            </button>
          )}
        </>
      )}
      <Issues items={uploadErrors} />
    </>
  );
}
