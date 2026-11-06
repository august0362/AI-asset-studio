import { useI18n } from "../../i18n";
import { Link, useSearchParams } from "react-router-dom";
import { Box, Search, X } from "lucide-react";
import { useJobs, useJob } from "../../api/queries";
import type { JobSummary } from "../../api/types";
import {
  ArtifactImage,
  ArtifactPreview,
  DownloadButton,
} from "../../components/ArtifactPreview";
import { Badge, Empty, Failure, Loading, Panel } from "../../components/ui";

function AssetCard({
  job,
  onSelect,
  selected,
}: {
  job: JobSummary;
  onSelect: () => void;
  selected: boolean;
}) {
  const { t, date, categoryLabels } = useI18n();
  const detail = useJob(job.job_id),
    preview = detail.data?.artifacts.find(
      (a) => a.artifact_id === detail.data?.preview?.artifact_id,
    );
  return (
    <article className={`asset-card ${selected ? "selected" : ""}`}>
      <button
        className="asset-open"
        onClick={onSelect}
        aria-label={t("library.inspect", {
          category: categoryLabels[job.asset_category],
          format: job.primary_artifact?.format.toUpperCase(),
          id: job.job_id,
        })}
      >
        <div className="asset-thumb">
          {preview ? (
            <ArtifactImage jobId={job.job_id} artifact={preview} />
          ) : (
            <Box size={40} aria-hidden="true" />
          )}
          <Badge>
            {job.primary_artifact?.format.toUpperCase()} · {t("common.mock")}
          </Badge>
        </div>
        <div className="asset-info">
          <span className="muted small">
            {categoryLabels[job.asset_category]}
          </span>
          <h2>
            {t("library.cardStudy", {
              category: categoryLabels[job.asset_category],
              study:
                job.primary_artifact?.format === "glb"
                  ? t("copy.3dStudy")
                  : t("copy.conceptStudy"),
            })}
          </h2>
          <p>{job.model_id}</p>
          <small>{date(job.created_at)}</small>
        </div>
      </button>
      <div className="asset-actions">
        <span className="badge success">{t("copy.completed")}</span>
        {job.primary_artifact && (
          <DownloadButton jobId={job.job_id} artifact={job.primary_artifact} />
        )}
      </div>
    </article>
  );
}
function AssetDetail({ id, onClose }: { id: string; onClose: () => void }) {
  const { t, date, categoryLabels } = useI18n();
  const job = useJob(id);
  if (job.error) return <Failure error={job.error} />;
  if (!job.data) return <Loading>{t("copy.loadingAssetDetails")}</Loading>;
  const j = job.data,
    primary = j.artifacts.find((a) => a.is_primary);
  return (
    <Panel
      title={t("copy.assetInspector")}
      extra={
        <button
          className="icon-button"
          aria-label={t("copy.closeAssetInspector")}
          onClick={onClose}
        >
          <X size={16} aria-hidden="true" />
        </button>
      }
    >
      <div className="panel-body">
        <h2>
          {t("library.study", {
            category: categoryLabels[j.request.asset_category],
          })}
        </h2>
        <p className="muted">
          {j.request.prompt ?? t("copy.imageBasedMockReconstruction")}
        </p>
        <code className="job-id">{id}</code>
      </div>
      {primary && <ArtifactPreview jobId={id} artifact={primary} />}
      <div className="panel-body">
        <dl className="properties">
          <dt>{t("copy.category")}</dt>
          <dd>{categoryLabels[j.request.asset_category]}</dd>
          <dt>{t("copy.format")}</dt>
          <dd>{primary?.format.toUpperCase()}</dd>
          <dt>{t("copy.model")}</dt>
          <dd>{j.request.model_id}</dd>
          <dt>{t("copy.created")}</dt>
          <dd>{date(j.created_at)}</dd>
        </dl>
        <p className="small muted">
          {t(
            "copy.mockFixtureUnseenRegionsInFutureReconstructionsMayBeApproximated",
          )}
        </p>
        {primary && <DownloadButton jobId={id} artifact={primary} />}
        <Link className="text-link" to={`/jobs/${id}`}>
          {t("copy.openSourceJobLogs")}
        </Link>
      </div>
    </Panel>
  );
}
export function LibraryPage() {
  const { t, number, categoryLabels } = useI18n();
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
          <div className="breadcrumb">{t("copy.workspaceLocalRepository")}</div>
          <h1>{t("copy.assetLibrary")}</h1>
        </div>
        <Badge tone="success">{t("copy.derivedFromCompletedJobs")}</Badge>
      </div>
      <div className="library-filters">
        <label className="search-field">
          <Search size={16} aria-hidden="true" />
          <span className="sr-only">{t("copy.searchAssets")}</span>
          <input
            name="asset-search"
            autoComplete="off"
            value={search}
            onChange={(e) => update("q", e.target.value)}
            placeholder={t("copy.searchCategoryModelOrJobId")}
            type="search"
          />
        </label>
        <label className="inline-field">
          {t("copy.category")}
          <select
            name="library-category"
            value={category}
            onChange={(e) => update("category", e.target.value)}
          >
            <option value="">{t("copy.allCategories")}</option>
            {Object.entries(categoryLabels).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-field">
          {t("copy.format")}
          <select
            name="library-format"
            value={format}
            onChange={(e) => update("format", e.target.value)}
          >
            <option value="">{t("copy.allFormats")}</option>
            <option value="png">{t("copy.png2DImage")}</option>
            <option value="glb">{t("copy.glb3DModel")}</option>
          </select>
        </label>
      </div>
      <div className={`library-layout ${selected ? "has-detail" : ""}`}>
        <div>
          <div className="section-title">
            <h2>{t("copy.repositoryItems")}</h2>
            <span className="muted">
              {t("library.matching", { count: number(assets.length, 0) })}
            </span>
          </div>
          {jobs.error ? (
            <Failure error={jobs.error} />
          ) : jobs.isPending ? (
            <Loading />
          ) : !assets.length ? (
            <Empty title={t("copy.noAssetsMatchYourFilters")}>
              <button onClick={() => setParams({})}>
                {t("copy.clearFilters")}
              </button>{" "}
              {t("copy.or")}{" "}
              <Link to="/generate/text-to-2d">{t("copy.generateAnAsset")}</Link>
              .
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
              {t("copy.loadMoreCompletedJobs")}
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
