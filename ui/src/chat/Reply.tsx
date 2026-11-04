// The Lead QS's reply as Markdown: bold, lists, tables and code. Never raw HTML; links and images open nothing.
import { createElement, type ReactNode } from "react";
import Markdown, { type Components, type ExtraProps } from "react-markdown";
import remarkGfm from "remark-gfm";

type BlockProps = ExtraProps & { className?: string; children?: ReactNode };

// Each block takes the direction of its own first letters, so English reads left to right inside the Arabic page.
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
  ul: block("ul", "list-disc ps-5"),
  ol: block("ol", "list-decimal ps-5"),
  li: block("li"),
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
};

export function Reply({ text }: { text: string }) {
  return (
    <div className="flex flex-col gap-2">
      <Markdown remarkPlugins={[remarkGfm]} components={components} skipHtml>
        {text}
      </Markdown>
    </div>
  );
}
