/** Browser-side `ElkLike` that runs ELK in a dedicated web worker (created lazily, reused). */

import type { ElkNode } from "elkjs/lib/elk-api";
import type { ElkLike } from "./elk-layout";

type Reply = { id: number; result?: ElkNode; error?: string };

export function createWorkerElk(): ElkLike & { terminate(): void } {
  let worker: Worker | null = null;
  let seq = 0;
  const pending = new Map<number, { resolve(g: ElkNode): void; reject(e: Error): void }>();

  const fail = (message: string) => {
    for (const p of pending.values()) p.reject(new Error(message));
    pending.clear();
    worker?.terminate();
    worker = null;
  };

  const ensure = () => {
    if (worker) return worker;
    worker = new Worker(new URL("./layout.worker.ts", import.meta.url), { type: "module" });
    worker.onmessage = (event: MessageEvent<Reply>) => {
      const { id, result, error } = event.data;
      const p = pending.get(id);
      if (!p) return;
      pending.delete(id);
      if (result) p.resolve(result);
      else p.reject(new Error(error ?? "Layout failed."));
    };
    worker.onerror = () => fail("The layout worker crashed.");
    return worker;
  };

  return {
    layout(graph) {
      const id = ++seq;
      return new Promise<ElkNode>((resolve, reject) => {
        pending.set(id, { resolve, reject });
        ensure().postMessage({ id, graph });
      });
    },
    terminate: () => fail("Layout cancelled."),
  };
}
