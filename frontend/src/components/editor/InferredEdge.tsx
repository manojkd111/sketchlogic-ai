"use client";

import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type EdgeProps } from "@xyflow/react";
import type { GraphFlowEdge } from "@/lib/graph-to-flow";
import { useEditorActions } from "./EditorActions";

/** Inferred (model-guessed) edge: dashed amber, confidence badge, accept/reject in place. */
export function InferredEdge(props: EdgeProps<GraphFlowEdge>) {
  const { id, data, markerEnd, markerStart, style } = props;
  const actions = useEditorActions();
  const [path, labelX, labelY] = getSmoothStepPath(props);
  const el = data?.element;
  if (!el) return null;
  const name = `${actions.labelOf(el.source)} to ${actions.labelOf(el.target)}`;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        markerStart={markerStart}
        style={{ ...style, stroke: "#d97706", strokeWidth: 1.5 }}
      />
      <EdgeLabelRenderer>
        <div
          style={{ transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)` }}
          className="nodrag nopan pointer-events-auto absolute flex items-center gap-1 rounded-full border border-amber-400 bg-amber-50 px-2 py-0.5 text-[10px] text-amber-900 shadow-sm dark:bg-amber-950 dark:text-amber-200"
        >
          <span title={el.rationale ?? "Inferred by the model"}>
            {el.label ? `${el.label} · ` : ""}inferred {Math.round(el.confidence * 100)}%
          </span>
          <button
            type="button"
            aria-label={`Accept inferred connection ${name}`}
            onClick={() => actions.acceptEdge(el.id)}
            className="rounded px-1 font-bold text-emerald-700 hover:bg-emerald-100 dark:text-emerald-400"
          >
            ✓
          </button>
          <button
            type="button"
            aria-label={`Reject inferred connection ${name}`}
            onClick={() => actions.rejectEdge(el.id)}
            className="rounded px-1 font-bold text-red-700 hover:bg-red-100 dark:text-red-400"
          >
            ✕
          </button>
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
