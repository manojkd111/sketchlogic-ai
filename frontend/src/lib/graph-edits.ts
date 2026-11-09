/**
 * Pure, immutable editor operations on a GraphDocument.
 *
 * Product rule: a manual edit locks what it touches. Every user action is expressed as
 * `applyUserEdit(prev, next)`, which compares the two documents and stamps changed elements
 * `user_corrected` (forces `locked`) and new elements `user_created` + `locked`. Automated
 * changes (auto-layout) must NOT go through `applyUserEdit`; they keep provenance as-is and must
 * leave locked elements alone unless the user approves (see `elk-layout.ts`).
 */

import type { GraphDocument, GraphEdge, GraphGroup, GraphNode, Provenance } from "./graph-schema";

type Element = GraphNode | GraphEdge | GraphGroup;

const CORRECTED: Provenance = { origin: "user_corrected", locked: true };
const CREATED: Provenance = { origin: "user_created", locked: true };
export const MAX_LABEL = 200;

function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (typeof a !== "object" || typeof b !== "object" || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  // Treat a missing key and an explicit `undefined` as equal.
  const ka = Object.keys(a).filter((k) => (a as Record<string, unknown>)[k] !== undefined);
  const kb = Object.keys(b).filter((k) => (b as Record<string, unknown>)[k] !== undefined);
  if (ka.length !== kb.length) return false;
  return ka.every((k) =>
    deepEqual((a as Record<string, unknown>)[k], (b as Record<string, unknown>)[k]),
  );
}

function withoutProvenance<T extends Element>(el: T): Omit<T, "provenance"> {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { provenance, ...rest } = el;
  return rest;
}

function stamp<T extends Element>(prev: T[], next: T[]): T[] {
  const before = new Map(prev.map((el) => [el.id, el]));
  return next.map((el) => {
    const old = before.get(el.id);
    if (!old) return { ...el, provenance: { ...CREATED } };
    if (deepEqual(withoutProvenance(old), withoutProvenance(el))) return el;
    // Editing your own element is not "correcting" the AI: it stays user_created (and locked).
    const own = old.provenance.origin === "user_created";
    return { ...el, provenance: { ...(own ? CREATED : CORRECTED) } };
  });
}

/** Stamp provenance on everything the user changed between `prev` and `next`. */
export function applyUserEdit(prev: GraphDocument, next: GraphDocument): GraphDocument {
  return {
    ...next,
    nodes: stamp(prev.nodes, next.nodes),
    edges: stamp(prev.edges, next.edges),
    groups: stamp(prev.groups, next.groups),
  };
}

const cleanLabel = (label: string) => label.trim().slice(0, MAX_LABEL);

export function renameNode(doc: GraphDocument, id: string, label: string): GraphDocument {
  const value = cleanLabel(label);
  return applyUserEdit(doc, {
    ...doc,
    nodes: doc.nodes.map((n) => (n.id === id ? { ...n, label: value } : n)),
  });
}

export function renameEdge(doc: GraphDocument, id: string, label: string): GraphDocument {
  const value = cleanLabel(label) || null;
  return applyUserEdit(doc, {
    ...doc,
    edges: doc.edges.map((e) => (e.id === id ? { ...e, label: value } : e)),
  });
}

export function renameGroup(doc: GraphDocument, id: string, label: string): GraphDocument {
  const value = cleanLabel(label);
  return applyUserEdit(doc, {
    ...doc,
    groups: doc.groups.map((g) => (g.id === id ? { ...g, label: value } : g)),
  });
}

/** User confirms an inferred edge: it becomes observed with full confidence. */
export function acceptInferredEdge(doc: GraphDocument, id: string): GraphDocument {
  return applyUserEdit(doc, {
    ...doc,
    edges: doc.edges.map((e) =>
      e.id === id && e.evidence === "inferred" ? { ...e, evidence: "observed", confidence: 1 } : e,
    ),
  });
}

/** User rejects an inferred edge: it is removed. Observed edges are not affected. */
export function rejectInferredEdge(doc: GraphDocument, id: string): GraphDocument {
  return {
    ...doc,
    edges: doc.edges.filter((e) => !(e.id === id && e.evidence === "inferred")),
  };
}

