/**
 * TypeScript mirror of the backend graph schema v1.0
 * (source of truth: backend/app/schemas/graph/v1.py, exported to shared/schemas/graph.v1.json).
 *
 * `graph-schema.test.ts` checks these enums against the exported JSON Schema so drift fails CI.
 * Never render AI output as code: these are plain data types only.
 */

export const GRAPH_SCHEMA_VERSION = "1.0" as const;

export const NODE_KINDS = [
  "component",
  "service",
  "database",
  "queue",
  "storage",
  "actor",
  "external",
  "process",
  "decision",
  "start_end",
  "note",
  "unknown",
] as const;
export const EDGE_DIRECTIONS = ["forward", "bidirectional", "none"] as const;
export const EDGE_EVIDENCE = ["observed", "inferred"] as const;
export const ORIGINS = [
  "ai_extracted",
  "ai_modified",
  "user_created",
  "user_corrected",
  "imported",
] as const;
export const SOURCE_KINDS = ["image", "xlsx", "sketch", "manual"] as const;

export type NodeKind = (typeof NODE_KINDS)[number];
export type EdgeDirection = (typeof EDGE_DIRECTIONS)[number];
export type EdgeEvidence = (typeof EDGE_EVIDENCE)[number];
export type Origin = (typeof ORIGINS)[number];
export type SourceKind = (typeof SOURCE_KINDS)[number];

export interface Provenance {
  origin: Origin;
  /** True when a user corrected this element; automated edits need approval. */
  locked: boolean;
}

export interface Position {
  x: number;
  y: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: NodeKind;
  group_id?: string | null;
  position?: Position | null;
  source_bbox?: BoundingBox | null;
  confidence: number;
  provenance: Provenance;
  attributes: Record<string, string>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string | null;
  direction: EdgeDirection;
  evidence: EdgeEvidence;
  confidence: number;
  rationale?: string | null;
  provenance: Provenance;
}

export interface GraphGroup {
  id: string;
  label: string;
  parent_id?: string | null;
  confidence: number;
  provenance: Provenance;
}

export interface SourceInfo {
  kind: SourceKind;
  upload_id?: string | null;
  filename?: string | null;
  width?: number | null;
  height?: number | null;
}

export interface GraphMetadata {
  source?: SourceInfo | null;
  provider?: string | null;
  model?: string | null;
  created_at: string;
  warnings: string[];
}

export interface GraphDocument {
  schema_version: typeof GRAPH_SCHEMA_VERSION;
  id: string;
  title: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  groups: GraphGroup[];
  metadata: GraphMetadata;
}

export function isInferred(edge: GraphEdge): boolean {
  return edge.evidence === "inferred";
}

export function isLocked(el: { provenance: Provenance }): boolean {
  return el.provenance.locked;
}
