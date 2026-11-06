import { Link, useSearchParams } from "react-router-dom";
import { Box, Search, X } from "lucide-react";
import { useJobs, useJob } from "../../api/queries";
import type { JobSummary } from "../../api/types";
import {
  ArtifactImage,
  ArtifactPreview,
  DownloadButton,
} from "../../components/ArtifactPreview";
import {
  Badge,
  categoryLabels,
  date,
  Empty,
  Failure,
  Loading,
  Panel,
} from "../../components/ui";

function AssetCard({
  job,
  onSelect,
  selected,
}: {
  job: JobSummary;
  onSelect: () => void;
  selected: boolean;
}) {
  const detail = useJob(job.job_id),
    preview = detail.data?.artifacts.find(
      (a) => a.artifact_id === detail.data?.preview?.artifact_id,
    );
  return (
    <article className={`asset-card ${selected ? "selected" : ""}`}>
      <button
        className="asset-open"
        onClick={onSelect}
        aria-label={`Inspect ${categoryLabels[job.asset_category]} ${job.primary_artifact?.format.toUpperCase()} ${job.job_id}`}
      >
        <div className="asset-thumb">
          {preview ? (
            <ArtifactImage jobId={job.job_id} artifact={preview} />
          ) : (
            <Box size={40} aria-hidden="true" />
          )}
          <Badge>{job.primary_artifact?.format.toUpperCase()} · MOCK</Badge>
        </div>
        <div className="asset-info">
          <span className="muted small">
            {categoryLabels[job.asset_category]}
          </span>
          <h2>
            {categoryLabels[job.asset_category]}{" "}
            {job.primary_artifact?.format === "glb"
              ? "3D study"
              : "concept study"}
          </h2>
          <p>{job.model_id}</p>
          <small>{date(job.created_at)}</small>
        </div>
      </button>
      <div className="asset-actions">
        <span className="badge success">Completed</span>
        {job.primary_artifact && (
          <DownloadButton jobId={job.job_id} artifact={job.primary_artifact} />
        )}
      </div>
    </article>
  );
}
function AssetDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const job = useJob(id);
  if (job.error) return <Failure error={job.error} />;
  if (!job.data) return <Loading>Loading asset details…</Loading>;
  const j = job.data,
    primary = j.artifacts.find((a) => a.is_primary);
  return (
    <Panel
      title="Asset inspector"
      extra={
        <button
          className="icon-button"
          aria-label="Close asset inspector"
          onClick={onClose}
        >
          <X size={16} aria-hidden="true" />
        </button>
      }
    >
      <div className="panel-body">
        <h2>{categoryLabels[j.request.asset_category]} study</h2>
        <p className="muted">
          {j.request.prompt ?? "Image-based mock reconstruction"}
        </p>
        <code className="job-id">{id}</code>
      </div>
      {primary && <ArtifactPreview jobId={id} artifact={primary} />}
      <div className="panel-body">
        <dl className="properties">
          <dt>Category</dt>
          <dd>{categoryLabels[j.request.asset_category]}</dd>
          <dt>Format</dt>
          <dd>{primary?.format.toUpperCase()}</dd>
          <dt>Model</dt>
          <dd>{j.request.model_id}</dd>
          <dt>Created</dt>
          <dd>{date(j.created_at)}</dd>
        </dl>
        <p className="small muted">
          Mock fixture. Unseen regions in future reconstructions may be
          approximated.
        </p>
        {primary && <DownloadButton jobId={id} artifact={primary} />}
        <Link className="text-link" to={`/jobs/${id}`}>
          Open source job & logs
        </Link>
      </div>
    </Panel>
  );
}
export function LibraryPage() {
  const [params, setParams] = useSearchParams(),
    jobs = useJobs({ status: "completed" });
  const search = params.get("q") ?? "",
    category = params.get("category") ?? "",
    format = params.get("format") ?? "",
    selected = params.get("asset");
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: key === "q" });
  };
  const assets = (jobs.data?.pages.flatMap((p) => p.jobs) ?? []).filter(
    (j) =>
      j.primary_artifact &&
      (!category || j.asset_category === category) &&
      (!format || j.primary_artifact.format === format) &&
      `${j.job_id} ${j.model_id} ${categoryLabels[j.asset_category]} ${j.primary_artifact.format}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="breadcrumb">Workspace / Local repository</div>
          <h1>Asset library</h1>
        </div>
        <Badge tone="success">Derived from completed jobs</Badge>
      </div>
      <div className="library-filters">
        <label className="search-field">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">Search assets</span>
          <input
            name="asset-search"
            autoComplete="off"
            value={search}
            onChange={(e) => update("q", e.target.value)}
            placeholder="Search category, model or job ID…"
            type="search"
          />
        </label>
        <label className="inline-field">
          Category
          <select
            name="library-category"
            value={category}
            onChange={(e) => update("category", e.target.value)}
          >
            <option value="">All categories</option>
            {Object.entries(categoryLabels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-field">
          Format
          <select
            name="library-format"
            value={format}
            onChange={(e) => update("format", e.target.value)}
          >
            <option value="">All formats</option>
            <option value="png">PNG · 2D image</option>
            <option value="glb">GLB · 3D model</option>
          </select>
        </label>
      </div>
      <div className={`library-layout ${selected ? "has-detail" : ""}`}>
        <div>
          <div className="section-title">
            <h2>Repository items</h2>
            <span className="muted">{assets.length} matching assets</span>
          </div>
          {jobs.error ? (
            <Failure error={jobs.error} />
          ) : jobs.isPending ? (
            <Loading />
          ) : !assets.length ? (
            <Empty title="No assets match your filters">
              <button onClick={() => setParams({})}>Clear filters</button> or{" "}
              <Link to="/generate/text-to-2d">generate an asset</Link>.
            </Empty>
          ) : (
            <div className="asset-grid">
              {assets.map((j) => (
                <AssetCard
                  key={j.job_id}
                  job={j}
                  onSelect={() => update("asset", j.job_id)}
                  selected={selected === j.job_id}
                />
              ))}
            </div>
          )}
          {jobs.hasNextPage && (
            <button
              onClick={() => void jobs.fetchNextPage()}
              disabled={jobs.isFetchingNextPage}
            >
              Load more completed jobs
            </button>
          )}
        </div>
        {selected && (
          <AssetDetail id={selected} onClose={() => update("asset", "")} />
        )}
      </div>
    </>
  );
}
