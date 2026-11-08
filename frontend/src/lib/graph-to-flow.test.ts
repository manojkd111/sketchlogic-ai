import { readFileSync } from "node:fs";
import path from "node:path";
import { MarkerType } from "@xyflow/react";
import { describe, expect, it } from "vitest";
import type { GraphDocument, GraphEdge, GraphGroup, GraphNode } from "./graph-schema";
import {
  GROUP_HEADER,
  GROUP_PADDING,
  GraphConversionError,
  NODE_HEIGHT,
  NODE_WIDTH,
  type FlowGraph,
  type GraphFlowNode,
  flowEdgeId,
  flowGroupId,
  flowNodeId,
  flowToGraph,
  graphToFlow,
} from "./graph-to-flow";

const repoRoot = path.resolve(__dirname, "../../..");
const example = JSON.parse(
  readFileSync(path.join(repoRoot, "shared/examples/three-tier.graph.json"), "utf-8"),
) as GraphDocument;

const prov = { origin: "ai_extracted", locked: false } as const;
const node = (id: string, extra: Partial<GraphNode> = {}): GraphNode => ({
  id,
  label: id.toUpperCase(),
  kind: "service",
  confidence: 1,
  provenance: prov,
  attributes: {},
  ...extra,
});
const group = (id: string, extra: Partial<GraphGroup> = {}): GraphGroup => ({
  id,
  label: id,
  confidence: 1,
  provenance: prov,
  ...extra,
});
const edge = (id: string, source: string, target: string, extra: Partial<GraphEdge> = {}) =>
  ({
    id,
    source,
    target,
    direction: "forward",
    evidence: "observed",
    confidence: 1,
    provenance: prov,
    ...extra,
  }) satisfies GraphEdge;

function doc(parts: Partial<GraphDocument>): GraphDocument {
  return {
    schema_version: "1.0",
    id: "g",
    title: "T",
    nodes: [],
    edges: [],
    groups: [],
    metadata: { created_at: "2026-11-08T00:00:00Z", warnings: [] },
    ...parts,
  };
}

// Child is listed before its parent to check ordering; node ids collide with a group id.
const nested = doc({
  groups: [group("inner", { parent_id: "outer" }), group("outer"), group("empty")],
  nodes: [
    node("outer", { position: { x: 0, y: 0 } }),
    node("a", { group_id: "inner", position: { x: 100.1, y: 200.2 } }),
    node("b", { group_id: "inner", position: { x: 400, y: 200 } }),
    node("c", { group_id: "outer" }),
  ],
  edges: [
    edge("e1", "a", "b", { label: "calls" }),
    edge("e2", "b", "outer", {
      evidence: "inferred",
      confidence: 0.6,
      direction: "bidirectional",
      rationale: "near",
      provenance: { origin: "user_corrected", locked: true },
    }),
    edge("e3", "a", "c", { direction: "none" }),
  ],
});

const find = (flow: FlowGraph, id: string) => {
  const n = flow.nodes.find((x) => x.id === id);
  if (!n) throw new Error(`missing ${id}`);
  return n;
};
const moveTo = (flow: FlowGraph, id: string, patch: Partial<GraphFlowNode>): FlowGraph => ({
  ...flow,
  nodes: flow.nodes.map((n) => (n.id === id ? { ...n, ...patch } : n)),
});

describe("graphToFlow", () => {
  it("namespaces ids so a node and group may share a schema id", () => {
    const flow = graphToFlow(nested);
    expect(find(flow, flowNodeId("outer")).data.role).toBe("node");
    expect(find(flow, flowGroupId("outer")).type).toBe("group");
    expect(flow.edges.map((e) => e.id)).toEqual(["e:e1", "e:e2", "e:e3"]);
    expect(flow.edges[1]).toMatchObject({ source: "n:b", target: "n:outer" });
  });

  it("lists parent groups before their children", () => {
    const ids = graphToFlow(nested).nodes.map((n) => n.id);
    expect(ids.indexOf("g:outer")).toBeLessThan(ids.indexOf("g:inner"));
    expect(ids.indexOf("g:inner")).toBeLessThan(ids.indexOf("n:a"));
  });

  it("sizes groups around members and converts children to parent-relative positions", () => {
    const flow = graphToFlow(nested);
    const inner = find(flow, "g:inner");
    expect(inner.parentId).toBe("g:outer");
    // inner box = members a..b, padded.
    expect(inner.width).toBeCloseTo(400 - 100.1 + NODE_WIDTH + 2 * GROUP_PADDING);
    expect(inner.height).toBeCloseTo(
      200.2 - 200 + NODE_HEIGHT + GROUP_PADDING + GROUP_HEADER + GROUP_PADDING,
    );
    const a = find(flow, "n:a");
    expect(a.parentId).toBe("g:inner");
    expect(a.position.x).toBeCloseTo(GROUP_PADDING);
    expect(a.position.y).toBeCloseTo(GROUP_PADDING + GROUP_HEADER + 0.2);
    // Unpositioned node is placed inside its group; empty group gets a default size.
    expect(find(flow, "n:c").position).toEqual({
      x: GROUP_PADDING,
      y: GROUP_PADDING + GROUP_HEADER,
    });
    expect(find(flow, "g:empty")).toMatchObject({ width: 240, height: 120 });
  });

  it("styles inferred edges and maps direction to arrow markers", () => {
    const [e1, e2, e3] = graphToFlow(nested).edges;
    const arrow = { type: MarkerType.ArrowClosed };
    expect(e1).toMatchObject({ label: "calls", markerEnd: arrow });
    expect(e1.markerStart).toBeUndefined();
    expect(e1.className).toBeUndefined();
    expect(e2).toMatchObject({ markerEnd: arrow, markerStart: arrow, className: "edge-inferred" });
    expect(e2.style?.strokeDasharray).toBeTruthy();
    expect(e2.data?.element.rationale).toBe("near");
    expect(e3.markerEnd).toBeUndefined();
  });

  it("uses plain-string labels (no markup)", () => {
    const evil = doc({ nodes: [node("x", { label: "<img src=x onerror=alert(1)>" })] });
    const n = graphToFlow(evil).nodes[0];
    expect(typeof n.data.label).toBe("string");
    expect(n.data.label).toBe("<img src=x onerror=alert(1)>");
  });
});

