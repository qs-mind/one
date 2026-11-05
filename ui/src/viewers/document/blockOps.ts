// Pure logic of the Document viewer, kept apart from Plate so it is tested without layout: the editor's value
// as drawn (each block's id on its element, pending changes as transient suggestion marks), the edits turned
// into the core's block operations, and offsets inside a block's text.
// A block's text is its text leaves joined; a number reference (`num`, `cell`) counts as no characters.
import type { Block, Change, Op, Segment } from "../../deliverables/types";

export type SlateText = { text: string; [mark: string]: unknown };
export type SlateElement = { type: string; id?: string; children: SlateNode[]; [key: string]: unknown };
export type SlateNode = SlateElement | SlateText;

/** A Suggested change drawn in the editor. `block` is the block it changes, or `new:<change id>` for a new block
 * placed after `after` (null: first). */
export type PendingBlock = {
  block: string;
  after?: string | null;
  segments: Segment[];
  changeId: string;
  author: string;
  label?: string;
};

const INLINES: Record<string, readonly string[]> = { num: ["number"], cell: ["deliverable", "row", "column"] };
const MARKS = ["bold", "italic"] as const;

const isText = (node: SlateNode): node is SlateText => typeof (node as SlateText).text === "string" && !("type" in node);

/** The key of a reference in a Document view's `refs` (the core's store.ref_key). */
export function refKey(node: SlateElement): string | null {
  if (node.type === "num") return `num:${String(node.number)}`;
  if (node.type === "cell") return `cell:${String(node.deliverable)}:${String(node.row)}:${String(node.column)}`;
  return null;
}

type Span = { path: number[]; start: number; end: number; text: string };

/** Each text leaf of a block outside references, with its path inside the block and its place in the block text. */
export function spans(node: SlateElement): Span[] {
  const out: Span[] = [];
  let at = 0;
  const walk = (el: SlateElement, path: number[]) => {
    el.children.forEach((child, i) => {
      if (isText(child)) {
        out.push({ path: [...path, i], start: at, end: at + child.text.length, text: child.text });
        at += child.text.length;
      } else if (!(child.type in INLINES)) walk(child, [...path, i]);
    });
  };
  walk(node, []);
  return out;
}

export const blockText = (node: SlateElement) => spans(node).map((s) => s.text).join("");

/** The part of [start, end) that falls in each leaf, as leaf offsets. */
export function pieces(node: SlateElement, start: number, end: number): { path: number[]; start: number; end: number }[] {
  return spans(node)
    .filter((s) => s.start < end && s.end > start)
    .map((s) => ({ path: s.path, start: Math.max(start, s.start) - s.start, end: Math.min(end, s.end) - s.start }));
}

/** A leaf point (path inside the block, offset in the leaf) as an offset in the block text; null inside a reference. */
export function offsetAt(node: SlateElement, path: number[], offset: number): number | null {
  const span = spans(node).find((s) => s.path.length === path.length && s.path.every((n, i) => n === path[i]));
  return span ? span.start + offset : null;
}

// ---- What is sent to the core ------------------------------------------------------------------------------

/** Only the template's keys: type, children and the block id on top; inline keys on references; text and true
 * marks on leaves. Transient marks (suggestions, comments) and nested ids never leave the screen. */
function clean(node: SlateNode, top: boolean): SlateNode {
  if (isText(node)) {
    const leaf: SlateText = { text: node.text };
    for (const mark of MARKS) if (node[mark] === true) leaf[mark] = true;
    return leaf;
  }
  const keys = INLINES[node.type];
  const el: SlateElement = { type: node.type, children: node.children.map((c) => clean(c, false)) };
  if (keys) for (const k of keys) el[k] = node[k];
  if (top && typeof node.id === "string") el.id = node.id;
  return el;
}

/** For comparing only: no id, no empty text leaves, neighbouring leaves with the same marks joined. */
function canon(node: SlateNode): unknown {
  if (isText(node)) return node;
  const children: SlateNode[] = [];
  for (const child of node.children.map((c) => (isText(c) ? c : (canon(c) as SlateElement)))) {
    const last = children[children.length - 1];
    if (isText(child) && child.text === "") continue;
    if (last && isText(last) && isText(child) && MARKS.every((m) => last[m] === child[m])) {
      children[children.length - 1] = { ...last, text: last.text + child.text };
    } else children.push(child);
  }
  const { id: _, ...rest } = node;
  return { ...rest, children };
}

const sorted = (value: unknown): unknown =>
  Array.isArray(value)
    ? value.map(sorted)
    : value && typeof value === "object"
      ? Object.fromEntries(Object.entries(value).sort(([a], [b]) => (a < b ? -1 : 1)).map(([k, v]) => [k, sorted(v)]))
      : value;
const same = (a: SlateNode, b: SlateNode) =>
  JSON.stringify(sorted(canon(clean(a, false)))) === JSON.stringify(sorted(canon(clean(b, false))));

/** Indexes (into `xs`) of a longest increasing run of `xs`; the blocks outside it are the ones that moved. */
function longestIncreasing(xs: number[]): Set<number> {
  const tails: number[] = [];
  const prev: number[] = [];
  xs.forEach((x, i) => {
    let lo = 0;
    let hi = tails.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1;
      if (xs[tails[mid]!]! < x) lo = mid + 1;
      else hi = mid;
    }
    prev[i] = lo > 0 ? tails[lo - 1]! : -1;
    tails[lo] = i;
  });
  const keep = new Set<number>();
  for (let i = tails.length ? tails[tails.length - 1]! : -1; i >= 0; i = prev[i]!) keep.add(i);
  return keep;
}

