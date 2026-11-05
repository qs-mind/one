// The Document editor on Plate: the only file that imports Plate. It draws the core's blocks, number
// references and the transient marks (pending changes as Plate suggestion marks, comments and untraced numbers as
// decorations), and hands the edited blocks back on blur or Ctrl+Enter. It never saves anything itself, and the
// value it hands back never holds a suggestion or comment mark.
import { BlockquotePlugin, BoldPlugin, H1Plugin, H2Plugin, H3Plugin, ItalicPlugin } from "@platejs/basic-nodes/react";
import { SuggestionPlugin } from "@platejs/suggestion/react";
import { ParagraphPlugin } from "platejs/react";
import {
  createPlatePlugin,
  Plate,
  PlateContent,
  PlateElement,
  PlateLeaf,
  usePlateEditor,
  type PlateEditor,
  type PlateElementProps,
  type PlateLeafProps,
} from "platejs/react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, type ReactNode } from "react";
import type { Block, RefValue } from "../../deliverables/types";
import { dir, t, type Language } from "../../i18n";
import { blockText, displayValue, offsetAt, pieces, refKey, spans, type PendingBlock, type SlateElement } from "./blockOps";
import { NumberRef } from "./NumberRef";

/** A comment drawn on a block: over [start, end) of its text, or, with no text (or moved), as a mark on the block. */
export type DocComment = { id: string; block: string; start: number; end: number; kind: "note" | "review"; moved?: boolean };
/** Selected text, as the core's comment anchor. */
export type TextAnchor = { type: "text"; block: string; start: number; end: number; quote: string };

export type DocEditorProps = {
  label: string;
  blocks: Block[];
  refs: Record<string, RefValue>;
  language: Language;
  readOnly: boolean;
  pending: PendingBlock[];
  comments: DocComment[];
  untraced: { block: string; text: string }[];
  /** The blocks as edited (pending ones as they were). Resolves false when nothing was sent: the edit is kept. */
  onCommit: (after: SlateElement[]) => Promise<boolean>;
  onDecide: (changeId: string, accept: boolean) => void;
  onOpenRef: (value: RefValue, el: HTMLElement, byKey: boolean) => void;
  onSelectText?: (anchor: TextAnchor | null) => void;
};

type Shared = {
  language: Language;
  refs: Record<string, RefValue>;
  pending: Map<string, PendingBlock>;
  marks: Map<string, DocComment[]>;
  onDecide: DocEditorProps["onDecide"];
  onOpenRef: DocEditorProps["onOpenRef"];
};
const Doc = createContext<Shared | null>(null);
const useDoc = () => useContext(Doc)!;

// ---- Blocks ------------------------------------------------------------------------------------------------

const STYLE: Record<string, string> = {
  p: "my-3",
  h1: "mb-4 mt-2 text-2xl font-semibold",
  h2: "mb-3 mt-6 text-lg font-semibold",
  h3: "mb-2 mt-5 font-semibold",
  blockquote: "my-3 border-s-2 border-slate ps-4",
  ul: "my-3 list-disc ps-6",
  ol: "my-3 list-decimal ps-6",
  li: "my-1",
  table: "my-4 border-collapse tabular-nums",
  tr: "border-b border-stone",
  td: "px-3 py-2 align-top",
};

/** What sits at a block's end, outside the text: ✓ ✗ for its pending change, and marks for comments on the block. */
function BlockEnd({ id }: { id: string }) {
  const { pending, marks, onDecide } = useDoc();
  const change = pending.get(id);
  const notes = marks.get(id) ?? [];
  if (!change && notes.length === 0) return null;
  return (
    <span contentEditable={false} className="ms-2 inline-flex select-none items-center gap-1 align-middle text-sm">
      {notes.map((c) => {
        const what = t(c.kind === "review" ? "reviewComment" : "reviewNote");
        const line = c.moved ? `${what}: ${t("docMoved")}` : what;
        return (
          <span
            key={c.id}
            role="note"
            aria-label={line}
            title={line}
            data-comment-mark={c.kind}
            className={`size-2 rounded-full ${c.kind === "review" ? "bg-copper" : "border border-slate"}`}
          />
        );
      })}
      {change?.label && <span className="text-slate">{change.label}</span>}
      {change && (
        <>
          <button
            type="button"
            aria-label={t("sheetAccept")}
            title={t("sheetAccept")}
            className="rounded border border-slate px-1.5 leading-5 hover:bg-stone"
            onClick={() => onDecide(change.changeId, true)}
          >
            ✓
          </button>
          <button
            type="button"
            aria-label={t("sheetReject")}
            title={t("sheetReject")}
            className="rounded border border-slate px-1.5 leading-5 hover:bg-stone"
            onClick={() => onDecide(change.changeId, false)}
          >
            ✗
          </button>
        </>
      )}
    </span>
  );
}

