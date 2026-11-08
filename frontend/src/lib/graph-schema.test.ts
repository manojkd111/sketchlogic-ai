import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import {
  EDGE_DIRECTIONS,
  EDGE_EVIDENCE,
  GRAPH_SCHEMA_VERSION,
  NODE_KINDS,
  ORIGINS,
  SOURCE_KINDS,
  type GraphDocument,
  isInferred,
} from "./graph-schema";

const repoRoot = path.resolve(__dirname, "../../..");
const schema = JSON.parse(
  readFileSync(path.join(repoRoot, "shared/schemas/graph.v1.json"), "utf-8"),
) as { $defs: Record<string, { enum?: string[] }>; properties: Record<string, { const?: string }> };

describe("graph schema mirror", () => {
  it.each([
    ["NodeKind", NODE_KINDS],
    ["EdgeDirection", EDGE_DIRECTIONS],
    ["EdgeEvidence", EDGE_EVIDENCE],
    ["Origin", ORIGINS],
    ["SourceKind", SOURCE_KINDS],
  ])("%s enum matches backend JSON Schema", (name, values) => {
    expect([...values].sort()).toEqual([...(schema.$defs[name].enum ?? [])].sort());
  });

  it("schema version matches", () => {
    expect(schema.properties.schema_version.const).toBe(GRAPH_SCHEMA_VERSION);
  });

  it("shared example parses and flags inferred edges", () => {
    const doc = JSON.parse(
      readFileSync(path.join(repoRoot, "shared/examples/three-tier.graph.json"), "utf-8"),
    ) as GraphDocument;
    expect(doc.schema_version).toBe("1.0");
    expect(doc.edges.filter(isInferred).map((e) => e.id)).toEqual(["e4"]);
  });
});
