// A source card for a box of numbers that is not a viewer (a chat reply, a card's table, a View block): the box
// spreads `host` on an element that does not clip (the card sits in it, under the number), calls `open` from a
// number's click, and renders `card`.
import { useRef, useState, type CSSProperties } from "react";
import type { NumberCell, Source } from "../deliverables/types";
import { readingDirection } from "./mark";
import { SourceCard } from "./SourceCard";

type Opened = { cell: NumberCell; sources: Record<string, Source>; from: HTMLElement; label?: string; style: CSSProperties; focus: boolean };

export function useSourceCard(projectId: string) {
  const host = useRef<HTMLDivElement>(null);
  const [opened, setOpened] = useState<Opened | null>(null);

  /** Opens `cell` from the number `from`; `focus` when opened from the keyboard (focus moves into the card). */
  function open(from: HTMLElement, cell: NumberCell, sources: Record<string, Source>, { label, focus = false }: { label?: string; focus?: boolean } = {}) {
    const box = host.current?.getBoundingClientRect();
    const at = from.getBoundingClientRect();
    if (!box) return;
    // under the number, lined up with its start edge (the right edge in Arabic)
    const side = readingDirection(from) === "rtl" ? { right: Math.max(box.right - at.right, 0) } : { left: Math.max(at.left - box.left, 0) };
    setOpened({ cell, sources, from, label, focus, style: { top: at.bottom - box.top, ...side } });
  }

  const card = opened && (
    <SourceCard
      projectId={projectId}
      cell={opened.cell}
      sources={opened.sources}
      style={opened.style}
      focus={opened.focus}
      from={opened.from}
      label={opened.label}
      onClose={() => setOpened(null)}
    />
  );
  return { host, open, card };
}
