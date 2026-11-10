// A clicked number's source, in a panel under the sheet (Document.dc.html, S147 to S155): which number and its value,
// how it was worked out, where it comes from and when, and the way to the file. It reads the core's explain of the
// number (GET .../numbers/{id}/explain); a number with no recorded source says so. Only what the core has is shown.
import { XIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { deliverablesApi } from "@/deliverables/api";
import type { Explained } from "@/deliverables/types";
import { Num } from "@/design/Num";
import { Pill } from "@/design/Pill";
import { Button } from "@/design/ui/button";
import type { NumberAsked } from "@/viewers/sheet/numberTarget";
import { openSourceFile } from "@/workspace/reveal";
import { common } from "@/texts/common";
import { formatDate } from "@/texts/format";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";

type Read = { state: "reading" } | { state: "read"; explained: Explained } | { state: "none" } | { state: "failed" };

function useExplained(projectId: string, numberId: string | null): Read {
  const [read, setRead] = useState<Read & { id?: string | null }>({ state: "reading" });
  useEffect(() => {
    if (!numberId) return setRead({ state: "none", id: numberId });
    let live = true;
    setRead({ state: "reading", id: numberId });
    deliverablesApi.explain(projectId, numberId).then(
      (answer) => live && setRead(answer.ok ? { state: "read", explained: answer.data, id: numberId } : { state: "failed", id: numberId }),
      () => live && setRead({ state: "failed", id: numberId }),
    );
    return () => {
      live = false;
    };
  }, [projectId, numberId]);
  return read;
}

export function SourcePanel({ projectId, asked, onClose }: { projectId: string; asked: NumberAsked; onClose: () => void }) {
  const t = useText();
  const { cell, label } = asked;
  const read = useExplained(projectId, cell.number_id);
  const unit = cell.currency ?? cell.unit;
  const listed = cell.source ? asked.sources[cell.source] : undefined;
  const source = read.state === "read" ? read.explained.source : listed;
  const calculation = read.state === "read" ? read.explained.calculation : null;
  const dated = (read.state === "read" ? read.explained.source.dated : null) ?? cell.dated;
  const day = dated ? formatDate(new Date(`${dated.slice(0, 10)}T00:00:00Z`), t.lang, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }) : null;
  const fileId = source?.file_id ?? null;

  return (
    <section
      aria-label={t(texts.sourceLabel)}
      data-source-panel
      className="flex max-w-190 flex-wrap items-start gap-8 rounded-2xl bg-muted px-6 py-5"
    >
      <div className="flex flex-[1_1_14rem] flex-col">
        <span className="text-xs text-muted-foreground" dir={textDir(label)}>
          {label}
        </span>
        <strong className="text-xl">
          <Num>{cell.value}</Num>
          {unit && (
            <>
              {" "}
              <bdi dir={textDir(unit)}>{unit}</bdi>
            </>
          )}
        </strong>
      </div>
      <div className="flex flex-[2_1_20rem] flex-col gap-1 text-xs text-muted-foreground">
        {read.state === "reading" && <span role="status">{t(texts.sourceReading)}</span>}
        {read.state === "failed" && <span role="alert">{t(texts.sourceFailed)}</span>}
        {calculation && (
          <span dir={textDir(calculation.formula)}>{t(texts.sourceMade, { formula: calculation.formula })}</span>
        )}
        {calculation?.stale && <span className="font-bold text-foreground">{t(texts.sourceStale)}</span>}
        {source ? (
          <span className="flex flex-wrap items-center gap-2">
            <span dir={textDir(source.title)}>{t(texts.sourceFrom, { title: source.title })}</span>
            {day && <span>{day}</span>}
            {source.kind === "sample" && <Pill>{t(common.sample)}</Pill>}
          </span>
        ) : (
          read.state !== "reading" && <span>{t(texts.sourceNone)}</span>
        )}
        {fileId && source && (
          <Button
            variant="link"
            className="self-start text-xs"
            onClick={() => openSourceFile(fileId, source.locator, [cell.value])}
          >
            {t(texts.openSource)}
          </Button>
        )}
      </div>
      <Button variant="ghost" size="icon" aria-label={t(texts.closeSource)} onClick={onClose}>
        <XIcon aria-hidden />
      </Button>
    </section>
  );
}
