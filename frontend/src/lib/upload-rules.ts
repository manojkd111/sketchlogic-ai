/**
 * Client-side pre-checks for fast feedback. The backend is authoritative: it sniffs
 * magic bytes and fully decodes the file, so these checks are a UX convenience only.
 */

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

export const ACCEPTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".webp", ".xlsx"] as const;

export const ACCEPT_ATTRIBUTE = [
  ...ACCEPTED_EXTENSIONS,
  "image/png",
  "image/jpeg",
  "image/webp",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
].join(",");

export type PrecheckResult = { ok: true } | { ok: false; message: string };

export function precheckFile(file: Pick<File, "name" | "size">): PrecheckResult {
  if (file.size === 0) return { ok: false, message: "The file is empty." };
  if (file.size > MAX_UPLOAD_BYTES) {
    return {
      ok: false,
      message: `File is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`,
    };
  }
  const lower = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return {
      ok: false,
      message: "Unsupported file type. Use PNG, JPEG, WebP or .xlsx.",
    };
  }
  return { ok: true };
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
