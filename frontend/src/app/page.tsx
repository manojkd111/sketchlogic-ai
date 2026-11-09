import Link from "next/link";
import { HealthBadge } from "@/components/HealthBadge";
import { UploadPanel } from "@/components/UploadPanel";

const ROADMAP = [
  {
    title: "AI extraction",
    body: "A local vision model replaces today's mock extractor; spreadsheets parsed directly.",
    phase: "Phase 3",
  },
  {
    title: "Natural-language edits",
    body: "Describe a change; review it as a proposal before anything locked is touched.",
    phase: "Phase 3",
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
        <p className="-mt-4 text-center text-sm text-zinc-600 dark:text-zinc-400">
          No photo handy?{" "}
          <Link
            href="/sketch"
            className="font-medium text-indigo-600 underline dark:text-indigo-400"
          >
            Draw a sketch instead
          </Link>
        </p>

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
