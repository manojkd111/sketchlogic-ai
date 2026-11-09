"use client";

import "@xyflow/react/dist/style.css";

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type EdgeChange,
  type NodeChange,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, getGraph, saveGraph } from "@/lib/api";
import { applyProposals, layoutGraph, type ElkLike, type LayoutProposal } from "@/lib/elk-layout";
import {
  acceptInferredEdge,
  applyUserEdit,
  connectNodes,
  pendingInferredEdges,
  rejectInferredEdge,
  renameEdge,
  renameGroup,
  renameNode,
} from "@/lib/graph-edits";
import type { GraphDocument } from "@/lib/graph-schema";
import {
  flowToGraph,
  graphToFlow,
  schemaNodeId,
  type FlowGraph,
  type GraphFlowEdge,
  type GraphFlowNode,
} from "@/lib/graph-to-flow";
import { createWorkerElk } from "@/lib/layout-client";
import { EditorActionsContext, type EditorActions } from "./editor/EditorActions";
import { GraphGroupView, GraphNodeView } from "./editor/GraphNodeView";
import { InferredEdge } from "./editor/InferredEdge";
import { Sidebar, type Selection } from "./editor/Sidebar";

const nodeTypes = { graphNode: GraphNodeView, graphGroup: GraphGroupView };
const edgeTypes = { inferred: InferredEdge };

/** Pick editor renderers for converted elements. */
function decorate(flow: FlowGraph): FlowGraph {
  return {
    nodes: flow.nodes.map((n) => ({
      ...n,
      type: n.data.role === "group" ? "graphGroup" : "graphNode",
      ...(n.data.role === "group" ? { connectable: false } : {}),
    })),
    edges: flow.edges.map((e) => ({
      ...e,
      type: e.data?.element.evidence === "inferred" ? "inferred" : "smoothstep",
    })),
  };
}

type Status = { tone: "info" | "error"; text: string; conflict?: boolean } | null;

export interface GraphEditorProps {
  graphId: string;
  /** Layout engine; defaults to ELK in a web worker. Tests inject an in-process ELK. */
  elk?: ElkLike;
}

