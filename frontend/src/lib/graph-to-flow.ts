/**
 * GraphDocument ⇄ React Flow conversion.
 *
 * Conventions
 * - `GraphNode.position` is an ABSOLUTE canvas coordinate. React Flow positions children relative
 *   to their parent, so we convert in both directions. Groups have no stored geometry in schema
 *   v1; their box is derived from their members on every `graphToFlow`.
 * - React Flow ids are namespaced (`n:` nodes, `g:` groups, `e:` edges) because the schema only
 *   guarantees uniqueness within each collection.
 * - `data.element` holds the original schema element and is the source of truth for every
 *   non-geometric field. The editor edits `data.element`; `flowToGraph` takes geometry
 *   (position, parent, edge endpoints) from React Flow and everything else from `data.element`.
 * - Elements whose geometry the user did not touch are returned unchanged (including a `null`
 *   or missing position), so a round trip with no edits is lossless.
 * - This module never changes provenance. Marking edits as `user_corrected` is the editor's job.
 * - Labels are plain strings rendered as React text. Never render them as HTML.
 */

import { MarkerType, type Edge, type Node, type XYPosition } from "@xyflow/react";
import type { GraphDocument, GraphEdge, GraphGroup, GraphNode } from "./graph-schema";

export const NODE_WIDTH = 180;
export const NODE_HEIGHT = 56;
export const GROUP_PADDING = 24;
export const GROUP_HEADER = 28;
const EMPTY_GROUP = { width: 240, height: 120 };

const NODE_PREFIX = "n:";
const GROUP_PREFIX = "g:";
const EDGE_PREFIX = "e:";

export const flowNodeId = (id: string) => NODE_PREFIX + id;
export const flowGroupId = (id: string) => GROUP_PREFIX + id;
export const flowEdgeId = (id: string) => EDGE_PREFIX + id;

/** Geometry as emitted by `graphToFlow`; used to detect what the user changed. */
interface Emitted {
  position: XYPosition;
  parentId: string | null;
}

export type GraphElementNodeData = {
  role: "node";
  /** Display only; `element.label` is authoritative. */
  label: string;
  element: GraphNode;
  emitted: Emitted;
};

export type GraphGroupNodeData = {
  role: "group";
  label: string;
  element: GraphGroup;
  emitted: Emitted;
};

export type GraphFlowNodeData = GraphElementNodeData | GraphGroupNodeData;
export type GraphFlowNode = Node<GraphFlowNodeData>;

export type GraphFlowEdgeData = { element: GraphEdge };
export type GraphFlowEdge = Edge<GraphFlowEdgeData>;

export interface FlowGraph {
  nodes: GraphFlowNode[];
  edges: GraphFlowEdge[];
}

export class GraphConversionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "GraphConversionError";
  }
}

interface Box {
  x: number;
  y: number;
  width: number;
  height: number;
}

const add = (a: XYPosition, b: XYPosition): XYPosition => ({ x: a.x + b.x, y: a.y + b.y });
const sub = (a: XYPosition, b: XYPosition): XYPosition => ({ x: a.x - b.x, y: a.y - b.y });
const samePos = (a: XYPosition, b: XYPosition) => a.x === b.x && a.y === b.y;
const INSET: XYPosition = { x: GROUP_PADDING, y: GROUP_PADDING + GROUP_HEADER };
const ORIGIN: XYPosition = { x: 0, y: 0 };

/** Groups ordered so every parent precedes its children (React Flow requires this). */
function groupsParentFirst(groups: GraphGroup[]): GraphGroup[] {
  const byId = new Map(groups.map((g) => [g.id, g]));
  const out: GraphGroup[] = [];
  const done = new Set<string>();
  const visit = (g: GraphGroup) => {
    if (done.has(g.id)) return;
    done.add(g.id); // schema forbids cycles; marking first also guards malformed input
    const parent = g.parent_id ? byId.get(g.parent_id) : undefined;
    if (parent) visit(parent);
    out.push(g);
  };
  groups.forEach(visit);
  return out;
}

