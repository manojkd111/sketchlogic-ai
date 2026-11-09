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
    return { ...el, provenance: { ...CORRECTED } };
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
