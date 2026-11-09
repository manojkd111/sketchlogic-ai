"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useId, useRef, useState } from "react";
import { ApiError, createUpload, extractUpload } from "@/lib/api";
import { sketchFileName } from "@/lib/sketch-export";
import type { SketchHandle } from "./SketchCanvas";

const SketchCanvas = dynamic(() => import("./SketchCanvas"), {
  ssr: false,
  loading: () => <p className="p-6 text-sm text-zinc-500">Loading canvas…</p>,
});

type Phase =
  | { name: "idle" }
  | { name: "working"; step: string }
  | { name: "done"; graphId: string }
  | { name: "error"; message: string };

export function SketchPanel() {
  const consentId = useId();
  const handle = useRef<SketchHandle | null>(null);
  const [ready, setReady] = useState(false);
  const [consent, setConsent] = useState(false);
  const [phase, setPhase] = useState<Phase>({ name: "idle" });
  const busy = phase.name === "working";

  const submitSketch = async () => {
    const canvas = handle.current;
    if (!canvas) return;
    if (canvas.isEmpty()) {
      setPhase({ name: "error", message: "Draw something first." });
      return;
    }
    try {
      setPhase({ name: "working", step: "Exporting sketch…" });
      const blob = await canvas.exportPng();
      const file = new File([blob], sketchFileName(), { type: "image/png" });
      setPhase({ name: "working", step: "Uploading…" });
      const upload = await createUpload(file, consent);
      setPhase({ name: "working", step: "Extracting diagram…" });
      const graph = await extractUpload(upload.id);
      setPhase({ name: "done", graphId: graph.id });
    } catch (err) {
      const message =
        err instanceof ApiError || err instanceof Error ? err.message : "Something went wrong.";
      setPhase({ name: "error", message });
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex flex-wrap items-center gap-3 border-b border-zinc-200 px-4 py-2 text-sm dark:border-zinc-800">
        <Link href="/" className="text-zinc-500 hover:text-zinc-900 dark:hover:text-zinc-100">
          ← SketchLogic
        </Link>
        <h1 className="font-semibold">Sketch a diagram</h1>
        <label
          htmlFor={consentId}
          className="ml-auto flex items-center gap-2 text-xs text-zinc-600 dark:text-zinc-400"
        >
          <input
            id={consentId}
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            disabled={busy}
          />
          Allow use for model training (off by default)
        </label>
        {phase.name === "done" ? (
          <Link
            href={`/graphs/${encodeURIComponent(phase.graphId)}`}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500"
          >
            Open in editor
          </Link>
        ) : (
          <button
            type="button"
            onClick={() => void submitSketch()}
            disabled={!ready || busy}
            className="rounded-lg bg-indigo-600 px-3 py-1.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            Use this sketch
          </button>
        )}
      </header>

      <div className="relative min-h-0 flex-1" aria-label="Sketch canvas">
        <SketchCanvas
          onReady={(h) => {
            handle.current = h;
            setReady(true);
          }}
        />
        {/* Overlaid, not stacked above: moving the canvas would desync Excalidraw's cached
            offsets and misplace strokes. */}
        <div
          aria-live="polite"
          className="pointer-events-none absolute inset-x-0 bottom-16 z-10 flex justify-center text-sm"
        >
          {phase.name === "working" && (
            <p className="rounded-lg bg-white/95 px-4 py-2 text-zinc-700 shadow dark:bg-zinc-900/95 dark:text-zinc-300">
              {phase.step}
            </p>
          )}
          {phase.name === "done" && (
            <p className="rounded-lg bg-emerald-50 px-4 py-2 text-emerald-800 shadow dark:bg-emerald-950 dark:text-emerald-300">
              Diagram extracted. Open it in the editor to review.
            </p>
          )}
          {phase.name === "error" && (
            <p
              role="alert"
              className="rounded-lg bg-red-50 px-4 py-2 text-red-700 shadow dark:bg-red-950 dark:text-red-300"
            >
              {phase.message}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
