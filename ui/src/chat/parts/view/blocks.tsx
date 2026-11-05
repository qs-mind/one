// One small component per view block (decision 16.1). Each draws only what the core checked: words as plain text,
// numbers as the core resolved them, each with its source chip. Logical CSS only, so a block reads right to left in
// an Arabic view; brand colours only, no shadows.
import type { NumberCell } from "../../../deliverables/types";
import { BlockBoundary } from "./BlockBoundary";
import { useViewEnv } from "./env";
import { Num } from "./Num";
import { viewBlocks } from "./registry";
import type { FiguresBlock, GroupBlock, HeadingBlock, ProseBlock, TableBlock } from "./types";
import { Words } from "./Words";

export function Heading({ block }: { block: HeadingBlock }) {
  const { unsourced } = useViewEnv();
  return (
    <h4 dir="auto" className="font-semibold">
      <Words text={block.text} unsourced={unsourced} />
    </h4>
  );
}

/** Plain words: a blank line starts a paragraph, a line break stays. */
export function Prose({ block }: { block: ProseBlock }) {
  const { unsourced } = useViewEnv();
  const paragraphs = block.text.split(/\n\s*\n/).filter((p) => p.trim());
  return (
    <div className="flex flex-col gap-2">
      {paragraphs.map((p, i) => (
        <p key={i} dir="auto" className="whitespace-pre-line">
          <Words text={p} unsourced={unsourced} />
        </p>
      ))}
    </div>
  );
}

export function Figures({ block }: { block: FiguresBlock }) {
  const { unsourced } = useViewEnv();
  return (
    <dl className="flex flex-wrap gap-3">
      {block.items.map((item, i) => (
        <div key={i} className="flex min-w-36 flex-col gap-1 rounded-md border border-stone px-3 py-2">
          <dt dir="auto" className="text-xs text-slate">
            <Words text={item.label} unsourced={unsourced} />
          </dt>
          <dd>
            <Num cell={item.value} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

const isCell = (value: string | NumberCell | undefined): value is NumberCell =>
  typeof value === "object" && value !== null && typeof value.value === "string";

export function Table({ block }: { block: TableBlock }) {
  const { unsourced } = useViewEnv();
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-start">
        <thead>
          <tr>
            {block.columns.map((c) => (
              <th
                key={c.key}
                scope="col"
                dir="auto"
                className={`border-b border-stone px-2 py-1 font-semibold ${c.type === "number" ? "text-end" : "text-start"}`}
              >
                <Words text={c.label} unsourced={unsourced} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, i) => (
            <tr key={i}>
              {block.columns.map((c) => {
                const value = row[c.key];
                return (
                  <td key={c.key} className={`border-b border-stone px-2 py-1 ${c.type === "number" ? "text-end" : ""}`}>
                    {isCell(value) ? (
                      <Num cell={value} />
                    ) : typeof value === "string" ? (
                      <span dir="auto">
                        <Words text={value} unsourced={unsourced} />
                      </span>
                    ) : null}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Blocks shown together under a title. It holds leaves only: a group in a group shows nothing. */
export function Group({ block }: { block: GroupBlock }) {
  const { unsourced } = useViewEnv();
  return (
    <section
      aria-label={block.title ?? undefined}
      className="flex flex-col gap-3 border-s-2 border-stone ps-3"
    >
      {block.title && (
        <h5 dir="auto" className="font-semibold text-slate">
          <Words text={block.title} unsourced={unsourced} />
        </h5>
      )}
      {block.blocks.map((leaf, i) =>
        leaf.kind === ("group" as string) ? null : <BlockBoundary key={i} block={leaf} registry={viewBlocks} />,
      )}
    </section>
  );
}
