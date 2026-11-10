// Where a submission date comes from (S39): the engineer's own word, or the place it was read, and the mark of a
// local OCR read that was not sure. In full it is a button that opens the file at its place; compact it is plain
// words, for a row that is itself a link (Home's tender rows), where the row opens the tender.
import { WaitingWord } from "@/design/now-waiting";
import type { Source } from "@/conversation/parts";
import { SourceLinks, sourceLabel } from "@/conversation/SourceLinks";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";

type DateSourceProps = { source: Source; onOpen?: (source: Source) => void; compact?: boolean };

export function DateSource({ source, onOpen, compact = false }: DateSourceProps) {
  const t = useText();
  if (source.kind === "engineer") return <span className="text-xs text-muted-foreground">{t(texts.submissionYours)}</span>;
  const unsure = source.locator.ocr_low_confidence === true;
  if (compact) {
    const label = sourceLabel(source, t);
    return (
      <span className="flex min-w-0 flex-col text-xs">
        <bdi dir={textDir(label)} title={label} className="truncate">
          {label}
        </bdi>
        {unsure && <WaitingWord>{t(texts.submissionUnsureShort)}</WaitingWord>}
      </span>
    );
  }
  return (
    <>
      <span className="text-xs">
        <SourceLinks sources={[source]} onOpen={onOpen} />
      </span>
      {unsure && <WaitingWord>{t(texts.submissionUnsure)}</WaitingWord>}
    </>
  );
}