export function graphToFlow(doc: GraphDocument): FlowGraph {
  const groupIds = new Set(doc.groups.map((g) => g.id));
  const groupOf = (id: string | null | undefined) => (id && groupIds.has(id) ? id : null);

  const childGroups = new Map<string, GraphGroup[]>();
  const memberNodes = new Map<string, GraphNode[]>();
  for (const g of doc.groups) {
    const p = groupOf(g.parent_id);
    if (p) childGroups.set(p, [...(childGroups.get(p) ?? []), g]);
  }
  for (const n of doc.nodes) {
    const p = groupOf(n.group_id);
    if (p) memberNodes.set(p, [...(memberNodes.get(p) ?? []), n]);
  }

  // Bounding box of each group from its positioned descendants (null if none are positioned).
  const boxes = new Map<string, Box | null>();
  const boxOf = (gid: string): Box | null => {
    if (boxes.has(gid)) return boxes.get(gid) ?? null;
    boxes.set(gid, null); // cycle guard
    const parts: Box[] = [];
    for (const n of memberNodes.get(gid) ?? [])
      if (n.position) parts.push({ ...n.position, width: NODE_WIDTH, height: NODE_HEIGHT });
    for (const c of childGroups.get(gid) ?? []) {
      const b = boxOf(c.id);
      if (b) parts.push(b);
    }
    let box: Box | null = null;
    if (parts.length) {
      const minX = Math.min(...parts.map((b) => b.x));
      const minY = Math.min(...parts.map((b) => b.y));
      const maxX = Math.max(...parts.map((b) => b.x + b.width));
      const maxY = Math.max(...parts.map((b) => b.y + b.height));
      box = {
        x: minX - INSET.x,
        y: minY - INSET.y,
        width: maxX - minX + 2 * GROUP_PADDING,
        height: maxY - minY + INSET.y + GROUP_PADDING,
      };
    }
    boxes.set(gid, box);
    return box;
  };

  const ordered = groupsParentFirst(doc.groups);
  const groupAbs = new Map<string, XYPosition>();
  const nodes: GraphFlowNode[] = [];

  for (const g of ordered) {
    const parent = groupOf(g.parent_id);
    const parentAbs = parent ? groupAbs.get(parent) : undefined;
    const box = boxOf(g.id);
    const abs = box ? { x: box.x, y: box.y } : parentAbs ? add(parentAbs, INSET) : ORIGIN;
    groupAbs.set(g.id, abs);
    const position = sub(abs, parentAbs ?? ORIGIN);
    const parentId = parent ? flowGroupId(parent) : null;
    nodes.push({
      id: flowGroupId(g.id),
      type: "group",
      position,
      ...(parentId ? { parentId } : {}),
      width: box?.width ?? EMPTY_GROUP.width,
      height: box?.height ?? EMPTY_GROUP.height,
      data: { role: "group", label: g.label, element: g, emitted: { position, parentId } },
    });
  }

  for (const n of doc.nodes) {
    const parent = groupOf(n.group_id);
    const parentAbs = parent ? groupAbs.get(parent) : undefined;
    const position = n.position ? sub(n.position, parentAbs ?? ORIGIN) : parentAbs ? INSET : ORIGIN;
    const parentId = parent ? flowGroupId(parent) : null;
    nodes.push({
      id: flowNodeId(n.id),
      type: "default",
      position: { ...position },
      ...(parentId ? { parentId } : {}),
      data: {
        role: "node",
        label: n.label,
        element: n,
        emitted: { position: { ...position }, parentId },
      },
    });
  }

  const edges: GraphFlowEdge[] = doc.edges.map((e) => {
    const marker = { type: MarkerType.ArrowClosed };
    const inferred = e.evidence === "inferred";
    return {
      id: flowEdgeId(e.id),
      source: flowNodeId(e.source),
      target: flowNodeId(e.target),
      ...(e.label ? { label: e.label } : {}),
      ...(e.direction !== "none" ? { markerEnd: marker } : {}),
      ...(e.direction === "bidirectional" ? { markerStart: marker } : {}),
      ...(inferred ? { className: "edge-inferred", style: { strokeDasharray: "6 4" } } : {}),
      data: { element: e },
    };
  });

  return { nodes, edges };
}

