import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, createGraph, getGraph, saveGraph } from "./api";
import type { GraphDocument } from "./graph-schema";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const doc = { schema_version: "1.0", id: "g1", title: "T", nodes: [], edges: [], groups: [] };
const record = {
  id: "g1",
  title: "T",
  version: 2,
  created_at: "2026-11-08T00:00:00Z",
  updated_at: "2026-11-08T00:00:00Z",
  document: doc,
};

afterEach(() => vi.restoreAllMocks());

describe("graph client", () => {
  it("creates a graph with a JSON body", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(record, 201));
    await createGraph(doc as unknown as GraphDocument);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/graphs$/);
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual(doc);
  });

  it("sends base_version on save and returns the new record", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(record));
    const saved = await saveGraph("g1", 1, doc as unknown as GraphDocument);
    expect(saved.version).toBe(2);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toMatch(/\/api\/v1\/graphs\/g1$/);
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(init?.body as string)).toEqual({ base_version: 1, document: doc });
  });

  it("surfaces version conflicts with the server's current version", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "graph_version_conflict",
            message: "Graph was changed elsewhere (now at version 3).",
            current_version: 3,
          },
        },
        409,
      ),
    );
    const err = await saveGraph("g1", 1, doc as unknown as GraphDocument).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "graph_version_conflict", currentVersion: 3 });
  });

  it("escapes graph ids in the path", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse(record));
    await getGraph("a/b");
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/graphs\/a%2Fb$/);
  });
});
