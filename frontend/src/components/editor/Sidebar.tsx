"use client";

import { useId } from "react";
import { MAX_LABEL, pendingInferredEdges } from "@/lib/graph-edits";
import type { GraphDocument, Provenance } from "@/lib/graph-schema";
import { useEditorActions } from "./EditorActions";

export type Selection = { kind: "node" | "edge" | "group"; id: string } | null;

interface SidebarProps {
  doc: GraphDocument;
  selection: Selection;
  onRename(selection: NonNullable<Selection>, label: string): void;
}

const pct = (c: number) => `${Math.round(c * 100)}%`;
const ORIGIN_LABEL: Record<Provenance["origin"], string> = {
  ai_extracted: "AI extracted",
  ai_modified: "AI modified",
  user_created: "Created by you",
  user_corrected: "Corrected by you",
  imported: "Imported",
};

export function Sidebar({ doc, selection, onRename }: SidebarProps) {
  return (
    <aside className="flex w-72 shrink-0 flex-col gap-6 overflow-y-auto border-l border-zinc-200 p-4 text-sm dark:border-zinc-800">
      <ReviewList doc={doc} />
      <Inspector doc={doc} selection={selection} onRename={onRename} />
    </aside>
  );
}

function ReviewList({ doc }: { doc: GraphDocument }) {
  const actions = useEditorActions();
  const pending = pendingInferredEdges(doc);
  return (
    <section aria-labelledby="review-title">
      <h2 id="review-title" className="mb-2 font-semibold">
        Review inferred connections{" "}
        <span className="font-normal text-zinc-500">({pending.length})</span>
      </h2>
      {pending.length === 0 ? (
        <p className="text-zinc-500">Nothing to review.</p>
      ) : (
        <ul className="space-y-2">
          {pending.map((e) => {
            const name = `${actions.labelOf(e.source)} to ${actions.labelOf(e.target)}`;
            return (
              <li
                key={e.id}
                className="rounded-lg border border-amber-300 bg-amber-50 p-2 dark:border-amber-800 dark:bg-amber-950/40"
              >
                <p className="font-medium">
                  {actions.labelOf(e.source)} → {actions.labelOf(e.target)}{" "}
                  <span className="font-normal text-zinc-500">{pct(e.confidence)}</span>
                </p>
                {e.rationale && (
                  <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{e.rationale}</p>
                )}
                <div className="mt-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => actions.acceptEdge(e.id)}
                    aria-label={`Accept inferred connection ${name}`}
                    className="rounded bg-emerald-600 px-2 py-1 text-xs font-medium text-white hover:bg-emerald-500"
                  >
                    Accept
                  </button>
                  <button
                    type="button"
                    onClick={() => actions.rejectEdge(e.id)}
                    aria-label={`Reject inferred connection ${name}`}
                    className="rounded px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-950"
                  >
                    Reject
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function Inspector({ doc, selection, onRename }: SidebarProps) {
  const inputId = useId();
  const el =
    selection?.kind === "node"
      ? doc.nodes.find((n) => n.id === selection.id)
      : selection?.kind === "edge"
        ? doc.edges.find((e) => e.id === selection.id)
        : selection?.kind === "group"
          ? doc.groups.find((g) => g.id === selection.id)
          : undefined;

  if (!selection || !el) {
    return (
      <section>
        <h2 className="mb-2 font-semibold">Selection</h2>
        <p className="text-zinc-500">
          Select a node, group or connection to edit it. Drag between handles to connect nodes.
        </p>
      </section>
    );
  }

  const label = el.label ?? "";
  const commit = (value: string) => {
    if (value.trim() !== label) onRename(selection, value);
  };

  return (
    <section aria-labelledby={`${inputId}-title`}>
      <h2 id={`${inputId}-title`} className="mb-2 font-semibold capitalize">
        {selection.kind === "edge" ? "Connection" : selection.kind}
      </h2>
      <label htmlFor={inputId} className="mb-1 block text-xs text-zinc-500">
        Label
      </label>
      <input
        key={`${selection.kind}:${el.id}:${label}`}
        id={inputId}
        defaultValue={label}
        maxLength={MAX_LABEL}
        onBlur={(e) => commit(e.currentTarget.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit(e.currentTarget.value);
        }}
        className="w-full rounded-md border border-zinc-300 bg-white px-2 py-1 dark:border-zinc-700 dark:bg-zinc-900"
      />
      <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {"kind" in el && (
          <>
            <dt className="text-zinc-500">Kind</dt>
            <dd>{el.kind.replace("_", " ")}</dd>
          </>
        )}
        {"evidence" in el && (
          <>
            <dt className="text-zinc-500">Evidence</dt>
            <dd>{el.evidence}</dd>
          </>
        )}
        <dt className="text-zinc-500">Confidence</dt>
        <dd>{pct(el.confidence)}</dd>
        <dt className="text-zinc-500">Origin</dt>
        <dd>{ORIGIN_LABEL[el.provenance.origin]}</dd>
      </dl>
      {el.provenance.locked && (
        <p className="mt-3 rounded-md bg-zinc-100 px-2 py-1 text-xs dark:bg-zinc-800">
          🔒 Locked. Automated changes to this element will need your approval.
        </p>
      )}
    </section>
  );
}