function element(tag: string) {
  return function DocBlock(props: PlateElementProps) {
    const { language } = useDoc();
    const top = props.path.length === 1;
    const id = typeof props.element.id === "string" ? props.element.id : undefined;
    const attributes = { ...props.attributes, dir: "auto", lang: language, ...(top && id ? { "data-block-id": id } : {}) };
    let children: ReactNode = props.children;
    if (tag === "table") children = <tbody>{children}</tbody>;
    return (
      <PlateElement {...props} as={tag as "div"} attributes={attributes as PlateElementProps["attributes"]} className={STYLE[tag]}>
        {children}
        {top && id && <BlockEnd id={id} />}
      </PlateElement>
    );
  };
}

function Reference(props: PlateElementProps) {
  const { refs, onOpenRef } = useDoc();
  const key = refKey(props.element as unknown as SlateElement);
  return (
    <PlateElement {...props} as="span" className="inline">
      <span contentEditable={false}>
        <NumberRef value={key ? refs[key] : undefined} onOpen={onOpenRef} />
      </span>
      {props.children}
    </PlateElement>
  );
}

const plain = (key: string) => createPlatePlugin({ key, node: { isElement: true, component: element(key) } });
const reference = (key: string) =>
  createPlatePlugin({ key, node: { isElement: true, isInline: true, isVoid: true, component: Reference } });

// ---- Leaves: suggestion marks and decorations ----------------------------------------------------------------

function SuggestionLeaf(props: PlateLeafProps) {
  const data = Object.entries(props.leaf).find(([k]) => k.startsWith("suggestion_"))?.[1] as { type?: string } | undefined;
  const removed = data?.type === "remove";
  return (
    <PlateLeaf
      {...props}
      as={removed ? "del" : "ins"}
      className={removed ? "text-slate line-through" : "text-ink underline decoration-ink"}
    />
  );
}

function CommentLeaf(props: PlateLeafProps) {
  const review = props.leaf.docComment === "review";
  const line = t(review ? "reviewComment" : "reviewNote");
  return (
    <PlateLeaf
      {...props}
      attributes={{ ...props.attributes, title: line, "data-comment": review ? "review" : "note" } as PlateLeafProps["attributes"]}
      className={review ? "border-b-2 border-copper bg-stone" : "border-b-2 border-slate"}
    />
  );
}

function UntracedLeaf(props: PlateLeafProps) {
  return (
    <PlateLeaf
      {...props}
      attributes={{ ...props.attributes, title: t("docUntraced"), "data-untraced": "" } as PlateLeafProps["attributes"]}
      className="underline decoration-slate decoration-dotted underline-offset-4"
    />
  );
}

const decoration = (key: string, component: (props: PlateLeafProps) => ReactNode) =>
  createPlatePlugin({ key, node: { isLeaf: true, isDecoration: true, component } });

// ---- Pending blocks are read only until the engineer decides --------------------------------------------------

type Guard = { locked: Set<string>; bypass: boolean };
const guards = new WeakMap<object, Guard>();
type AnyOp = { type: string; path?: number[]; newPath?: number[] };

function lockedAt(editor: PlateEditor, indexes: number[], locked: Set<string>) {
  return indexes.some((i) => {
    const id = (editor.children[i] as SlateElement | undefined)?.id;
    return id !== undefined && locked.has(id);
  });
}

