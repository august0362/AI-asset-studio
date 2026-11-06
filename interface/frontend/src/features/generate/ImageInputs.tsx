import { useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ImagePlus, Trash2 } from "lucide-react";
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
import { Badge, Issues, number } from "../../components/ui";

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
    <span className="thumbnail-placeholder">PNG</span>
  );
}
export function ImageInputs({
  uploads,
  roles,
  model,
  errors,
  onAdd,
  onRole,
  onRemove,
}: {
  uploads: { record: UploadRecord; role: ImageRole }[];
  roles: ImageRole[];
  model: ModelCapabilities;
  errors: ErrorItem[];
  onAdd: (items: { record: UploadRecord; role: ImageRole }[]) => void;
  onRole: (index: number, role: ImageRole) => void;
  onRemove: (index: number) => void;
}) {
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
  return (
    <>
      <div className="reference-summary">
        <span>Reference images</span>
        <Badge>
          {uploads.length} / {model.inputs.max_images} supported
        </Badge>
      </div>
      {model.inputs.max_images > 0 && (
        <p className="muted small">
          {model.inputs.required_image_roles.length
            ? `Required: ${model.inputs.required_image_roles.join(", ")}. `
            : "Optional reference. "}
          Accepted by model:{" "}
          {model.inputs.supported_mime_types
            ?.map((m) => m.replace("image/", "").toUpperCase())
            .join(", ")}
          .{" "}
          {number(
            (model.inputs.maximum_file_size_bytes ?? 52428800) / 1024 ** 2,
          )}{" "}
          MiB max per file.
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
                  {u.record.width} × {u.record.height} ·{" "}
                  {number(u.record.size_bytes / 1024 ** 2)} MiB
                </small>
                <label>
                  <span className="sr-only">Role for {u.record.filename}</span>
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
                        {r.replaceAll("_", " ")}
                        {model.inputs.supported_image_roles.includes(r)
                          ? ""
                          : " (unsupported)"}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <button
                type="button"
                className="icon-button"
                aria-label={`Remove ${u.record.filename}`}
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
            aria-label="Upload reference images"
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
              {busy ? "Uploading images…" : "Add reference images"}
            </strong>
            <span>Drop files here or browse · Multiple images supported</span>
          </button>
        </>
      )}
      <Issues items={uploadErrors} />
    </>
  );
}
