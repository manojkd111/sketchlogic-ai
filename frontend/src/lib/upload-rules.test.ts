import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_BYTES, formatBytes, precheckFile } from "./upload-rules";

describe("precheckFile", () => {
  it.each(["a.png", "B.JPG", "c.jpeg", "d.webp", "flow.xlsx"])("accepts %s", (name) => {
    expect(precheckFile({ name, size: 100 })).toEqual({ ok: true });
  });

  it.each(["a.gif", "b.xls", "c.pdf", "noext"])("rejects %s", (name) => {
    expect(precheckFile({ name, size: 100 }).ok).toBe(false);
  });

  it("rejects empty and oversized files", () => {
    expect(precheckFile({ name: "a.png", size: 0 }).ok).toBe(false);
    expect(precheckFile({ name: "a.png", size: MAX_UPLOAD_BYTES + 1 }).ok).toBe(false);
  });
});

describe("formatBytes", () => {
  it("formats units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
  });
});
