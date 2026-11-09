import { readFileSync } from "node:fs";
import path from "node:path";
import ELK from "elkjs/lib/elk.bundled.js";
import { describe, expect, it } from "vitest";
import { applyProposals, layoutGraph, toElkGraph } from "./elk-layout";
import type { GraphDocument } from "./graph-schema";

const repoRoot = path.resolve(__dirname, "../../..");
const raw = JSON.parse(
  readFileSync(path.join(repoRoot, "shared/examples/three-tier.graph.json"), "utf-8"),
) as GraphDocument;
// The example omits defaults; fill in provenance like the backend does.
const example: GraphDocument = {
  ...raw,
  nodes: raw.nodes.map((n) => ({
    ...n,
    provenance: n.provenance ?? { origin: "ai_extracted", locked: false },
  })),
};

const elk = new ELK();

describe("toElkGraph", () => {
  it("nests nodes inside compound group nodes", () => {
    const g = toElkGraph(example);
    const aws = g.children?.find((c) => c.id === "g:aws");
    const priv = aws?.children?.find((c) => c.id === "g:private");
    expect(g.children?.map((c) => c.id).sort()).toEqual(["g:aws", "n:user"]);
    expect(aws?.children?.map((c) => c.id).sort()).toEqual(["g:private", "n:lb"]);
    expect(priv?.children?.map((c) => c.id).sort()).toEqual(["n:api", "n:cache", "n:db"]);
    expect(g.edges).toHaveLength(4);
    expect(g.layoutOptions?.["elk.hierarchyHandling"]).toBe("INCLUDE_CHILDREN");
  });
});

describe("layoutGraph", () => {
  it("positions every unpinned node with absolute coordinates and no overlaps", async () => {
    const { doc, proposals } = await layoutGraph(example, elk);
    expect(proposals).toEqual([]); // `db` is locked but had no position yet
    const pos = doc.nodes.map((n) => n.position);
    expect(pos.every(Boolean)).toBe(true);
    // Members of nested groups are placed to the right of the user (layered, direction RIGHT).
    const x = (id: string) => doc.nodes.find((n) => n.id === id)?.position?.x ?? NaN;
    expect(x("lb")).toBeGreaterThan(x("user"));
    expect(x("api")).toBeGreaterThan(x("lb"));
    const keys = new Set(pos.map((p) => `${p?.x},${p?.y}`));
    expect(keys.size).toBe(pos.length);
    // Provenance untouched by automated layout.
    expect(doc.nodes.map((n) => n.provenance)).toEqual(example.nodes.map((n) => n.provenance));
  });

  it("never moves pinned locked nodes; proposes instead, applied only on approval", async () => {
    const pinned: GraphDocument = {
      ...example,
      nodes: example.nodes.map((n) =>
        n.id === "db" ? { ...n, position: { x: -999, y: -999 } } : n,
      ),
    };
    const { doc, proposals } = await layoutGraph(pinned, elk);
    expect(doc.nodes.find((n) => n.id === "db")?.position).toEqual({ x: -999, y: -999 });
    expect(proposals).toHaveLength(1);
    expect(proposals[0]).toMatchObject({ nodeId: "db", from: { x: -999, y: -999 } });

    const approved = applyProposals(doc, proposals);
    expect(approved.nodes.find((n) => n.id === "db")?.position).toEqual(proposals[0].to);
    expect(approved.nodes.find((n) => n.id === "db")?.provenance.locked).toBe(true);
  });
});