/** One op per changed, added, removed or moved block, each with the block's version as `expect`. A block id seen
 * twice (a split paragraph copies it) stays with the first; the second is new. New blocks in a row all name the
 * block before them and are sent last first, so accepting them in order puts them back in order. */
export function opsFor(before: Block[], after: SlateElement[]): Op[] {
  const old = new Map(before.map((b, i) => [b.id, { ...b, index: i }]));
  const seen = new Set<string>();
  const ids = after.map((el) => {
    const id = typeof el.id === "string" && old.has(el.id) && !seen.has(el.id) ? el.id : null;
    if (id) seen.add(id);
    return id;
  });
  const kept = ids.flatMap((id, i) => (id ? [i] : []));
  const stay = longestIncreasing(kept.map((i) => old.get(ids[i]!)!.index));
  const moved = new Set(kept.filter((_, k) => !stay.has(k)));

  const ops: Op[] = [];
  let previous: string | null = null; // the nearest existing block before this one
  let run: Op[] = [];
  const flush = () => {
    ops.push(...run.reverse());
    run = [];
  };
  after.forEach((el, i) => {
    const id = ids[i];
    if (!id) {
      const { id: _, ...node } = clean(el, true) as SlateElement;
      run.push({ op: "insert_block", after: previous, node });
      return;
    }
    flush();
    const was = old.get(id)!;
    if (moved.has(i)) ops.push({ op: "move_block", block: id, after: previous, expect: was.version });
    if (!same(was.node as SlateElement, el)) ops.push({ op: "set_block", block: id, node: clean(el, true) as SlateElement, expect: was.version });
    previous = id;
  });
  flush();
  for (const b of before) if (!seen.has(b.id)) ops.push({ op: "remove_block", block: b.id, expect: b.version });
  return ops;
}

// ---- What the editor draws ---------------------------------------------------------------------------------

const TEXT_BLOCKS = new Set(["p", "h1", "h2", "h3", "blockquote"]);

function transient(type: string, id: string, p: PendingBlock): SlateElement {
  const children: SlateText[] = p.segments
    .filter((s) => s.text !== "")
    .map((s) =>
      s.op === "same"
        ? { text: s.text }
        : {
            text: s.text,
            suggestion: true,
            [`suggestion_${p.changeId}`]: { id: p.changeId, type: s.op === "del" ? "remove" : "insert", userId: p.author, createdAt: 0 },
          },
    );
  // A list or table drawn as its text only, in one line, until the engineer decides.
  return { type: TEXT_BLOCKS.has(type) ? type : "p", id, children: children.length ? children : [{ text: "" }] };
}

/** The editor's value: the view's blocks with their ids, a block with a pending change drawn from the core's
 * segments as Plate suggestion marks, and suggested new blocks in place. Never saved as it is. */
export function displayValue(blocks: Block[], pending: PendingBlock[]): SlateElement[] {
  const byBlock = new Map<string, PendingBlock>();
  const added = new Map<string | null, PendingBlock[]>();
  for (const p of pending) {
    if (p.after !== undefined) added.set(p.after, [...(added.get(p.after) ?? []), p]);
    else if (!byBlock.has(p.block)) byBlock.set(p.block, p); // one pending change drawn per block; the rest wait their turn
  }
  const insertsAfter = (id: string | null) => {
    const list = added.get(id) ?? [];
    added.delete(id);
    return list.map((p) => transient("p", p.block, p));
  };
  const out: SlateElement[] = [...insertsAfter(null)];
  for (const b of blocks) {
    const node = b.node as SlateElement;
    const p = byBlock.get(b.id);
    out.push(p ? transient(node.type, b.id, p) : { ...node, id: b.id });
    out.push(...insertsAfter(b.id));
  }
  for (const id of [...added.keys()]) out.push(...insertsAfter(id)); // after a block no longer shown: at the end
  return out;
}

/** The pending block changes as the editor draws them. A set_block is drawn from the core's word segments; with
 * none, the old text struck and the new text beside it (the screen never diffs). */
export function pendingBlocks(changes: Change[], blocks: Block[], moveLabel: string): PendingBlock[] {
  const nodes = new Map(blocks.map((b) => [b.id, b.node as SlateElement]));
  return changes
    .filter((c) => c.status === "pending")
    .flatMap((c): PendingBlock[] => {
      const base = { changeId: c.id, author: c.author };
      const op = c.op;
      const was = "block" in op ? nodes.get(op.block) : undefined;
      switch (op.op) {
        case "set_block":
          if (!was) return [];
          return [
            {
              ...base,
              block: op.block,
              segments: c.segments ?? [
                { op: "del", text: blockText(was) },
                { op: "ins", text: blockText(op.node as SlateElement) },
              ],
            },
          ];
        case "insert_block":
          return [{ ...base, block: `new:${c.id}`, after: op.after, segments: c.segments ?? [{ op: "ins", text: blockText(op.node as SlateElement) }] }];
        case "remove_block":
          return was ? [{ ...base, block: op.block, segments: [{ op: "del", text: blockText(was) }] }] : [];
        case "move_block":
          return was ? [{ ...base, block: op.block, segments: [{ op: "same", text: blockText(was) }], label: moveLabel }] : [];
        default:
          return [];
      }
    });
}
