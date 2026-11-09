import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ELK from "elkjs/lib/elk.bundled.js";
import { beforeAll, describe, expect, it, vi } from "vitest";
import type { GraphDocument } from "@/lib/graph-schema";
import { GraphEditor } from "./GraphEditor";

// jsdom lacks the browser APIs React Flow measures with.
beforeAll(() => {
  globalThis.ResizeObserver ??= class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
  globalThis.DOMMatrixReadOnly ??= class {
    m22 = 1;
  } as unknown as typeof DOMMatrixReadOnly;
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const ai = { origin: "ai_extracted", locked: false } as const;
const doc: GraphDocument = {
  schema_version: "1.0",
  id: "graph-1",
  title: "Checkout flow",
  groups: [],
  nodes: [
    { id: "a", label: "Client", kind: "actor", confidence: 0.9, provenance: ai, attributes: {} },
    { id: "b", label: "API", kind: "service", confidence: 0.9, provenance: ai, attributes: {} },
  ],
  edges: [
    {
      id: "e1",
      source: "a",
      target: "b",
      direction: "forward",
      evidence: "inferred",
      confidence: 0.6,
      rationale: "Boxes are adjacent.",
      provenance: ai,
    },
  ],
  metadata: { created_at: "2026-11-08T00:00:00Z", warnings: [] },
};
const record = (document: GraphDocument, version = 1) => ({
  id: "graph-1",
  title: document.title,
  version,
  created_at: "2026-11-08T00:00:00Z",
  updated_at: "2026-11-08T00:00:00Z",
  document,
});

const elk = new ELK();

describe("GraphEditor", () => {
  it("lays out, lets the user accept an inferred edge, and saves it as a locked correction", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(record(doc)))
      .mockImplementationOnce(async (_url, init) => {
        const body = JSON.parse(init?.body as string) as { document: GraphDocument };
        return jsonResponse(record(body.document, 2));
      });
    const user = userEvent.setup();
    render(<GraphEditor graphId="graph-1" elk={elk} />);

    expect(await screen.findByRole("heading", { name: "Checkout flow" })).toBeInTheDocument();
    expect(screen.getByText("1 inferred to review")).toBeInTheDocument();
    const review = screen.getByRole("region", { name: /review inferred connections/i });
    expect(within(review).getByText("Boxes are adjacent.")).toBeInTheDocument();
    // Unpositioned nodes were auto-laid out on load, which counts as an unsaved change.
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();

    await user.click(
      within(review).getByRole("button", { name: "Accept inferred connection Client to API" }),
    );
    expect(within(review).getByText("Nothing to review.")).toBeInTheDocument();
    expect(screen.queryByText(/inferred to review/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("Saved version 2.")).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toMatch(/\/api\/v1\/graphs\/graph-1$/);
    const sent = JSON.parse(init?.body as string) as {
      base_version: number;
      document: GraphDocument;
    };
    expect(sent.base_version).toBe(1);
    expect(sent.document.edges[0]).toMatchObject({
      evidence: "observed",
      confidence: 1,
      provenance: { origin: "user_corrected", locked: true },
    });
    expect(sent.document.nodes.every((n) => n.position)).toBe(true);
    // Layout is automated: it must not stamp provenance on nodes.
    expect(sent.document.nodes.map((n) => n.provenance)).toEqual([ai, ai]);
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("rejecting removes the inferred edge", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(jsonResponse(record(doc)));
    const user = userEvent.setup();
    render(<GraphEditor graphId="graph-1" elk={elk} />);
    await user.click(
      await screen.findByRole("button", { name: "Reject inferred connection Client to API" }),
    );
    expect(screen.getByText("Nothing to review.")).toBeInTheDocument();
  });

  it("shows a version conflict with a reload option", async () => {
    const placed = {
      ...doc,
      nodes: doc.nodes.map((n, i) => ({ ...n, position: { x: i * 300, y: 0 } })),
    };
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(record(placed)))
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "graph_version_conflict",
              message: "Graph was changed elsewhere (now at version 3). Reload it before saving.",
              current_version: 3,
            },
          },
          409,
        ),
      );
    const user = userEvent.setup();
    render(<GraphEditor graphId="graph-1" elk={elk} />);
    await user.click(
      await screen.findByRole("button", { name: "Accept inferred connection Client to API" }),
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/changed elsewhere/);
    expect(screen.getByRole("button", { name: /reload latest/i })).toBeInTheDocument();
  });

  it("shows an error when the graph cannot be loaded", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse({ error: { code: "graph_not_found", message: "Graph 'x' not found." } }, 404),
    );
    render(<GraphEditor graphId="x" elk={elk} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Graph 'x' not found.");
  });
});