function uniqueId(prefix: string, taken: Set<string>): string {
  let i = taken.size + 1;
  while (taken.has(`${prefix}${i}`)) i += 1;
  return `${prefix}${i}`;
}

/** Add a user-drawn edge. Duplicate source→target pairs and self-loops are ignored. */
export function connectNodes(doc: GraphDocument, source: string, target: string): GraphDocument {
  const known = new Set(doc.nodes.map((n) => n.id));
  if (source === target || !known.has(source) || !known.has(target)) return doc;
  if (doc.edges.some((e) => e.source === source && e.target === target)) return doc;
  const edge: GraphEdge = {
    id: uniqueId("e-user-", new Set(doc.edges.map((e) => e.id))),
    source,
    target,
    direction: "forward",
    evidence: "observed",
    confidence: 1,
    provenance: { ...CREATED },
  };
  return applyUserEdit(doc, { ...doc, edges: [...doc.edges, edge] });
}

export function pendingInferredEdges(doc: GraphDocument): GraphEdge[] {
  return doc.edges.filter((e) => e.evidence === "inferred");
}

export interface DeleteRequest {
  nodes?: string[];
  edges?: string[];
  groups?: string[];
}

/**
 * Delete elements the user chose. Removing a node removes its connections. Removing a group
 * keeps its contents: member nodes are ungrouped and child groups move up to the deleted
 * group's parent (those moves count as user edits and lock the affected elements).
 */
export function deleteElements(doc: GraphDocument, req: DeleteRequest): GraphDocument {
  const nodes = new Set(req.nodes ?? []);
  const edges = new Set(req.edges ?? []);
  const groups = new Set(req.groups ?? []);
  if (!nodes.size && !edges.size && !groups.size) return doc;

  // Where each deleted group's children go: the nearest surviving ancestor (or top level).
  const parentOf = new Map(doc.groups.map((g) => [g.id, g.parent_id ?? null]));
  const survivor = (gid: string | null | undefined): string | null => {
    let cur = gid ?? null;
    const seen = new Set<string>();
    while (cur && groups.has(cur) && !seen.has(cur)) {
      seen.add(cur);
      cur = parentOf.get(cur) ?? null;
    }
    return cur;
  };

  const next: GraphDocument = {
    ...doc,
    nodes: doc.nodes
      .filter((n) => !nodes.has(n.id))
      .map((n) =>
        n.group_id && groups.has(n.group_id) ? { ...n, group_id: survivor(n.group_id) } : n,
      ),
    edges: doc.edges.filter(
      (e) => !edges.has(e.id) && !nodes.has(e.source) && !nodes.has(e.target),
    ),
    groups: doc.groups
      .filter((g) => !groups.has(g.id))
      .map((g) =>
        g.parent_id && groups.has(g.parent_id) ? { ...g, parent_id: survivor(g.parent_id) } : g,
      ),
  };
  return applyUserEdit(doc, next);
}

export const NEW_NODE_GAP = 80;

/** Add a user-created node to the right of the diagram (or at the origin if empty). */
export function addNode(
  doc: GraphDocument,
  init: { label?: string; kind?: GraphNode["kind"]; width: number },
): { doc: GraphDocument; id: string } {
  const placed = doc.nodes.filter((n) => n.position);
  const position = placed.length
    ? {
        x: Math.max(...placed.map((n) => n.position?.x ?? 0)) + init.width + NEW_NODE_GAP,
        y: Math.min(...placed.map((n) => n.position?.y ?? 0)),
      }
    : { x: 0, y: 0 };
  const id = uniqueId("n-user-", new Set(doc.nodes.map((n) => n.id)));
  const node: GraphNode = {
    id,
    label: cleanLabel(init.label ?? "New node") || "New node",
    kind: init.kind ?? "component",
    position,
    confidence: 1,
    provenance: { ...CREATED },
    attributes: {},
  };
  return { doc: applyUserEdit(doc, { ...doc, nodes: [...doc.nodes, node] }), id };
}

export function setNodeKind(
  doc: GraphDocument,
  id: string,
  kind: GraphNode["kind"],
): GraphDocument {
  return applyUserEdit(doc, {
    ...doc,
    nodes: doc.nodes.map((n) => (n.id === id ? { ...n, kind } : n)),
  });
}
