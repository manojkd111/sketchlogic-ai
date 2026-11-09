import type { Metadata } from "next";
import { SketchPanel } from "@/components/sketch/SketchPanel";

export const metadata: Metadata = { title: "Sketch · SketchLogic AI" };

export default function SketchPage() {
  return (
    <div className="flex h-dvh flex-col">
      <SketchPanel />
    </div>
  );
}
