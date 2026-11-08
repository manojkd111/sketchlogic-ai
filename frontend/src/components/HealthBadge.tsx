"use client";

import { useEffect, useState } from "react";
import { getHealth, type HealthResponse } from "@/lib/api";

type State =
  | { status: "loading" }
  | { status: "ok"; health: HealthResponse }
  | { status: "error"; message: string };

const POLL_MS = 15_000;

export function HealthBadge() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    const check = () =>
      getHealth(controller.signal)
        .then((health) => setState({ status: "ok", health }))
        .catch((err: unknown) => {
          if (controller.signal.aborted) return;
          setState({
            status: "error",
            message: err instanceof Error ? err.message : "API unreachable",
          });
        });
    check();
    const id = setInterval(check, POLL_MS);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, []);

  const { dot, text, title } = describe(state);
  return (
    <span
      role="status"
      title={title}
      className="inline-flex items-center gap-2 rounded-full border border-zinc-200 px-3 py-1 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
    >
      <span aria-hidden className={`h-2 w-2 rounded-full ${dot}`} />
      {text}
    </span>
  );
}

function describe(state: State): { dot: string; text: string; title: string } {
  switch (state.status) {
    case "loading":
      return { dot: "bg-zinc-400", text: "Checking API…", title: "Contacting backend" };
    case "error":
      return { dot: "bg-red-500", text: "API offline", title: state.message };
    case "ok": {
      const h = state.health;
      return {
        dot: h.status === "ok" ? "bg-emerald-500" : "bg-amber-500",
        text: `API ${h.status} · schema v${h.graph_schema_version}`,
        title: `v${h.version} · provider: ${h.inference_provider} · AWS ${h.aws_enabled ? "enabled" : "disabled"}`,
      };
    }
  }
}
