import { describe, expect, it } from "vitest";
import { MAX_LONG_SIDE, MIN_SHORT_SIDE, exportDimensions, sketchFileName } from "./sketch-export";

describe("exportDimensions", () => {
  it("scales small drawings up to the minimum short side", () => {
    const d = exportDimensions(100, 40);
    expect(d.height).toBe(MIN_SHORT_SIDE);
    expect(d.width).toBe(1280);
    expect(d.scale).toBeCloseTo(12.8);
  });

  it("leaves mid-sized drawings at scale 1", () => {
    expect(exportDimensions(1200, 800)).toEqual({ width: 1200, height: 800, scale: 1 });
  });

  it("caps very large drawings at the maximum long side", () => {
    const d = exportDimensions(20_000, 10_000);
    expect(d.width).toBe(MAX_LONG_SIDE);
    expect(d.height).toBe(2048);
  });

  it("lets the long-side cap win for long, thin drawings", () => {
    const d = exportDimensions(5000, 10);
    expect(d.width).toBe(MAX_LONG_SIDE);
    expect(d.height).toBeGreaterThanOrEqual(8);
  });
});

it("builds a safe, timestamped file name", () => {
  expect(sketchFileName(new Date("2026-11-08T19:05:03.123Z"))).toBe(
    "sketch-2026-11-08T19-05-03.png",
  );
});
