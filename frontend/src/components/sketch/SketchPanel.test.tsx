import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useEffect } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { SketchPanel } from "./SketchPanel";
import type { SketchHandle } from "./SketchCanvas";

// Excalidraw needs a real canvas; stand in a fake that exposes the same handle.
const fake = { empty: false, exportPng: vi.fn<() => Promise<Blob>>() };
vi.mock("./SketchCanvas", () => ({
  default: function FakeCanvas({ onReady }: { onReady(h: SketchHandle): void }) {
    useEffect(() => {
      onReady({ isEmpty: () => fake.empty, exportPng: () => fake.exportPng() });
    }, [onReady]);
    return <div>fake canvas</div>;
  },
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fake.empty = false;
  fake.exportPng.mockResolvedValue(
    new Blob([new Uint8Array([137, 80, 78, 71])], { type: "image/png" }),
  );
});

describe("SketchPanel", () => {
  it("exports, uploads with consent off, extracts and links to the editor", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: "u1", training_consent: false }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "graph-u1", version: 1 }, 201));
    const user = userEvent.setup();
    render(<SketchPanel />);

    const use = await screen.findByRole("button", { name: "Use this sketch" });
    await screen.findByText("fake canvas");
    expect(screen.getByRole("checkbox", { name: /model training/i })).not.toBeChecked();
    await user.click(use);

    expect(await screen.findByRole("link", { name: "Open in editor" })).toHaveAttribute(
      "href",
      "/graphs/graph-u1",
    );
    const [uploadUrl, uploadInit] = fetchMock.mock.calls[0];
    expect(uploadUrl).toMatch(/\/api\/v1\/uploads$/);
    const form = uploadInit?.body as FormData;
    expect(form.get("training_consent")).toBe("false");
    expect((form.get("file") as File).name).toMatch(/^sketch-.*\.png$/);
    expect((form.get("file") as File).type).toBe("image/png");
    expect(fetchMock.mock.calls[1][0]).toMatch(/\/uploads\/u1\/extract$/);
  });

  it("sends consent only when the user opts in", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse({ id: "u1", training_consent: true }, 201))
      .mockResolvedValueOnce(jsonResponse({ id: "graph-u1", version: 1 }, 201));
    const user = userEvent.setup();
    render(<SketchPanel />);
    await screen.findByText("fake canvas");
    await user.click(screen.getByRole("checkbox", { name: /model training/i }));
    await user.click(screen.getByRole("button", { name: "Use this sketch" }));
    await screen.findByRole("link", { name: "Open in editor" });
    expect((fetchMock.mock.calls[0][1]?.body as FormData).get("training_consent")).toBe("true");
  });

  it("refuses an empty canvas without calling the API", async () => {
    fake.empty = true;
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup();
    render(<SketchPanel />);
    await screen.findByText("fake canvas");
    await user.click(screen.getByRole("button", { name: "Use this sketch" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Draw something first.");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows backend rejections", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(
        { valid: false, error: { code: "image_too_small", message: "Image is 8x8px." } },
        422,
      ),
    );
    const user = userEvent.setup();
    render(<SketchPanel />);
    await screen.findByText("fake canvas");
    await user.click(screen.getByRole("button", { name: "Use this sketch" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Image is 8x8px.");
    expect(screen.queryByRole("link", { name: "Open in editor" })).not.toBeInTheDocument();
  });
});
