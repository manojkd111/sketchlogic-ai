import { HealthBadge } from "@/components/HealthBadge";
import { UploadPanel } from "@/components/UploadPanel";

const ROADMAP = [
  { title: "Sketch canvas", body: "Draw a flow freehand with Excalidraw.", phase: "Phase 2" },
  {
    title: "AI extraction",
    body: "Components, groups and connections, with inferred links flagged for review.",
    phase: "Phase 3",
  },
  {
    title: "Diagram editor",
    body: "Editable React Flow graph with ELK.js auto layout.",
    phase: "Phase 2",
  },
  {
    title: "Present & export",
    body: "Step-by-step playback; PNG, SVG, Mermaid and JSON export.",
    phase: "Phase 4",
  },
];

export default function Home() {
  return (
    <div className="mx-auto flex w-full max-w-4xl flex-1 flex-col gap-8 px-4 py-10 sm:px-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">SketchLogic AI</h1>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Turn messy sketches, whiteboards and spreadsheets into clean, editable diagrams.
          </p>
        </div>
        <HealthBadge />
      </header>

      <main className="flex flex-col gap-8">
        <UploadPanel />

        <section aria-labelledby="roadmap-title">
          <h2 id="roadmap-title" className="mb-3 text-sm font-semibold text-zinc-500">
            Coming next
          </h2>
          <ul className="grid gap-3 sm:grid-cols-2">
            {ROADMAP.map((item) => (
              <li
                key={item.title}
                className="rounded-xl border border-zinc-200 p-4 dark:border-zinc-800"
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium">{item.title}</span>
                  <span className="text-xs text-zinc-500">{item.phase}</span>
                </div>
                <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{item.body}</p>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