export function GraphEditor({ graphId, elk }: GraphEditorProps) {
  const [loadError, setLoadError] = useState<string | null>(null);
  const [doc, setDoc] = useState<GraphDocument | null>(null);
  const [saved, setSaved] = useState<{ version: number; json: string } | null>(null);
  const [nodes, setNodes] = useState<GraphFlowNode[]>([]);
  const [edges, setEdges] = useState<GraphFlowEdge[]>([]);
  const [selection, setSelection] = useState<Selection>(null);
  const [proposals, setProposals] = useState<LayoutProposal[]>([]);
  const [status, setStatus] = useState<Status>(null);
  const [busy, setBusy] = useState<null | "saving" | "layout">(null);
  const workerElk = useRef<ReturnType<typeof createWorkerElk> | null>(null);

  useEffect(() => () => workerElk.current?.terminate(), []);

  const engine = useCallback((): ElkLike => {
    if (elk) return elk;
    workerElk.current ??= createWorkerElk();
    return workerElk.current;
  }, [elk]);

  /** Make `next` the current document and rebuild the canvas from it. */
  const commit = useCallback((next: GraphDocument) => {
    setDoc(next);
    const flow = decorate(graphToFlow(next));
    setNodes(flow.nodes);
    setEdges(flow.edges);
  }, []);

  const runLayout = useCallback(
    async (current: GraphDocument) => {
      setBusy("layout");
      try {
        const result = await layoutGraph(current, engine());
        commit(result.doc);
        setProposals(result.proposals);
      } catch (err) {
        setStatus({ tone: "error", text: `Auto-layout failed: ${messageOf(err)}` });
      } finally {
        setBusy(null);
      }
    },
    [commit, engine],
  );

  const load = useCallback(
    (signal?: AbortSignal) =>
      fetchForEditing(graphId, engine(), signal).then(
        (loaded) => {
          if (signal?.aborted) return;
          setSaved({ version: loaded.version, json: JSON.stringify(loaded.stored) });
          setLoadError(null);
          setStatus(loaded.layoutError ? { tone: "error", text: loaded.layoutError } : null);
          setProposals(loaded.proposals);
          commit(loaded.doc);
        },
        (err: unknown) => {
          if (!signal?.aborted) setLoadError(messageOf(err));
        },
      ),
    [graphId, commit, engine],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const dirty = useMemo(() => !!doc && !!saved && JSON.stringify(doc) !== saved.json, [doc, saved]);

  const labels = useMemo(() => new Map(doc?.nodes.map((n) => [n.id, n.label]) ?? []), [doc]);
  const actions = useMemo<EditorActions>(
    () => ({
      acceptEdge: (id) => {
        if (doc) commit(acceptInferredEdge(doc, id));
      },
      rejectEdge: (id) => {
        if (!doc) return;
        commit(rejectInferredEdge(doc, id));
        setSelection((s) => (s?.kind === "edge" && s.id === id ? null : s));
      },
      labelOf: (id) => labels.get(id) || id,
    }),
    [doc, commit, labels],
  );

  // Deleting is not supported yet, so "remove" changes (e.g. Backspace) are ignored.
  const onNodesChange = useCallback(
    (changes: NodeChange<GraphFlowNode>[]) =>
      setNodes((ns) =>
        applyNodeChanges(
          changes.filter((c) => c.type !== "remove"),
          ns,
        ),
      ),
    [],
  );
  const onEdgesChange = useCallback(
    (changes: EdgeChange<GraphFlowEdge>[]) =>
      setEdges((es) =>
        applyEdgeChanges(
          changes.filter((c) => c.type !== "remove"),
          es,
        ),
      ),
    [],
  );

  const onNodeDragStop = useCallback(
    (_: unknown, __: GraphFlowNode, dragged: GraphFlowNode[]) => {
      if (!doc) return;
      const moved = new Map(dragged.map((n) => [n.id, n.position]));
      const current = nodes.map((n) => {
        const p = moved.get(n.id);
        return p ? { ...n, position: p } : n;
      });
      commit(applyUserEdit(doc, flowToGraph({ nodes: current, edges }, doc)));
    },
    [doc, nodes, edges, commit],
  );

  const onConnect = useCallback(
    (c: Connection) => {
      const source = schemaNodeId(c.source);
      const target = schemaNodeId(c.target);
      if (doc && source && target) commit(connectNodes(doc, source, target));
    },
    [doc, commit],
  );

  const onSelectionChange = useCallback(({ nodes: ns, edges: es }: OnSelectionChangeParams) => {
    const n = ns[0] as GraphFlowNode | undefined;
    const e = es[0] as GraphFlowEdge | undefined;
    if (n)
      setSelection({ kind: n.data.role === "group" ? "group" : "node", id: n.data.element.id });
    else if (e?.data) setSelection({ kind: "edge", id: e.data.element.id });
    else setSelection(null);
  }, []);

  const onRename = useCallback(
    (sel: NonNullable<Selection>, label: string) => {
      if (!doc) return;
      const rename = { node: renameNode, edge: renameEdge, group: renameGroup }[sel.kind];
      commit(rename(doc, sel.id, label));
    },
    [doc, commit],
  );

  const save = async () => {
    if (!doc || !saved) return;
    setBusy("saving");
    setStatus(null);
    try {
      const record = await saveGraph(graphId, saved.version, doc);
      setSaved({ version: record.version, json: JSON.stringify(record.document) });
      commit(record.document);
      setStatus({ tone: "info", text: `Saved version ${record.version}.` });
    } catch (err) {
      const conflict = err instanceof ApiError && err.code === "graph_version_conflict";
      setStatus({ tone: "error", text: messageOf(err), conflict });
    } finally {
      setBusy(null);
    }
  };

  if (loadError) {
    return (
      <div className="m-6 space-y-3">
        <p
          role="alert"
          className="rounded-lg bg-red-50 px-3 py-2 text-red-700 dark:bg-red-950/50 dark:text-red-300"
        >
          Could not open diagram: {loadError}
        </p>
        <Link href="/" className="text-sm font-medium underline">
          Back to uploads
        </Link>
      </div>
    );
  }
  if (!doc) return <p className="p-6 text-sm text-zinc-500">Loading diagram…</p>;

  const pending = pendingInferredEdges(doc).length;

  return (
    <EditorActionsContext.Provider value={actions}>
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="flex flex-wrap items-center gap-3 border-b border-zinc-200 px-4 py-2 text-sm dark:border-zinc-800">
          <Link href="/" className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
            ← SketchLogic
          </Link>
          <h1 className="font-semibold">{doc.title || "Untitled diagram"}</h1>
          <span className="text-xs text-zinc-500">v{saved?.version}</span>
          {pending > 0 && (
            <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {pending} inferred to review
            </span>
          )}
          <span aria-live="polite" className="text-xs text-zinc-500">
            {busy === "layout"
              ? "Laying out…"
              : busy === "saving"
                ? "Saving…"
                : dirty
                  ? "Unsaved changes"
                  : ""}
          </span>
          <div className="ml-auto flex gap-2">
            <button
              type="button"
              onClick={() => void runLayout(doc)}
              disabled={!!busy}
              className="rounded-lg px-3 py-1.5 font-medium hover:bg-zinc-100 disabled:opacity-50 dark:hover:bg-zinc-800"
            >
              Auto-layout
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={!!busy || !dirty}
              className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
            >
              Save
            </button>
          </div>
        </header>

        {proposals.length > 0 && (
          <div
            role="status"
            className="flex flex-wrap items-center gap-3 border-b border-amber-300 bg-amber-50 px-4 py-2 text-sm dark:border-amber-800 dark:bg-amber-950/40"
          >
            <span>
              Auto-layout kept {proposals.length} node{proposals.length === 1 ? "" : "s"} you
              positioned in place.
            </span>
            <button
              type="button"
              onClick={() => {
                commit(applyProposals(doc, proposals));
                setProposals([]);
              }}
              className="font-medium underline"
            >
              Move them too
            </button>
            <button
              type="button"
              onClick={() => setProposals([])}
              className="font-medium underline"
            >
              Keep positions
            </button>
          </div>
        )}

        {status && (
          <div
            role={status.tone === "error" ? "alert" : "status"}
            className={`flex items-center gap-3 px-4 py-2 text-sm ${
              status.tone === "error"
                ? "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300"
                : "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300"
            }`}
          >
            <span>{status.text}</span>
            {status.conflict && (
              <button type="button" onClick={() => void load()} className="font-medium underline">
                Reload latest (discards your unsaved changes)
              </button>
            )}
          </div>
        )}

        <div className="flex min-h-0 flex-1">
          <div className="min-h-0 flex-1" aria-label="Diagram canvas">
            <ReactFlow<GraphFlowNode, GraphFlowEdge>
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              edgeTypes={edgeTypes}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onNodeDragStop={onNodeDragStop}
              onConnect={onConnect}
              onSelectionChange={onSelectionChange}
              deleteKeyCode={null}
              fitView
              minZoom={0.1}
            >
              <Background />
              <Controls />
              <MiniMap pannable zoomable />
            </ReactFlow>
          </div>
          <Sidebar doc={doc} selection={selection} onRename={onRename} />
        </div>
      </div>
    </EditorActionsContext.Provider>
  );
}

/**
 * Fetch a graph and, if any node lacks a position, lay it out before the first render so
 * `fitView` frames real positions. A layout failure is reported but does not block editing.
 */
async function fetchForEditing(graphId: string, elk: ElkLike, signal?: AbortSignal) {
  const record = await getGraph(graphId, signal);
  const stored = record.document;
  if (!stored.nodes.some((n) => !n.position)) {
    return { version: record.version, stored, doc: stored, proposals: [], layoutError: null };
  }
  try {
    const result = await layoutGraph(stored, elk);
    return { version: record.version, stored, ...result, layoutError: null };
  } catch (err) {
    const layoutError = `Auto-layout failed: ${messageOf(err)}`;
    return { version: record.version, stored, doc: stored, proposals: [], layoutError };
  }
}

function messageOf(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : "Something went wrong.";
}
