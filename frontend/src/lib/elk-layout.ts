/**
 * ELK auto-layout for a GraphDocument, with groups as compound (hierarchical) nodes.
 *
 * Auto-layout is an automated change, so it respects locks:
 *   - unlocked nodes, and locked nodes that have no position yet, get the layout position;
 *   - locked nodes that already have a position ("pinned") are NOT moved. Their layout
 *     positions come back as `proposals` that the user can approve with `applyProposals`.
 * Provenance is never changed by layout.
 *
 * `elk` is injected so the browser can run ELK in a web worker (`layout-client.ts`) while tests
 * run it in-process.
 */

import type { ElkExtendedEdge, ElkNode } from "elkjs/lib/elk-api";
import type { GraphDocument, Position } from "./graph-schema";
import { GROUP_HEADER, GROUP_PADDING, NODE_HEIGHT, NODE_WIDTH } from "./graph-to-flow";

export interface ElkLike {
  layout(graph: ElkNode): Promise<ElkNode>;
}

export interface LayoutProposal {
  nodeId: string;
  from: Position;
  to: Position;
}

export interface LayoutResult {
  doc: GraphDocument;
  proposals: LayoutProposal[];
}

// Layer gap leaves room for the ~120px inferred-edge badge (label, confidence, accept/reject).
// ELK options do not inherit into compound nodes, so groups repeat the spacing.
const SPACING = {
  "elk.spacing.nodeNode": "40",
  "elk.layered.spacing.nodeNodeBetweenLayers": "140",
  "elk.spacing.edgeLabel": "8",
};
const ROOT_OPTIONS = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.hierarchyHandling": "INCLUDE_CHILDREN",
  "elk.edgeRouting": "ORTHOGONAL",
  ...SPACING,
};
const GROUP_OPTIONS = {
  ...SPACING,
  "elk.padding": `[top=${GROUP_PADDING + GROUP_HEADER},left=${GROUP_PADDING},bottom=${GROUP_PADDING},right=${GROUP_PADDING}]`,
};

// ELK ids share one namespace; reuse the flow prefixes for the same reason.
const nodeKey = (id: string) => `n:${id}`;
const groupKey = (id: string) => `g:${id}`;

export function toElkGraph(doc: GraphDocument): ElkNode {
  const groupIds = new Set(doc.groups.map((g) => g.id));
  const parentKey = (gid: string | null | undefined) =>
    gid && groupIds.has(gid) ? groupKey(gid) : "root";

  const elkNodes = new Map<string, ElkNode>([
    ["root", { id: "root", layoutOptions: ROOT_OPTIONS, children: [] }],
  ]);
  for (const g of doc.groups) {
    elkNodes.set(groupKey(g.id), {
      id: groupKey(g.id),
      layoutOptions: GROUP_OPTIONS,
      children: [],
    });
  }
  const attach = (parent: string, child: ElkNode) => elkNodes.get(parent)?.children?.push(child);

  // Group nesting is acyclic (validated by the backend schema), so this builds a tree.
  for (const g of doc.groups) {
    attach(parentKey(g.parent_id), elkNodes.get(groupKey(g.id)) as ElkNode);
  }
  for (const n of doc.nodes) {
    attach(parentKey(n.group_id), { id: nodeKey(n.id), width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  const edges: ElkExtendedEdge[] = doc.edges.map((e) => ({
    id: `e:${e.id}`,
    sources: [nodeKey(e.source)],
    targets: [nodeKey(e.target)],
  }));
  return { ...(elkNodes.get("root") as ElkNode), edges };
}

/** Absolute top-left position of every laid-out schema node, keyed by schema id. */
function absolutePositions(root: ElkNode): Map<string, Position> {
  const out = new Map<string, Position>();
  const walk = (node: ElkNode, ox: number, oy: number) => {
    for (const child of node.children ?? []) {
      const x = ox + (child.x ?? 0);
      const y = oy + (child.y ?? 0);
      if (child.id.startsWith("n:")) out.set(child.id.slice(2), { x, y });
      walk(child, x, y);
    }
  };
  walk(root, 0, 0);
  return out;
}

const samePos = (a: Position, b: Position) => a.x === b.x && a.y === b.y;

export async function layoutGraph(doc: GraphDocument, elk: ElkLike): Promise<LayoutResult> {
  const laidOut = await elk.layout(toElkGraph(doc));
  const positions = absolutePositions(laidOut);
  const proposals: LayoutProposal[] = [];

  const nodes = doc.nodes.map((n) => {
    const to = positions.get(n.id);
    if (!to) return n;
    if (n.provenance.locked && n.position) {
      if (!samePos(n.position, to)) proposals.push({ nodeId: n.id, from: n.position, to });
      return n;
    }
    return { ...n, position: to };
  });
  return { doc: { ...doc, nodes }, proposals };
}

/** The user approved moving pinned nodes: apply the proposed positions. */
export function applyProposals(doc: GraphDocument, proposals: LayoutProposal[]): GraphDocument {
  const byId = new Map(proposals.map((p) => [p.nodeId, p.to]));
  return {
    ...doc,
    nodes: doc.nodes.map((n) => {
      const to = byId.get(n.id);
      return to ? { ...n, position: to } : n;
    }),
  };
}
