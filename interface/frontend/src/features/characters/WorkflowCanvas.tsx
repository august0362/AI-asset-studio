import { useEffect, useRef, useState } from "react";
import type {
  StageId,
  WorkflowStage,
  ArtifactReference,
} from "../../api/characterTypes";
import { useCharacterText, EditorialStatus, FrozenThumbnail } from "./shared";
const layout = [
  [32, 60],
  [266, 60],
  [500, 60],
  [734, 60],
  [734, 340],
  [500, 340],
  [266, 340],
];
export function WorkflowCanvas({
  stages,
  selected,
  onSelect,
  outputs = [],
  characterId,
}: {
  stages: WorkflowStage[];
  selected: StageId;
  onSelect: (s: StageId) => void;
  outputs?: ArtifactReference[];
  characterId: string;
}) {
  const { t, text } = useCharacterText(),
    ref = useRef<HTMLDivElement>(null),
    drag = useRef<{ x: number; y: number; px: number; py: number } | null>(
      null,
    );
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const fit = () => {
    const width = ref.current?.clientWidth ?? 960;
    setView({ x: 12, y: 12, scale: Math.min(1, (width - 24) / 976) });
  };
  useEffect(() => {
    const element = ref.current!;
    const observer =
      typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => {
            const width = element.clientWidth;
            setView({ x: 12, y: 12, scale: Math.min(1, (width - 24) / 976) });
          })
        : null;
    observer?.observe(element);
    return () => observer?.disconnect();
  }, []);
  const zoom = (factor: number) =>
    setView((v) => ({
      ...v,
      scale: Math.max(0.35, Math.min(1.8, v.scale * factor)),
    }));
  useEffect(() => {
    const element = ref.current!;
    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      zoom(e.deltaY < 0 ? 1.1 : 1 / 1.1);
    };
    element.addEventListener("wheel", wheel, { passive: false });
    return () => element.removeEventListener("wheel", wheel);
  }, []);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has("node"))
      ref.current
        ?.querySelector<HTMLButtonElement>(`[data-node="${selected}"]`)
        ?.focus({ preventScroll: true });
  }, [selected]);
  return (
    <section className="workflow-shell" aria-label={t("char.canvas")}>
      <div className="workflow-toolbar">
        <strong>{t("char.workspace")}</strong>
        <div>
          <button onClick={() => zoom(1.2)} aria-label={t("char.zoomIn")}>
            +
          </button>
          <button onClick={() => zoom(1 / 1.2)} aria-label={t("char.zoomOut")}>
            −
          </button>
          <button onClick={fit}>{t("char.fit")}</button>
          <span>{t("char.pan")}</span>
        </div>
      </div>
      <p className="small muted workflow-help">{t("char.canvasHelp")}</p>
      <div
        ref={ref}
        className="workflow-viewport"
        tabIndex={0}
        aria-label={t("char.canvas")}
        onKeyDown={(e) => {
          if (e.key === "+" || e.key === "=") {
            e.preventDefault();
            zoom(1.2);
          }
          if (e.key === "-") {
            e.preventDefault();
            zoom(1 / 1.2);
          }
          if (
            ["ArrowRight", "ArrowDown", "ArrowLeft", "ArrowUp"].includes(e.key)
          ) {
            e.preventDefault();
            const focused =
              (e.target as HTMLElement).closest<HTMLElement>("[data-node]")
                ?.dataset.node ?? selected;
            const i = stages.findIndex((s) => s.config.stage_id === focused),
              delta = ["ArrowRight", "ArrowDown"].includes(e.key) ? 1 : -1;
            const next =
              stages[(i + delta + stages.length) % stages.length].config
                .stage_id;
            onSelect(next);
            ref.current
              ?.querySelector<HTMLButtonElement>(`[data-node="${next}"]`)
              ?.focus();
          }
        }}
        onPointerDown={(e) => {
          if ((e.target as Element).closest("button")) return;
          drag.current = { x: e.clientX, y: e.clientY, px: view.x, py: view.y };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const start = drag.current;
          if (start)
            setView((v) => ({
              ...v,
              x: start.px + e.clientX - start.x,
              y: start.py + e.clientY - start.y,
            }));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
        }}
      >
        <div
          className="workflow-plane"
          data-testid="workflow-plane"
          style={{
            transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
          }}
        >
          <svg
            className="workflow-edges"
            viewBox="0 0 980 580"
            aria-hidden="true"
          >
            <defs>
              <marker
                id="flow-arrow"
                markerWidth="8"
                markerHeight="8"
                refX="6"
                refY="3"
                orient="auto"
              >
                <path d="M0,0 L6,3 L0,6" />
              </marker>
            </defs>
            {stages.flatMap((to, i) =>
              to.config.dependencies.map((dep) => {
                const j = stages.findIndex(
                  (s) => s.config.stage_id === dep.stage_id,
                );
                if (j < 0) return null;
                const [x1, y1] = layout[j],
                  [x2, y2] = layout[i];
                const connected =
                    selected === dep.stage_id ||
                    selected === to.config.stage_id,
                  stale = to.state.approved?.stale_reasons.some(
                    (r) => r.upstream_stage_id === dep.stage_id,
                  );
                return (
                  <path
                    key={`${dep.stage_id}-${to.config.stage_id}`}
                    data-from={dep.stage_id}
                    data-to={to.config.stage_id}
                    data-kind={dep.kind}
                    data-connected={connected}
                    data-stale={stale}
                    className="workflow-edge"
                    markerEnd="url(#flow-arrow)"
                    d={`M${x1 + 202},${y1 + 88} C${x1 + 250},${y1 + 88} ${x2 - 52},${y2 + 88} ${x2},${y2 + 88}`}
                  />
                );
              }),
            )}
          </svg>
          {stages.map((s, i) => (
            <button
              type="button"
              key={s.config.stage_id}
              data-node={s.config.stage_id}
              data-testid={`node-${s.config.stage_id}`}
              className="workflow-node"
              style={{ left: layout[i][0], top: layout[i][1] }}
              aria-pressed={selected === s.config.stage_id}
              onClick={() => onSelect(s.config.stage_id)}
            >
              <span className="workflow-node-number">
                {s.config.stage_id.toUpperCase()}
              </span>
              <strong>{text(s.config.title_key)}</strong>
              {outputs
                .filter((a) => a.frozen_in.stage_id === s.config.stage_id)
                .slice(0, 1)
                .map((a) => (
                  <FrozenThumbnail
                    key={a.asset_id}
                    characterId={characterId}
                    assetId={a.asset_id}
                    alt={text(s.config.title_key)}
                  />
                ))}
              <EditorialStatus status={s.state.editorial_status} />
              <small>
                {s.config.availability !== "available"
                  ? t("char.planned")
                  : s.state.approved
                    ? t("char.revision", {
                        revision: s.state.approved.revision,
                      })
                    : t("char.draftVersion", {
                        version: s.state.draft_version,
                      })}
              </small>
              {s.state.blockers.some((b) => b.code === "STAGE_BLOCKED") && (
                <small>{t("char.missingInput")}</small>
              )}
              <span className="node-input">{t("char.inputPort")}</span>
              <span className="node-output">{t("char.outputPort")}</span>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
