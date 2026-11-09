"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  ApiError,
  createUpload,
  extractUpload,
  validateUpload,
  type UploadResponse,
  type ValidationResult,
} from "@/lib/api";
import { ACCEPT_ATTRIBUTE, formatBytes, precheckFile } from "@/lib/upload-rules";

type Phase =
  | { name: "idle" }
  | { name: "validating"; file: File }
  | { name: "valid"; file: File; result: ValidationResult }
  | { name: "uploading"; file: File; result: ValidationResult }
  | { name: "uploaded"; file: File; upload: UploadResponse }
  | { name: "extracting"; file: File; upload: UploadResponse }
  | { name: "extracted"; file: File; upload: UploadResponse; graphId: string }
  | { name: "error"; file?: File; message: string };

export function UploadPanel() {
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const [consent, setConsent] = useState(false);
  const [dragging, setDragging] = useState(false);
  const preview = usePreviewUrl(phase);

  const handleFile = useCallback(async (file: File) => {
    const pre = precheckFile(file);
    if (!pre.ok) {
      setPhase({ name: "error", file, message: pre.message });
      return;
    }
    setPhase({ name: "validating", file });
    try {
      const result = await validateUpload(file);
      setPhase({ name: "valid", file, result });
    } catch (err) {
      setPhase({ name: "error", file, message: errorMessage(err) });
    }
  }, []);

  const handleUpload = async () => {
    if (phase.name !== "valid") return;
    const { file, result } = phase;
    setPhase({ name: "uploading", file, result });
    try {
      const upload = await createUpload(file, consent);
      setPhase({ name: "uploaded", file, upload });
    } catch (err) {
      setPhase({ name: "error", file, message: errorMessage(err) });
    }
  };

  const handleExtract = async () => {
    if (phase.name !== "uploaded") return;
    const { file, upload } = phase;
    setPhase({ name: "extracting", file, upload });
    try {
      const graph = await extractUpload(upload.id);
      setPhase({ name: "extracted", file, upload, graphId: graph.id });
    } catch (err) {
      setPhase({ name: "error", file, message: errorMessage(err) });
    }
  };

  const reset = () => {
    setPhase({ name: "idle" });
    if (inputRef.current) inputRef.current.value = "";
  };

  const busy = phase.name === "validating" || phase.name === "uploading";
  const details =
    phase.name === "valid" || phase.name === "uploading"
      ? phase.result
      : phase.name === "uploaded" || phase.name === "extracting" || phase.name === "extracted"
        ? phase.upload
        : null;

  return (
    <section
      aria-labelledby={`${inputId}-title`}
      className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-900"
    >
      <h2 id={`${inputId}-title`} className="text-lg font-semibold">
        Upload a diagram source
      </h2>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        Whiteboard photo, hand-drawn flow or spreadsheet screenshot (PNG, JPEG, WebP), or an .xlsx
        workbook. Max {formatBytes(10 * 1024 * 1024)}.
      </p>

      <label
        htmlFor={inputId}
        data-testid="dropzone"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) void handleFile(file);
        }}
        className={`mt-4 flex min-h-40 cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-colors ${
          dragging
            ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40"
            : "border-zinc-300 hover:border-zinc-400 dark:border-zinc-700"
        }`}
      >
        <span className="text-sm font-medium">Drop a file here or click to browse</span>
        <span className="mt-1 text-xs text-zinc-500">.png · .jpg · .webp · .xlsx</span>
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept={ACCEPT_ATTRIBUTE}
          className="sr-only"
          aria-label="Choose file"
          disabled={busy}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void handleFile(file);
          }}
        />
      </label>

      <div aria-live="polite" className="mt-4 space-y-3 text-sm">
        {phase.name === "validating" && <p>Validating {phase.file.name}…</p>}
        {phase.name === "uploading" && <p>Uploading {phase.file.name}…</p>}

        {phase.name === "error" && (
          <p
            role="alert"
            className="rounded-lg bg-red-50 px-3 py-2 text-red-700 dark:bg-red-950/50 dark:text-red-300"
          >
            {phase.file ? `${phase.file.name}: ` : ""}
            {phase.message}
          </p>
        )}

        {details && (
          <div className="flex gap-4 rounded-lg bg-zinc-50 p-3 dark:bg-zinc-800/60">
            {preview && (
              // eslint-disable-next-line @next/next/no-img-element -- local blob preview
              <img
                src={preview}
                alt="Preview of the selected file"
                className="h-24 w-32 rounded object-contain"
              />
            )}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              <dt className="text-zinc-500">File</dt>
              <dd className="truncate">{details.filename}</dd>
              <dt className="text-zinc-500">Type</dt>
              <dd>{details.kind.toUpperCase()}</dd>
              <dt className="text-zinc-500">Size</dt>
              <dd>{formatBytes(details.size_bytes)}</dd>
              {details.width && details.height && (
                <>
                  <dt className="text-zinc-500">Dimensions</dt>
                  <dd>
                    {details.width} × {details.height}px
                  </dd>
                </>
              )}
              {details.sheet_names.length > 0 && (
                <>
                  <dt className="text-zinc-500">Sheets</dt>
                  <dd>{details.sheet_names.join(", ")}</dd>
                </>
              )}
            </dl>
          </div>
        )}
        {details?.warnings.map((w) => (
          <p key={w} className="text-amber-700 dark:text-amber-400">
            ⚠ {w}
          </p>
        ))}

        {(phase.name === "valid" || phase.name === "uploading") && (
          <>
            <label className="flex items-start gap-2">
              <input
                type="checkbox"
                checked={consent}
                onChange={(e) => setConsent(e.target.checked)}
                className="mt-0.5"
              />
              <span className="text-zinc-600 dark:text-zinc-400">
                Allow SketchLogic to use this file to improve the model. Off by default; private
                diagrams are never used for training without this opt-in.
              </span>
            </label>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={handleUpload}
                disabled={busy}
                className="rounded-lg bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                Upload
              </button>
              <button
                type="button"
                onClick={reset}
                disabled={busy}
                className="rounded-lg px-4 py-2 font-medium text-zinc-700 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                Cancel
              </button>
            </div>
          </>
        )}

        {(phase.name === "uploaded" ||
          phase.name === "extracting" ||
          phase.name === "extracted") && (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-emerald-50 px-3 py-2 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300">
            <span>
              Uploaded · id <code className="font-mono text-xs">{phase.upload.id}</code>
            </span>
            <span className="flex items-center gap-3">
              {phase.name === "extracted" ? (
                <Link
                  href={`/graphs/${encodeURIComponent(phase.graphId)}`}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500"
                >
                  Open in editor
                </Link>
              ) : (
                <button
                  type="button"
                  onClick={handleExtract}
                  disabled={phase.name === "extracting"}
                  className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
                >
                  {phase.name === "extracting" ? "Extracting…" : "Extract diagram"}
                </button>
              )}
              <button type="button" onClick={reset} className="font-medium underline">
                Upload another
              </button>
            </span>
          </div>
        )}
        {phase.name === "error" && (
          <button type="button" onClick={reset} className="font-medium underline">
            Try another file
          </button>
        )}
      </div>
    </section>
  );
}

function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  return err instanceof Error ? err.message : "Something went wrong.";
}

function usePreviewUrl(phase: Phase): string | null {
  const file = "file" in phase ? phase.file : undefined;
  const isImage = !!file && file.type.startsWith("image/") && phase.name !== "error";
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file || !isImage || typeof URL.createObjectURL !== "function") return;
    const u = URL.createObjectURL(file);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- sync with external blob URL
    setUrl(u);
    return () => {
      URL.revokeObjectURL(u);
      setUrl(null);
    };
  }, [file, isImage]);
  return isImage ? url : null;
}