/** Drops any operation on a block that has a pending change (typing, deleting, merging into it, moving it). */
const GuardPlugin = createPlatePlugin({ key: "docGuard" }).overrideEditor(({ editor, tf: { apply } }) => ({
  transforms: {
    apply(operation) {
      const op = operation as unknown as AnyOp;
      const guard = guards.get(editor);
      if (guard && !guard.bypass && op.type !== "set_selection" && op.type !== "insert_node" && op.path) {
        const at = [op.path[0]!];
        if (op.type === "merge_node" && op.path.length === 1) at.push(op.path[0]! - 1);
        if (op.newPath) at.push(op.newPath[0]!);
        if (lockedAt(editor, at, guard.locked)) return;
      }
      apply(operation);
    },
  },
}));

function selectionLocked(editor: PlateEditor) {
  const guard = guards.get(editor);
  const sel = editor.selection;
  if (!guard || !sel) return false;
  const [a, b] = [sel.anchor.path[0]!, sel.focus.path[0]!].sort((x, y) => x - y);
  return lockedAt(editor, Array.from({ length: b! - a! + 1 }, (_, k) => a! + k), guard.locked);
}

// ---- The editor ------------------------------------------------------------------------------------------------

const PLUGINS = [
  ParagraphPlugin.withComponent(element("p")),
  H1Plugin.withComponent(element("h1")),
  H2Plugin.withComponent(element("h2")),
  H3Plugin.withComponent(element("h3")),
  BlockquotePlugin.withComponent(element("blockquote")),
  ...["ul", "ol", "li", "table", "tr", "td"].map(plain),
  reference("num"),
  reference("cell"),
  BoldPlugin,
  ItalicPlugin,
  SuggestionPlugin.withComponent(SuggestionLeaf),
  decoration("docComment", CommentLeaf),
  decoration("docUntraced", UntracedLeaf),
  GuardPlugin,
];

const DIGIT = /[0-9٠-٩۰-۹.,٫٬]/;

