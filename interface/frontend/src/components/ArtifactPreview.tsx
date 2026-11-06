import { lazy, Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { api } from "../api/client";
import type { Artifact } from "../api/types";
import { Failure, Loading } from "./ui";
const GlbViewer = lazy(() => import("./GlbViewer"));

export function useBlobUrl(blob?: Blob) {
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!blob) {
      setUrl(undefined);
      return;
    }
    const next = URL.createObjectURL(blob);
    setUrl(next);
    return () => URL.revokeObjectURL(next);
  }, [blob]);
  return url;
}
export function ArtifactImage({
  jobId,
  artifact,
  alt = "Mock fixture: cyan textured box concept",
  className = "",
}: {
  jobId: string;
  artifact: Artifact;
  alt?: string;
  className?: string;
}) {
  const data = useQuery({
    queryKey: ["artifact", jobId, artifact.artifact_id],
    queryFn: () => api.artifactContent(jobId, artifact.artifact_id),
    staleTime: Infinity,
  });
  const url = useBlobUrl(data.data);
  return data.error ? (
    <Failure error={data.error} />
  ) : url ? (
    <img
      className={className}
      src={url}
      alt={alt}
      width={artifact.width ?? 768}
      height={artifact.height ?? 768}
      loading="lazy"
    />
  ) : (
    <Loading>Loading preview…</Loading>
  );
}
export function ArtifactPreview({
  jobId,
  artifact,
}: {
  jobId: string;
  artifact: Artifact;
}) {
  const data = useQuery({
    queryKey: ["artifact", jobId, artifact.artifact_id],
    queryFn: () => api.artifactContent(jobId, artifact.artifact_id),
    staleTime: Infinity,
  });
  const url = useBlobUrl(data.data);
  if (data.error) return <Failure error={data.error} />;
  if (!url) return <Loading>Loading artifact…</Loading>;
  return artifact.format === "glb" ? (
    <Suspense fallback={<Loading>Loading 3D viewer…</Loading>}>
      <GlbViewer url={url} />
    </Suspense>
  ) : (
    <div className="image-preview">
      <img
        src={url}
        alt="Mock PNG output: a cyan textured box on an Obsidian grid"
        width={artifact.width ?? 768}
        height={artifact.height ?? 768}
      />
    </div>
  );
}
export function DownloadButton({
  jobId,
  artifact,
}: {
  jobId: string;
  artifact: Artifact;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  async function download() {
    setBusy(true);
    setError(undefined);
    try {
      const blob = await api.artifactContent(jobId, artifact.artifact_id);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${jobId}_${artifact.artifact_id}.${artifact.format}`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      // Keep the object URL alive until the browser has started reading the download.
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button type="button" onClick={download} disabled={busy}>
        <Download size={14} aria-hidden="true" />
        {busy ? "Downloading…" : `Download ${artifact.format.toUpperCase()}`}
      </button>
      {error ? <Failure error={error} /> : null}
    </div>
  );
}
