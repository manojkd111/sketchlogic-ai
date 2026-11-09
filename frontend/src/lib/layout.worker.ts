/** Runs ELK off the main thread. Messages: { id, graph } -> { id, result } | { id, error }. */

import ELK from "elkjs/lib/elk.bundled.js";
import type { ElkNode } from "elkjs/lib/elk-api";

// Minimal worker-scope typing (the project compiles against the DOM lib, not "webworker").
interface WorkerScope {
  onmessage: ((event: MessageEvent<{ id: number; graph: ElkNode }>) => void) | null;
  postMessage(message: unknown): void;
}

const elk = new ELK();
const ctx = self as unknown as WorkerScope;

ctx.onmessage = async (event) => {
  const { id, graph } = event.data;
  try {
    ctx.postMessage({ id, result: await elk.layout(graph) });
  } catch (err) {
    ctx.postMessage({ id, error: err instanceof Error ? err.message : String(err) });
  }
};