function stripPrefix(flowId: string, prefix: string, what: string): string {
  if (!flowId.startsWith(prefix)) {
    throw new GraphConversionError(`${what} '${flowId}' is not a ${prefix}-prefixed flow id`);
  }
  return flowId.slice(prefix.length);
}

/**
 * Rebuild a GraphDocument from React Flow state. Document-level fields (id, title, metadata)
 * come from `base`. Group order follows `base`; new groups are appended.
 */
export function flowToGraph(
  flow: { nodes: GraphFlowNode[]; edges: GraphFlowEdge[] },
  base: GraphDocument,
): GraphDocument {
  const byId = new Map(flow.nodes.map((n) => [n.id, n]));

  const parentOf = (n: GraphFlowNode) => n.parentId ?? null;
  const moved = new Map<string, boolean>();
  const isMoved = (n: GraphFlowNode): boolean => {
    const cached = moved.get(n.id);
    if (cached !== undefined) return cached;
    moved.set(n.id, true); // cycle guard
    const { emitted } = n.data;
    const parent = parentOf(n);
    const parentNode = parent ? byId.get(parent) : undefined;
    const result =
      !samePos(n.position, emitted.position) ||
      parent !== emitted.parentId ||
      (parentNode ? isMoved(parentNode) : false);
    moved.set(n.id, result);
    return result;
  };
  const absOf = (n: GraphFlowNode, seen = new Set<string>()): XYPosition => {
    const parent = parentOf(n);
    const parentNode = parent ? byId.get(parent) : undefined;
    if (!parentNode || seen.has(n.id)) return n.position;
    seen.add(n.id);
    return add(absOf(parentNode, seen), n.position);
  };
  const groupIdOf = (n: GraphFlowNode): string | null => {
    const parent = parentOf(n);
    if (!parent) return null;
    if (!byId.get(parent))
      throw new GraphConversionError(`'${n.id}' has unknown parent '${parent}'`);
    return stripPrefix(parent, GROUP_PREFIX, "parent");
  };

  const nodes: GraphNode[] = [];
  const groups: GraphGroup[] = [];
  for (const fn of flow.nodes) {
    const parentChanged = parentOf(fn) !== fn.data.emitted.parentId;
    if (fn.data.role === "node") {
      const el = fn.data.element;
      const out: GraphNode = { ...el };
      if (parentChanged) out.group_id = groupIdOf(fn);
      if (isMoved(fn)) out.position = absOf(fn);
      nodes.push(out);
    } else {
      const el = fn.data.element;
      const out: GraphGroup = { ...el };
      if (parentChanged) out.parent_id = groupIdOf(fn);
      groups.push(out);
    }
  }

  const order = new Map(base.groups.map((g, i) => [g.id, i]));
  const rank = (g: GraphGroup) => order.get(g.id) ?? Number.MAX_SAFE_INTEGER;
  groups.sort((a, b) => rank(a) - rank(b)); // stable: new groups keep their relative order

  const edges: GraphEdge[] = flow.edges.map((fe) => {
    if (!fe.data?.element) {
      throw new GraphConversionError(`edge '${fe.id}' has no schema element in data`);
    }
    const el = fe.data.element;
    const source = stripPrefix(fe.source, NODE_PREFIX, `edge '${fe.id}' source`);
    const target = stripPrefix(fe.target, NODE_PREFIX, `edge '${fe.id}' target`);
    return source === el.source && target === el.target ? { ...el } : { ...el, source, target };
  });

  return { ...base, nodes, edges, groups };
}
