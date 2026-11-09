"use client";

import { createContext, useContext } from "react";

export interface EditorActions {
  acceptEdge(edgeId: string): void;
  rejectEdge(edgeId: string): void;
  /** Display label of a schema node id (for accessible names). */
  labelOf(nodeId: string): string;
}

const noop: EditorActions = { acceptEdge() {}, rejectEdge() {}, labelOf: (id) => id };

export const EditorActionsContext = createContext<EditorActions>(noop);
export const useEditorActions = () => useContext(EditorActionsContext);
