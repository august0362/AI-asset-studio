import { useEffect, useRef, useState } from "react";
import type {
  StageId,
  WorkflowStage,
  ArtifactReference,
} from "../../api/characterTypes";
import { useCharacterText, EditorialStatus, FrozenThumbnail } from "./shared";
import {
  defaultLayout,
  readLayout,
  saveLayout,
  edgePath,
  type CanvasLayout,
  type Position,
} from "./canvasLayout";

type Drag = {
  x: number;
  y: number;
  /** Start position: the node's layout position, or the plane offset when panning. */
  px: number;
  py: number;
  scale: number;
  node?: StageId;
  element: HTMLElement;
  moved: boolean;
  dx: number;
  dy: number;
  frame: number;
};

/**
 * An edge carries data (D-039) when its upstream stage has an approved revision that is not stale,
 * and the downstream end is not marked stale by that upstream.
 */
export function flowsData(from: WorkflowStage | undefined, to: WorkflowStage, upstream: StageId) {
  const approved = from?.state.approved;
  return Boolean(
    approved &&
      !approved.stale &&
      !approved.stale_reasons.length &&
      !to.state.approved?.stale_reasons.some((r) => r.upstream_stage_id === upstream),
  );
}

export function WorkflowCanvas({
  stages,
  selected,
  onSelect,
  onOpen,
  outputs = [],
  characterId,
}: {
  stages: WorkflowStage[];
  selected: StageId;
  onSelect: (s: StageId) => void;
  /** Opens the stage's Stage Detail (double-click or Enter on a node). */
  onOpen?: (s: StageId) => void;
  outputs?: ArtifactReference[];
  characterId: string;
}) {
  const { t, text } = useCharacterText(),
    ref = useRef<HTMLDivElement>(null),
    plane = useRef<HTMLDivElement>(null),
    drag = useRef<Drag | null>(null),
    suppressClick = useRef(false),
    dragEndedAt = useRef(-Infinity);
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
  // Positions change only on drop or reset, so this writes once per change, never per pointer move.
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
  useEffect(() => () => cancelAnimationFrame(drag.current?.frame ?? 0), []);

  const livePosition = (d: Drag): Position => [d.px + d.dx / d.scale, d.py + d.dy / d.scale];
  /** Applies the latest pointer offset straight to the DOM, once per animation frame. */
  const paint = () => {
    const d = drag.current;
    if (!d) return;
    d.frame = 0;
    if (!d.node) {
      d.element.style.transform = `translate(${d.px + d.dx}px, ${d.py + d.dy}px) scale(${d.scale})`;
      return;
    }
    const node = d.node,
      at = livePosition(d);
    d.element.style.transform = `translate(${d.dx / d.scale}px, ${d.dy / d.scale}px)`;
    const layout = { ...positions, [node]: at };
    ref.current
      ?.querySelectorAll<SVGPathElement>(`path[data-from="${node}"], path[data-to="${node}"]`)
      .forEach((path) => {
        const from = path.dataset.from as StageId,
          to = path.dataset.to as StageId;
        path.setAttribute("d", edgePath(layout[from], layout[to]));
      });
  };
  const finish = (commit: boolean) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    cancelAnimationFrame(d.frame);
    delete d.element.dataset.dragging;
    if (!d.moved) return;
    if (d.node) {
      const node = d.node,
        at = livePosition(d);
      d.element.style.transform = "";
      dragEndedAt.current = performance.now();
      if (commit) setPositions((p) => ({ ...p, [node]: at }));
      else
        ref.current
          ?.querySelectorAll<SVGPathElement>(`path[data-from="${node}"], path[data-to="${node}"]`)
          .forEach((path) =>
            path.setAttribute(
              "d",
              edgePath(positions[path.dataset.from as StageId], positions[path.dataset.to as StageId]),
            ),
          );
    } else if (commit) setView((v) => ({ ...v, x: d.px + d.dx, y: d.py + d.dy }));
    else
      d.element.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
  };
  const open = (s: StageId) => {
    // A drag is never part of a double-click.
    if (performance.now() - dragEndedAt.current < 600) return;
    onOpen?.(s);
  };

  const byId = new Map(stages.map((s) => [s.config.stage_id, s]));
  const edges = stages.flatMap((to) =>
    to.config.dependencies
      .filter((dep) => byId.has(dep.stage_id))
      .map((dep) => ({
        from: dep.stage_id,
        to: to.config.stage_id,
        kind: dep.kind,
        connected: selected === dep.stage_id || selected === to.config.stage_id,
        stale: Boolean(
          to.state.approved?.stale_reasons.some((r) => r.upstream_stage_id === dep.stage_id),
        ),
        flowing: flowsData(byId.get(dep.stage_id), to, dep.stage_id),
        d: edgePath(positions[dep.stage_id], positions[to.config.stage_id]),
      })),
  );
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
          <button
            onClick={() => {
              setPositions(structuredClone(defaultLayout));
              fit(defaultLayout);
            }}
          >
            {t("char.resetLayout")}
          </button>
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
          if (e.button !== 0 || !plane.current) return;
          drag.current = {
            x: e.clientX,
            y: e.clientY,
            px: view.x,
            py: view.y,
            scale: view.scale,
            element: plane.current,
            moved: false,
            dx: 0,
            dy: 0,
            frame: 0,
          };
          e.currentTarget.setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          const d = drag.current;
          if (!d) return;
          const dx = e.clientX - d.x,
            dy = e.clientY - d.y;
          if (!d.moved && Math.hypot(dx, dy) < 4) return;
          if (!d.moved) {
            d.moved = true;
            if (d.node) {
              suppressClick.current = true;
              d.element.dataset.dragging = "true";
            }
          }
          d.dx = dx;
          d.dy = dy;
          if (!d.frame) d.frame = requestAnimationFrame(paint);
        }}
        onPointerUp={() => finish(true)}
        onPointerCancel={() => {
          finish(false);
          suppressClick.current = false;
        }}
      >
        <div
          ref={plane}
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
            {edges.map((edge) => (
              <path
                key={`${edge.from}-${edge.to}`}
                data-from={edge.from}
                data-to={edge.to}
                data-kind={edge.kind}
                data-connected={edge.connected}
                data-stale={edge.stale}
                data-flowing={edge.flowing}
                className="workflow-edge"
                markerEnd="url(#flow-arrow)"
                d={edge.d}
              />
            ))}
            {edges
              .filter((edge) => edge.flowing)
              .flatMap((edge) => [
                <path
                  key={`${edge.from}-${edge.to}-glow`}
                  data-from={edge.from}
                  data-to={edge.to}
                  className="workflow-flow-glow"
                  d={edge.d}
                />,
                <path
                  key={`${edge.from}-${edge.to}-flow`}
                  data-from={edge.from}
                  data-to={edge.to}
                  data-testid={`flow-${edge.from}-${edge.to}`}
                  className="workflow-flow"
                  d={edge.d}
                />,
              ])}
          </svg>
          {stages.map((s) => (
            <button
              type="button"
              key={s.config.stage_id}
              data-node={s.config.stage_id}
              data-testid={`node-${s.config.stage_id}`}
              data-status={s.state.editorial_status}
              className="workflow-node"
              style={{ left: positions[s.config.stage_id][0], top: positions[s.config.stage_id][1] }}
              aria-pressed={selected === s.config.stage_id}
              aria-keyshortcuts="Enter"
              onPointerDown={(e) => {
                if (e.button !== 0) return;
                e.stopPropagation();
                const node = s.config.stage_id;
                suppressClick.current = false;
                drag.current = {
                  x: e.clientX,
                  y: e.clientY,
                  px: positions[node][0],
                  py: positions[node][1],
                  scale: view.scale,
                  node,
                  element: e.currentTarget,
                  moved: false,
                  dx: 0,
                  dy: 0,
                  frame: 0,
                };
                e.currentTarget.setPointerCapture(e.pointerId);
              }}
              onClick={(e) => {
                if (!suppressClick.current || e.detail === 0) onSelect(s.config.stage_id);
                suppressClick.current = false;
              }}
              onDoubleClick={() => open(s.config.stage_id)}
              onKeyDown={(e) => {
                if (e.key !== "Enter" || !onOpen) return;
                e.preventDefault();
                onSelect(s.config.stage_id);
                onOpen(s.config.stage_id);
              }}
            >
              <span className="workflow-node-head">
                <span className="workflow-node-number">
                  {s.config.stage_id.toUpperCase()}
                </span>
                <EditorialStatus status={s.state.editorial_status} />
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
