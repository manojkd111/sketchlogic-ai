import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UploadPanel } from "./UploadPanel";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const validResult = {
  valid: true,
  filename: "board.png",
  kind: "png",
  media_type: "image/png",
  size_bytes: 1234,
  width: 640,
  height: 480,
  sheet_names: [],
  warnings: [],
};

const pngFile = () => new File([new Uint8Array(1234)], "board.png", { type: "image/png" });

describe("UploadPanel", () => {
  it("validates then uploads with consent off by default", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(validResult))
      .mockResolvedValueOnce(
        jsonResponse({ ...validResult, id: "abc123", sha256: "f", training_consent: false }, 201),
      );
    const user = userEvent.setup();
    render(<UploadPanel />);

    await user.upload(screen.getByLabelText("Choose file"), pngFile());
    expect(await screen.findByText("640 × 480px")).toBeInTheDocument();
    expect(fetchMock.mock.calls[0][0]).toMatch(/\/api\/v1\/uploads\/validate$/);

    const consent = screen.getByRole("checkbox");
    expect(consent).not.toBeChecked();

    await user.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText("abc123")).toBeInTheDocument();
    const body = fetchMock.mock.calls[1][1]?.body as FormData;
    expect(body.get("training_consent")).toBe("false");
  });

  it("extracts the upload and links to the editor", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(validResult))
      .mockResolvedValueOnce(
        jsonResponse({ ...validResult, id: "abc123", sha256: "f", training_consent: false }, 201),
      )
      .mockResolvedValueOnce(jsonResponse({ id: "graph-abc123", version: 1 }, 201));
    const user = userEvent.setup();
    render(<UploadPanel />);
    await user.upload(screen.getByLabelText("Choose file"), pngFile());
    await user.click(await screen.findByRole("button", { name: "Upload" }));
    await user.click(await screen.findByRole("button", { name: "Extract diagram" }));

    const open = await screen.findByRole("link", { name: "Open in editor" });
    expect(open).toHaveAttribute("href", "/graphs/graph-abc123");
    expect(fetchMock.mock.calls[2][0]).toMatch(/\/api\/v1\/uploads\/abc123\/extract$/);
    expect(fetchMock.mock.calls[2][1]?.method).toBe("POST");
  });

  it("shows extraction errors", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse(validResult))
      .mockResolvedValueOnce(
        jsonResponse({ ...validResult, id: "abc123", sha256: "f", training_consent: false }, 201),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          {
            error: {
              code: "provider_unavailable",
              message: "provider 'local' is not implemented yet",
            },
          },
          503,
        ),
      );
    const user = userEvent.setup();
    render(<UploadPanel />);
    await user.upload(screen.getByLabelText("Choose file"), pngFile());
    await user.click(await screen.findByRole("button", { name: "Upload" }));
    await user.click(await screen.findByRole("button", { name: "Extract diagram" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not implemented yet");
  });

  it("shows backend validation errors", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      jsonResponse(
        { valid: false, error: { code: "corrupt_file", message: "Corrupt image." } },
        422,
      ),
    );
    const user = userEvent.setup();
    render(<UploadPanel />);
    await user.upload(screen.getByLabelText("Choose file"), pngFile());
    expect(await screen.findByRole("alert")).toHaveTextContent("Corrupt image.");
  });

  it("rejects unsupported files without calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const user = userEvent.setup({ applyAccept: false });
    render(<UploadPanel />);
    await user.upload(
      screen.getByLabelText("Choose file"),
      new File(["x"], "notes.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Unsupported file type");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports an unreachable backend", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const user = userEvent.setup();
    render(<UploadPanel />);
    await user.upload(screen.getByLabelText("Choose file"), pngFile());
    expect(await screen.findByRole("alert")).toHaveTextContent("Is the backend running?");
  });
});
