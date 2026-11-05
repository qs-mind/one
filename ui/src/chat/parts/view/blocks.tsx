// One small component per view block (decision 16.1). Each draws only what the core checked: words as plain text,
// numbers as the core resolved them, each with its source chip. Logical CSS only, so a block reads right to left in
// an Arabic view; brand colours only, no shadows.
import { BlockBoundary } from "./BlockBoundary";
import { useViewEnv } from "./env";
import { Num } from "./Num";
import { viewBlocks } from "./registry";
import type { FiguresBlock, HeadingBlock, ProseBlock, TableBlock, ViewBlock } from "./types";
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
    // equal columns, so the cards line up whatever their words' length
    <dl className="grid grid-cols-[repeat(auto-fill,minmax(10rem,1fr))] gap-3">
      {block.items.map((item, i) => (
        <div key={i} className="flex min-w-0 flex-col justify-between gap-1 rounded-md border border-stone px-3 py-2">
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

/** A row is its label (headed by `label_header`), then its texts, then its numbers: where a value stands says what it
 * is, so the last columns, as many as the first row's numbers, are the number columns. */
export function Table({ block }: { block: TableBlock }) {
  const { unsourced } = useViewEnv();
  const firstNumber = block.columns.length - (block.rows[0]?.numbers.length ?? 0);
  const cell = "border-b border-stone px-2 py-1";
  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-start">
        <thead>
          <tr>
            <th scope="col" dir="auto" className={`${cell} text-start font-semibold`}>
              <Words text={block.label_header} unsourced={unsourced} />
            </th>
            {block.columns.map((c, i) => (
              <th
                key={i}
                scope="col"
                dir="auto"
                className={`${cell} font-semibold ${i >= firstNumber ? "text-end" : "text-start"}`}
              >
                <Words text={c.label} unsourced={unsourced} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {block.rows.map((row, i) => (
            <tr key={i}>
              <th scope="row" dir="auto" className={`${cell} text-start font-normal`}>
                <Words text={row.label} unsourced={unsourced} />
              </th>
              {row.texts.map((text, j) => (
                <td key={`t${j}`} className={cell}>
                  <span dir="auto">
                    <Words text={text} unsourced={unsourced} />
                  </span>
                </td>
              ))}
              {row.numbers.map((number, j) => (
                <td key={`n${j}`} className={`${cell} text-end`}>
                  <Num cell={number} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A run of blocks under one section title, one level deep. */
export function Section({ title, blocks }: { title: string; blocks: ViewBlock[] }) {
  const { unsourced } = useViewEnv();
  return (
    <section aria-label={title} className="flex flex-col gap-3 border-s-2 border-stone ps-3">
      <h5 dir="auto" className="font-semibold text-slate">
        <Words text={title} unsourced={unsourced} />
      </h5>
      {blocks.map((block, i) => (
        <BlockBoundary key={i} block={block} registry={viewBlocks} />
      ))}
    </section>
  );
}
