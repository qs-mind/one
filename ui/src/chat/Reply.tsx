// The Lead QS's reply as Markdown: bold, lists, tables and code. Never raw HTML; links and images open nothing.
// A number the numbers guard found with no source is marked where it stands.
import { createElement, useMemo, type ReactNode } from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";
import { t, useLanguage } from "../i18n";
import { isolateOtherScript } from "./bidi";

type BlockProps = ExtraProps & { className?: string; children?: ReactNode };

// Each block takes the direction of its own first letters, so English reads left to right inside the Arabic page; the
// runs in the other script inside a block are isolated (./bidi).
function block(tag: string, className?: string) {
  return function Block({ node: _node, className: given, ...props }: BlockProps) {
    return createElement(tag, { ...props, dir: "auto", className: [given, className].filter(Boolean).join(" ") });
  };
}

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
  table: block("table", "border-collapse"),
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

/** A remark step that wraps each whole unsourced number in its text in a <mark>, in prose and tables alike. */
function markUnsourced(values: string[], title: string) {
  // whole numbers only: "7,500" is not marked inside "17,500" or "7,500.25"
  const pattern = new RegExp(`(?<!${digit}[.,\u066B\u066C]?)(?:${values.map(escape).join("|")})(?![.,\u066B\u066C]?${digit})`, "g");
  const split = (value: string): Node[] => {
    const out: Node[] = [];
    let at = 0;
    for (const match of value.matchAll(pattern)) {
      if (match.index > at) out.push({ type: "text", value: value.slice(at, match.index) });
      out.push({
        type: "unsourced",
        data: { hName: "mark", hProperties: { title } },
        children: [{ type: "text", value: match[0] }],
      });
      at = match.index + match[0].length;
    }
    if (at < value.length) out.push({ type: "text", value: value.slice(at) });
    return out;
  };
  const walk = (node: Node) => {
    if (!node.children) return;
    node.children = node.children.flatMap((child) => (child.type === "text" ? split(child.value ?? "") : [child]));
    for (const child of node.children) if (child.type !== "unsourced") walk(child);
  };
  return () => walk;
}

export function Reply({ text, unsourced = [] }: { text: string; unsourced?: string[] }) {
  const lang = useLanguage();
  const key = unsourced.join("\n");
  const plugins = useMemo(() => {
    const values = key ? key.split("\n") : [];
    return values.length
      ? [remarkGfm, markUnsourced(values, t("noSource")), isolateOtherScript()]
      : [remarkGfm, isolateOtherScript()];
  }, [key, lang]);
  return (
    <div className="flex flex-col gap-2">
      <Markdown remarkPlugins={plugins} components={components} skipHtml>
        {text}
      </Markdown>
      {unsourced.length > 0 && <p className="text-slate">{t("noSourceNote")}</p>}
    </div>
  );
}