export function DocEditor(props: DocEditorProps) {
  const { blocks, pending, comments, untraced, language } = props;
  const displayed = useMemo(() => displayValue(blocks, pending), [blocks, pending]);
  const editor = usePlateEditor({ plugins: PLUGINS, value: displayed, nodeId: false });
  const guard = useMemo<Guard>(() => {
    const g = { locked: new Set<string>(), bypass: false };
    guards.set(editor, g);
    return g;
  }, [editor]);
  guard.locked = useMemo(() => new Set(pending.map((p) => p.block)), [pending]);

  const latest = useRef(displayed);
  latest.current = displayed;
  const shown = useRef<unknown>(editor.children); // the value last put in by us, not typed
  const shownKey = useRef(JSON.stringify(displayed)); // and what it was made from
  const dirty = useRef(false);

  /** Puts the latest view (and its pending changes) back in the editor, out of the undo history. */
  const reset = useCallback(() => {
    const selection = editor.selection;
    guard.bypass = true;
    try {
      editor.tf.withoutSaving(() => editor.tf.setValue(structuredClone(latest.current) as never));
      const history = (editor as unknown as { history?: { undos: unknown[]; redos: unknown[] } }).history;
      if (history) history.undos = history.redos = [];
      const fits = (point: { path: number[]; offset: number }) => {
        const leaf = editor.api.node(point.path)?.[0] as { text?: unknown } | undefined;
        return typeof leaf?.text === "string" && point.offset <= leaf.text.length;
      };
      if (selection && fits(selection.anchor) && fits(selection.focus)) editor.tf.select(selection);
    } catch {
      // the old selection does not fit the new value: leave it unset
    } finally {
      guard.bypass = false;
      shown.current = editor.children;
      shownKey.current = JSON.stringify(latest.current);
    }
  }, [editor, guard]);

  // Only a real change of the view or its pending changes is put in (a refetch that brings the same data, or a
  // new array with the same changes, leaves the editor and its DOM alone), and never over an unsent edit.
  useEffect(() => {
    if (!dirty.current && JSON.stringify(displayed) !== shownKey.current) reset();
  }, [displayed, reset]);

  const original = useMemo(() => new Map(blocks.map((b) => [b.id, b.node as SlateElement])), [blocks]);
  const commit = useCallback(async () => {
    if (!dirty.current) return;
    dirty.current = false;
    // Suggested new blocks are not the engineer's; a block waiting for a decision goes back as it was.
    const after = (editor.children as SlateElement[])
      .filter((el) => !(typeof el.id === "string" && el.id.startsWith("new:")))
      .map((el) => (el.id && guard.locked.has(el.id) && original.has(el.id) ? { ...original.get(el.id)!, id: el.id } : el));
    const sent = await props.onCommit(after);
    if (sent) reset();
    else dirty.current = true;
  }, [editor, guard, original, props.onCommit, reset]);

  const decorate = useCallback(
    ({ entry: [node, path] }: { entry: [unknown, number[]] }) => {
      const el = node as SlateElement;
      if (path.length !== 1 || typeof el.id !== "string" || guard.locked.has(el.id)) return [];
      const ranges: Record<string, unknown>[] = [];
      const at = (leaf: number[], offset: number) => ({ path: [...path, ...leaf], offset });
      for (const c of comments) {
        if (c.block !== el.id || c.moved || c.end <= c.start) continue;
        for (const piece of pieces(el, c.start, c.end))
          ranges.push({ anchor: at(piece.path, piece.start), focus: at(piece.path, piece.end), docComment: c.kind });
      }
      const texts = new Set(untraced.filter((u) => u.block === el.id).map((u) => u.text));
      for (const span of texts.size ? spans(el) : []) {
        for (const text of texts) {
          for (let k = span.text.indexOf(text); k >= 0; k = span.text.indexOf(text, k + text.length)) {
            const before = span.text[k - 1];
            const after = span.text[k + text.length];
            if ((before && DIGIT.test(before)) || (after && DIGIT.test(after))) continue; // part of a longer number
            ranges.push({ anchor: at(span.path, k), focus: at(span.path, k + text.length), docUntraced: true });
          }
        }
      }
      return ranges;
    },
    [comments, untraced, guard],
  );

  const selectText = useRef(props.onSelectText);
  selectText.current = props.onSelectText;
  const reported = useRef("null");
  function report(selection: PlateEditor["selection"]) {
    let anchor: TextAnchor | null = null;
    const [i, j] = [selection?.anchor.path[0], selection?.focus.path[0]];
    const el = i === undefined ? undefined : (editor.children[i] as SlateElement | undefined);
    if (selection && el && i === j && typeof el.id === "string" && !guard.locked.has(el.id)) {
      const a = offsetAt(el, selection.anchor.path.slice(1), selection.anchor.offset);
      const b = offsetAt(el, selection.focus.path.slice(1), selection.focus.offset);
      if (a !== null && b !== null && a !== b) {
        const [start, end] = a < b ? [a, b] : [b, a];
        anchor = { type: "text", block: el.id, start, end, quote: blockText(el).slice(start, end) };
      }
    }
    const key = JSON.stringify(anchor);
    if (key === reported.current) return;
    reported.current = key;
    selectText.current?.(anchor);
  }

  const marks = useMemo(() => {
    const out = new Map<string, DocComment[]>();
    for (const c of comments) if (c.moved || c.end <= c.start) out.set(c.block, [...(out.get(c.block) ?? []), c]);
    return out;
  }, [comments]);
  const shared = useMemo<Shared>(
    () => ({
      language,
      refs: props.refs,
      pending: new Map(pending.map((p) => [p.block, p])),
      marks,
      onDecide: props.onDecide,
      onOpenRef: props.onOpenRef,
    }),
    [language, props.refs, pending, marks, props.onDecide, props.onOpenRef],
  );

  // Returning true tells Plate and Slate the event is handled, so neither edits the locked block.
  const stop = (event: { preventDefault(): void }) => {
    if (!selectionLocked(editor)) return undefined;
    event.preventDefault();
    return true;
  };

  return (
    <Doc.Provider value={shared}>
      <Plate
        editor={editor}
        onValueChange={({ value }) => {
          if (value !== shown.current) dirty.current = true;
        }}
        onSelectionChange={({ selection }) => report(selection)}
      >
        <PlateContent
          aria-label={props.label}
          dir={dir(language)}
          lang={language}
          readOnly={props.readOnly}
          decorate={decorate as never}
          className="mx-auto min-h-24 max-w-[44rem] px-8 py-6 text-start outline-none focus-visible:ring-1 focus-visible:ring-slate"
          onDOMBeforeInput={stop}
          onPaste={stop}
          onCut={stop}
          onDrop={stop}
          onBlur={() => void commit()}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
              event.preventDefault();
              void commit();
            }
          }}
        />
      </Plate>
    </Doc.Provider>
  );
}
