import { useEffect, useRef, useState } from "react";
import type {
  StageId,
  WorkflowStage,
  ArtifactReference,
} from "../../api/characterTypes";
import { useCharacterText, EditorialStatus, FrozenThumbnail } from "./shared";
import { defaultLayout, readLayout, saveLayout, edgePath, type CanvasLayout } from "./canvasLayout";
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
    drag = useRef<{ x: number; y: number; px: number; py: number; node?: StageId; moved: boolean } | null>(
      null,
    ),
    suppressClick = useRef(false);
  const [positions, setPositions] = useState(() => readLayout(characterId));
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 });
  const fit = (layout: CanvasLayout = positions) => {
    const width = ref.current?.clientWidth ?? 960;
    const height = ref.current?.clientHeight || 620;
    const points = Object.values(layout),
      left = Math.min(...points.map(([x]) => x)) - 32,
      top = Math.min(...points.map(([, y]) => y)) - 40,
      right = Math.max(...points.map(([x]) => x)) + 234,
      bottom = Math.max(...points.map(([, y]) => y)) + 260,
      scale = Math.min(1, (width - 24) / (right - left), (height - 24) / (bottom - top));
    setView({ x: 12 - left * scale, y: 12 - top * scale, scale });
  };
  useEffect(() => saveLayout(characterId, positions), [characterId, positions]);
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
          <button onClick={() => fit()}>{t("char.fit")}</button>
          <button onClick={() => {
            setPositions(structuredClone(defaultLayout));
            fit(defaultLayout);
          }}>{t("char.resetLayout")}</button>
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
          if (e.button !== 0) return;
          drag.current = { x: e.clientX, y: e.clientY, px: view.x, py: view.y, moved: false };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const start = drag.current;
          if (!start) return;
          const dx = e.clientX - start.x, dy = e.clientY - start.y;
          if (!start.moved && Math.hypot(dx, dy) < 4) return;
          start.moved = true;
          if (start.node) {
            const node = start.node;
            suppressClick.current = true;
            setPositions((p) => ({ ...p, [node]: [start.px + dx / view.scale, start.py + dy / view.scale] }));
          } else
            setView((v) => ({
              ...v,
              x: start.px + dx,
              y: start.py + dy,
            }));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
        onPointerCancel={() => {
          drag.current = null;
          suppressClick.current = false;
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
            {stages.flatMap((to) =>
              to.config.dependencies.map((dep) => {
                const j = stages.findIndex(
                  (s) => s.config.stage_id === dep.stage_id,
                );
                if (j < 0) return null;
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
                    d={edgePath(positions[dep.stage_id], positions[to.config.stage_id])}
                  />
                );
              }),
            )}
          </svg>
          {stages.map((s) => (
            <button
              type="button"
              key={s.config.stage_id}
              data-node={s.config.stage_id}
              data-testid={`node-${s.config.stage_id}`}
              className="workflow-node"
              style={{ left: positions[s.config.stage_id][0], top: positions[s.config.stage_id][1] }}
              aria-pressed={selected === s.config.stage_id}
              onPointerDown={(e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                const node = s.config.stage_id;
                suppressClick.current = false;
                drag.current = { x: e.clientX, y: e.clientY, px: positions[node][0], py: positions[node][1], node, moved: false };
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onClick={(e) => {
                if (!suppressClick.current || e.detail === 0) onSelect(s.config.stage_id);
                suppressClick.current = false;
              }}
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
