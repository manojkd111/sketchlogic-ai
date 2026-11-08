import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import Home from "./page";

describe("Home page (smoke)", () => {
  it("renders the upload panel and shows API health", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          status: "ok",
          version: "0.1.0",
          environment: "test",
          graph_schema_version: "1.0",
          supported_schema_versions: ["1.0"],
          database: "ok",
          inference_provider: "mock",
          aws_enabled: false,
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<Home />);
    expect(screen.getByRole("heading", { name: "SketchLogic AI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Upload a diagram source" })).toBeInTheDocument();
    expect(await screen.findByText("API ok · schema v1.0")).toBeInTheDocument();
  });
});
