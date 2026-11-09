"use client";

import { Handle, Position as Side, type NodeProps } from "@xyflow/react";
import { NODE_HEIGHT, NODE_WIDTH, type GraphFlowNode } from "@/lib/graph-to-flow";

const pct = (c: number) => `${Math.round(c * 100)}%`;

/** A graph node. Labels render as React text (escaped), never as HTML. */
export function GraphNodeView({ data, selected }: NodeProps<GraphFlowNode>) {
  if (data.role !== "node") return null;
  const n = data.element;
  const locked = n.provenance.locked;
  return (
    <div
      style={{ width: NODE_WIDTH, height: NODE_HEIGHT }}
      className={`flex flex-col justify-center rounded-lg border bg-white px-3 text-zinc-900 shadow-sm dark:bg-zinc-900 dark:text-zinc-100 ${
        selected
          ? "border-indigo-500 ring-2 ring-indigo-500/40"
          : "border-zinc-300 dark:border-zinc-700"
      }`}
    >
      <Handle type="target" position={Side.Left} />
      <span className="truncate text-sm font-medium" title={n.label}>
        {n.label || "Untitled"}
      </span>
      <span className="flex items-center gap-2 text-[10px] text-zinc-500">
        <span>{n.kind.replace("_", " ")}</span>
        {n.confidence < 1 && <span title="Extraction confidence">{pct(n.confidence)}</span>}
        {locked && (
          <span title="Manually corrected: AI changes need your approval">
            🔒<span className="sr-only">Locked</span>
          </span>
        )}
      </span>
      <Handle type="source" position={Side.Right} />
    </div>
  );
}

export function GraphGroupView({ data, selected }: NodeProps<GraphFlowNode>) {
  if (data.role !== "group") return null;
  return (
    <div
      className={`h-full w-full rounded-xl border-2 border-dashed bg-indigo-50/40 dark:bg-indigo-950/20 ${
        selected ? "border-indigo-500" : "border-indigo-300 dark:border-indigo-800"
      }`}
    >
      <span className="block truncate px-3 pt-1 text-xs font-semibold text-indigo-700 dark:text-indigo-300">
        {data.element.label}
        {data.element.provenance.locked && " 🔒"}
      </span>
    </div>
  );
}
