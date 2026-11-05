// The Lead QS's reply as Markdown: bold, lists, tables and code. Never raw HTML; links and images open nothing.
// A number the numbers guard found with no source is marked where it stands; a number one ledger number gave opens in
// place into its source card, and hovering it draws its source line to that number in a sheet or document on screen.
import { createElement, useMemo, type ReactNode } from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";
import { fill, t, useLanguage } from "../i18n";
import { sourceLineHandlers } from "../sources/line";
import { useSourceCard } from "../sources/useSourceCard";
import { isolateOtherScript } from "./bidi";
import type { SourcedData } from "./parts/types";

type BlockProps = ExtraProps & { className?: string; children?: ReactNode };

// Each block takes the direction of its own first letters, so English reads left to right inside the Arabic page; the
// runs in the other script inside a block are isolated (./bidi).
function block(tag: string, className?: string) {
  return function Block({ node: _node, className: given, ...props }: BlockProps) {
    return createElement(tag, { ...props, dir: "auto", className: [given, className].filter(Boolean).join(" ") });
  };
}

const Table = block("table", "border-collapse");

const components: Components = {
  p: block("p"),
  h1: block("h1", "font-semibold"),
  h2: block("h2", "font-semibold"),
  h3: block("h3", "font-semibold"),
  h4: block("h4", "font-semibold"),
  h5: block("h5", "font-semibold"),
  h6: block("h6", "font-semibold"),
  // the room for the marker is on each item's own start side, so an English item in an Arabic list has it on the left
  ul: block("ul", "list-disc"),
  ol: block("ol", "list-decimal"),
  li: block("li", "ms-5"),
  blockquote: block("blockquote", "border-s-2 border-slate ps-3 text-slate"),
  // a wide table scrolls inside its own box, not the chat
  table: (props) => (
    <div className="overflow-x-auto">
      <Table {...props} />
    </div>
  ),
  th: block("th", "border border-stone px-2 py-1 text-start font-semibold"),
  td: block("td", "border border-stone px-2 py-1"),
  pre: ({ node: _node, ...props }) => (
    <pre {...props} dir="ltr" className="overflow-x-auto rounded-md bg-stone p-3 font-mono [&_code]:px-0" />
  ),
  code: ({ node: _node, className, ...props }) => (
    <code {...props} className={[className, "rounded bg-stone px-1 font-mono"].filter(Boolean).join(" ")} />
  ),
  // A link is text in the app window: its words, then its address when that adds something.
  a: ({ href, children }) => (
    <span className="underline decoration-slate">
      {children}
      {href && href !== children && (
        <>
          {" ("}
          <bdi dir="ltr">{href}</bdi>
          {")"}
        </>
      )}
    </span>
  ),
  img: ({ alt }) => <span>{alt}</span>,
  hr: () => <hr className="border-stone" />,
  mark: ({ node: _node, ...props }) => (
    <mark {...props} className="rounded-sm bg-stone px-0.5 text-copper underline decoration-dotted" />
  ),
};

type Node = { type: string; value?: string; children?: Node[]; data?: object };

const escape = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const digit = "[0-9\u0660-\u0669]";

/** A remark step that wraps each whole number of `values` in its text in an element, in prose and tables alike: an
 * unsourced one in a <mark>, a sourced one in a <data> naming how it is written. */
function markNumbers(values: string[], element: (written: string) => { hName: string; hProperties: object }) {
  // whole numbers only: "7,500" is not marked inside "17,500" or "7,500.25"
  const pattern = new RegExp(`(?<!${digit}[.,\u066B\u066C]?)(?:${values.map(escape).join("|")})(?![.,\u066B\u066C]?${digit})`, "g");
  const split = (value: string): Node[] => {
    const out: Node[] = [];
    let at = 0;
    for (const match of value.matchAll(pattern)) {
      if (match.index > at) out.push({ type: "text", value: value.slice(at, match.index) });
      out.push({ type: "marked", data: element(match[0]), children: [{ type: "text", value: match[0] }] });
      at = match.index + match[0].length;
    }
    if (at < value.length) out.push({ type: "text", value: value.slice(at) });
    return out;
  };
  const walk = (node: Node) => {
    if (!node.children) return;
    node.children = node.children.flatMap((child) => (child.type === "text" ? split(child.value ?? "") : [child]));
    for (const child of node.children) if (child.type !== "marked") walk(child);
  };
  return () => walk;
}

export function Reply({
  text,
  unsourced = [],
  sourced = {},
  projectId,
}: {
  text: string;
  unsourced?: string[];
  sourced?: SourcedData["numbers"];
  /** A number opens into its source card only inside its project. */
  projectId?: string;
}) {
  const lang = useLanguage();
  const key = unsourced.join("\n");
  const sourcedKey = projectId ? Object.keys(sourced).join("\n") : "";
  const plugins = useMemo(() => {
    const values = key ? key.split("\n") : [];
    const opened = sourcedKey ? sourcedKey.split("\n") : [];
    return [
      remarkGfm,
      ...(values.length ? [markNumbers(values, () => ({ hName: "mark", hProperties: { title: t("noSource") } }))] : []),
      ...(opened.length ? [markNumbers(opened, (written) => ({ hName: "data", hProperties: { value: written } }))] : []),
      isolateOtherScript(),
    ];
  }, [key, sourcedKey, lang]);
  const source = useSourceCard(projectId ?? "");
  const shown: Components = {
    ...components,
    data: ({ value, children }) => {
      const number = typeof value === "string" ? sourced[value] : undefined;
      if (!number) return <>{children}</>;
      return (
        <button
          type="button"
          aria-label={fill(t("sourceOfNumber"), { value: String(value) })}
          className="rounded-sm border-b border-copper px-0.5 hover:bg-stone focus-visible:outline focus-visible:outline-copper"
          onClick={(event) =>
            source.open(event.currentTarget, { value: number.value, number_id: number.id, source: null, dated: null }, {}, { focus: event.detail === 0 })
          }
          {...sourceLineHandlers([`number:${number.id}`])}
        >
          {children}
        </button>
      );
    },
  };
  return (
    <div ref={source.host} className="relative flex flex-col gap-2">
      <Markdown remarkPlugins={plugins} components={shown} skipHtml>
        {text}
      </Markdown>
      {source.card}
      {unsourced.length > 0 && <p className="text-slate">{t("noSourceNote")}</p>}
    </div>
  );
}
