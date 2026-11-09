import { describe, expect, it } from "vitest";
import {
  acceptInferredEdge,
  applyUserEdit,
  connectNodes,
  pendingInferredEdges,
  rejectInferredEdge,
  renameEdge,
  renameNode,
} from "./graph-edits";
import type { GraphDocument } from "./graph-schema";

const ai = { origin: "ai_extracted", locked: false } as const;
const base: GraphDocument = {
  schema_version: "1.0",
  id: "g",
  title: "T",
  groups: [{ id: "vpc", label: "VPC", confidence: 1, provenance: ai }],
  nodes: [
    { id: "a", label: "A", kind: "actor", confidence: 0.9, provenance: ai, attributes: {} },
    {
      id: "b",
      label: "B",
      kind: "service",
      group_id: "vpc",
      position: { x: 1, y: 2 },
      confidence: 0.8,
      provenance: ai,
      attributes: {},
    },
  ],
  edges: [
    {
      id: "e1",
      source: "a",
      target: "b",
      direction: "forward",
      evidence: "inferred",
      confidence: 0.6,
      rationale: "near",
      provenance: ai,
    },
    {
      id: "e2",
      source: "b",
      target: "a",
      direction: "forward",
      evidence: "observed",
      confidence: 1,
      provenance: ai,
    },
  ],
  metadata: { created_at: "2026-11-08T00:00:00Z", warnings: [] },
};

const corrected = { origin: "user_corrected", locked: true };

describe("applyUserEdit", () => {
  it("locks only what changed", () => {
    const moved = {
      ...base,
      nodes: base.nodes.map((n) => (n.id === "b" ? { ...n, position: { x: 50, y: 2 } } : n)),
    };
    const out = applyUserEdit(base, moved);
    expect(out.nodes[1].provenance).toEqual(corrected);
    expect(out.nodes[0]).toBe(base.nodes[0]);
    expect(out.edges).toEqual(base.edges);
    expect(out.groups).toEqual(base.groups);
  });

  it("marks new elements user_created and locked", () => {
    const added = {
      ...base,
      nodes: [...base.nodes, { ...base.nodes[0], id: "c", provenance: ai }],
    };
    expect(applyUserEdit(base, added).nodes[2].provenance).toEqual({
      origin: "user_created",
      locked: true,
    });
  });

  it("treats a provenance-only difference as no edit", () => {
    const same = { ...base, nodes: base.nodes.map((n) => ({ ...n })) };
    expect(applyUserEdit(base, same).nodes.map((n) => n.provenance)).toEqual([ai, ai]);
  });
});

describe("edit operations", () => {
  it("rename trims, caps length and locks; renaming to the same label is a no-op", () => {
    const out = renameNode(base, "a", "  Customer  ");
    expect(out.nodes[0]).toMatchObject({ label: "Customer", provenance: corrected });
    expect(renameNode(base, "a", "x".repeat(500)).nodes[0].label).toHaveLength(200);
    expect(renameNode(base, "a", "A").nodes[0].provenance).toEqual(ai);
  });

  it("renaming an edge to blank clears the label", () => {
    const labelled = renameEdge(base, "e2", "SQL");
    expect(labelled.edges[1]).toMatchObject({ label: "SQL", provenance: corrected });
    expect(renameEdge(labelled, "e2", "   ").edges[1].label).toBeNull();
  });

  it("accepting an inferred edge makes it observed, certain and locked", () => {
    const out = acceptInferredEdge(base, "e1");
    expect(out.edges[0]).toMatchObject({
      evidence: "observed",
      confidence: 1,
      rationale: "near",
      provenance: corrected,
    });
    expect(pendingInferredEdges(out)).toEqual([]);
  });

  it("reject removes only inferred edges", () => {
    expect(rejectInferredEdge(base, "e1").edges.map((e) => e.id)).toEqual(["e2"]);
    expect(rejectInferredEdge(base, "e2").edges).toHaveLength(2);
  });

  it("connect adds a locked user edge and ignores duplicates, self-loops and unknown ids", () => {
    const out = connectNodes(base, "a", "b");
    expect(out).toBe(base); // a->b already exists
    const fresh = connectNodes({ ...base, edges: [] }, "a", "b");
    expect(fresh.edges[0]).toMatchObject({
      source: "a",
      target: "b",
      evidence: "observed",
      provenance: { origin: "user_created", locked: true },
    });
    expect(fresh.edges[0].id).toMatch(/^[A-Za-z0-9_.:-]+$/);
    expect(connectNodes(base, "a", "a")).toBe(base);
    expect(connectNodes(base, "a", "zzz")).toBe(base);
  });
});
