import type { Metadata } from "next";
import { Suspense } from "react";
import { GraphEditor } from "@/components/GraphEditor";

export const metadata: Metadata = { title: "Diagram editor · SketchLogic AI" };

// Not async: `params` is awaited inside the Suspense boundary so the shell stays static.
export default function GraphPage({ params }: PageProps<"/graphs/[id]">) {
  return (
    <div className="flex h-dvh flex-col">
      <Suspense fallback={<p className="p-6 text-sm text-zinc-500">Loading editor…</p>}>
        {params.then(({ id }) => (
          <GraphEditor graphId={id} />
        ))}
      </Suspense>
    </div>
  );
}
