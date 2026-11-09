"use client";

import "@excalidraw/excalidraw/index.css";

import { Excalidraw, exportToBlob } from "@excalidraw/excalidraw";
import type { ExcalidrawImperativeAPI } from "@excalidraw/excalidraw/types";
import { exportDimensions } from "@/lib/sketch-export";

/** What the panel needs from the canvas; keeps Excalidraw out of everything else. */
export interface SketchHandle {
  isEmpty(): boolean;
  exportPng(): Promise<Blob>;
}

function handleFor(api: ExcalidrawImperativeAPI): SketchHandle {
  return {
    isEmpty: () => api.getSceneElements().length === 0,
    exportPng: () =>
      exportToBlob({
        elements: api.getSceneElements(),
        appState: { ...api.getAppState(), exportBackground: true, viewBackgroundColor: "#ffffff" },
        files: api.getFiles(),
        mimeType: "image/png",
        exportPadding: 32,
        getDimensions: exportDimensions,
      }),
  };
}

/** Client-only (Excalidraw touches `window`); load via `next/dynamic` with `ssr: false`. */
export default function SketchCanvas({ onReady }: { onReady(handle: SketchHandle): void }) {
  return (
    <Excalidraw
      excalidrawAPI={(api) => onReady(handleFor(api))}
      initialData={{ appState: { viewBackgroundColor: "#ffffff" } }}
      UIOptions={{
        // The sketch only leaves the browser through "Use this sketch" (upload + consent).
        canvasActions: { loadScene: false, saveToActiveFile: false, export: false },
      }}
    />
  );
}