describe("flowToGraph", () => {
  it.each([
    ["shared example", example],
    ["nested groups with null positions", nested],
  ])("round-trips %s losslessly (ids, provenance, evidence)", (_, input) => {
    expect(flowToGraph(graphToFlow(input), input)).toEqual(input);
  });

  it("writes the new absolute position of a moved node and nothing else", () => {
    const flow = graphToFlow(nested);
    const a = find(flow, "n:a");
    const out = flowToGraph(
      moveTo(flow, "n:a", { position: { x: a.position.x + 10, y: a.position.y } }),
      nested,
    );
    expect(out.nodes.find((n) => n.id === "a")?.position?.x).toBeCloseTo(110.1);
    expect(out.nodes.find((n) => n.id === "b")).toEqual(nested.nodes[2]);
    expect(out.nodes.find((n) => n.id === "c")?.position).toBeUndefined();
  });

  it("moving a group moves its descendants in absolute terms", () => {
    const flow = graphToFlow(nested);
    const outer = find(flow, "g:outer");
    const out = flowToGraph(
      moveTo(flow, "g:outer", { position: { x: outer.position.x + 50, y: outer.position.y } }),
      nested,
    );
    expect(out.nodes.find((n) => n.id === "a")?.position?.x).toBeCloseTo(150.1);
    expect(out.nodes.find((n) => n.id === "b")?.position?.x).toBeCloseTo(450);
    // Top-level node outside the group is untouched.
    expect(out.nodes.find((n) => n.id === "outer")).toEqual(nested.nodes[0]);
  });

  it("reparenting updates group_id / parent_id", () => {
    let flow = graphToFlow(nested);
    flow = moveTo(flow, "n:a", { parentId: undefined, position: { x: 5, y: 5 } });
    flow = moveTo(flow, "g:inner", { parentId: undefined });
    const out = flowToGraph(flow, nested);
    expect(out.nodes.find((n) => n.id === "a")).toMatchObject({
      group_id: null,
      position: { x: 5, y: 5 },
    });
    expect(out.groups.find((g) => g.id === "inner")?.parent_id).toBeNull();
    expect(out.groups.map((g) => g.id)).toEqual(["inner", "outer", "empty"]);
  });

  it("follows reconnected edges and drops deleted elements", () => {
    const flow = graphToFlow(nested);
    const out = flowToGraph(
      {
        nodes: flow.nodes.filter((n) => n.id !== "n:c"),
        edges: flow.edges
          .filter((e) => e.id !== flowEdgeId("e3"))
          .map((e) => (e.id === "e:e1" ? { ...e, target: "n:outer" } : e)),
      },
      nested,
    );
    expect(out.nodes.map((n) => n.id)).toEqual(["outer", "a", "b"]);
    expect(out.edges.map((e) => [e.id, e.source, e.target])).toEqual([
      ["e1", "a", "outer"],
      ["e2", "b", "outer"],
    ]);
    expect(out.edges[1].provenance).toEqual({ origin: "user_corrected", locked: true });
  });

  it("rejects edges attached to groups and edges without schema data", () => {
    const flow = graphToFlow(nested);
    const toGroup = { ...flow, edges: [{ ...flow.edges[0], target: "g:inner" }] };
    expect(() => flowToGraph(toGroup, nested)).toThrow(GraphConversionError);
    const bare = { ...flow, edges: [{ id: "x", source: "n:a", target: "n:b" }] };
    expect(() => flowToGraph(bare, nested)).toThrow(/no schema element/);
  });

  it("rejects a node whose parent is not a group", () => {
    const flow = moveTo(graphToFlow(nested), "n:b", { parentId: "n:a" });
    expect(() => flowToGraph(flow, nested)).toThrow(GraphConversionError);
  });
});
