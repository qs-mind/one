// The sources under a reply or a decision: a row of link-looking buttons, each opening its source in ONE's viewer.
// Up to four sit in the row; more fold under "{n} sources".
import { textDir } from "@/texts/language";
import { conversation } from "@/texts/conversation";
import { type Translate, useText } from "@/texts/useText";
import { Source, Sources, SourcesContent, SourcesTrigger } from "./ai/sources";
import type { Source as SourceData } from "./parts";

const IN_ROW = 4;

/** A source in words: its title, and where in it when the core knows (a page, a BOQ item, a row). */
export function sourceLabel(source: SourceData, t: Translate): string {
  const { page, item, row } = source.locator;
  if (typeof page === "number") return t(conversation.sourcePage, { title: source.title, page });
  if (typeof item === "string") return t(conversation.sourceItem, { title: source.title, item });
  if (typeof row === "number") return t(conversation.sourceRow, { title: source.title, row });
  return source.title;
}

type SourceLinksProps = { sources: readonly SourceData[]; onOpen?: (source: SourceData) => void };

export function SourceLinks({ sources, onOpen }: SourceLinksProps) {
  const t = useText();
  if (sources.length === 0) return null;
  const links = sources.map((source, index) => {
    const label = sourceLabel(source, t);
    return (
      // A source has no id of its own; its place in the list is its identity.
      <Source key={index} title={<bdi dir={textDir(label)}>{label}</bdi>} onClick={() => onOpen?.(source)} />
    );
  });
  if (sources.length <= IN_ROW) return <div className="flex flex-wrap gap-x-5">{links}</div>;
  return (
    <Sources>
      <SourcesTrigger label={t.plural(conversation.sources, sources.length)} />
      <SourcesContent>{links}</SourcesContent>
    </Sources>
  );
}
