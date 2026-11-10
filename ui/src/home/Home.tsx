// Home (spec "Three places", 1; mockup Home.dc.html): the greeting with the engineer's first name, the Lead's summary
// when the core has one (never a line made up in its place), what waits for the engineer, the tenders in the core's
// order (nearest submission first) and the one message box, which also takes a dropped tender folder. With no
// tender, one line invites the folder. It moves with the `home` event.
import { useRef } from "react";
import type { Schemas } from "@/api/client";
import { ListRow } from "@/design/ListRow";
import { Pill } from "@/design/Pill";
import { SectionLabel } from "@/design/SectionLabel";
import { Button } from "@/design/ui/button";
import { common } from "@/texts/common";
import { home as texts } from "@/texts/home";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import { isMorning, useClock } from "./days";
import { HomeBox } from "./HomeBox";
import { TenderRow } from "./TenderRow";
import { useHome } from "./useHome";
import { Waiting } from "./Waiting";

function Greeting({ firstName, now }: { firstName: string; now: Date }) {
  const t = useText();
  const morning = isMorning(now);
  if (!firstName) return <>{t(morning ? texts.morningNoName : texts.eveningNoName)}</>;
  return <>{t(morning ? texts.morning : texts.evening, { name: firstName })}</>;
}

function Summary({ summary, listed }: { summary: Schemas["HomeSummary"]; listed: number }) {
  const t = useText();
  const left = listed - summary.covers;
  return (
    <div className="flex max-w-155 flex-col gap-1">
      <p dir={textDir(summary.text)} className="text-lg text-muted-foreground">
        {summary.text}
      </p>
      {left > 0 && <p className="text-xs text-muted-foreground">{t.plural(texts.leftOut, left)}</p>}
    </div>
  );
}

function Tenders({ home, now }: { home: Schemas["Home"]; now: Date }) {
  const t = useText();
  const allSample = home.tenders.every((row) => row.sample);
  const near = home.tenders.find((row) => row.state !== "finished" && row.submission_date)?.project_id;
  return (
    <section aria-labelledby="home-tenders" className="flex flex-col">
      <SectionLabel id="home-tenders" className="mb-2">
        {t(common.tenders)}
      </SectionLabel>
      {home.tenders.map((row) => (
        <TenderRow key={row.project_id} row={row} today={now} near={row.project_id === near} samplePill={!allSample} />
      ))}
      {home.unreadable.map((it) => (
        <ListRow key={it.project_id} frame="divided" tone="muted" title={t(texts.cannotOpen)} meta={t(it.reason)} />
      ))}
    </section>
  );
}

export function Home() {
  const t = useText();
  const now = useClock();
  const { state, reload } = useHome();
  const conversation = useRef<HTMLElement>(null);
  const ready = state.status === "ready" ? state.home : null;
  const empty = ready !== null && ready.tenders.length === 0 && ready.unreadable.length === 0;
  const nameOf = (id: string) => {
    const row = ready?.tenders.find((it) => it.project_id === id);
    return row ? (row.name_pair ? t(row.name_pair) : row.name) : null;
  };

  return (
    <main
      data-place="home"
      aria-busy={state.status === "loading" || undefined}
      className="mx-auto flex min-h-full w-full max-w-230 flex-col gap-10 px-4 pt-12 pb-10 md:px-14 md:pt-18"
    >
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline gap-4">
          <h1 className="text-3xl font-bold">
            <Greeting firstName={state.status === "ready" ? state.firstName : ""} now={now} />
          </h1>
          {ready && ready.tenders.length > 0 && ready.tenders.every((row) => row.sample) && (
            <Pill className="ms-auto">{t(common.sample)}</Pill>
          )}
        </div>
        {ready?.summary && <Summary summary={ready.summary} listed={ready.tenders.length} />}
      </header>

      {state.status === "failed" && (
        <div role="alert" className="flex flex-wrap items-center gap-3">
          <p>{t(texts.loadFailed)}</p>
          <Button variant="outline" onClick={reload}>
            {t(texts.tryAgain)}
          </Button>
        </div>
      )}
      {ready && (
        <Waiting
          items={ready.waiting}
          nameOf={nameOf}
          onHomeConversation={() => conversation.current?.focus()}
        />
      )}
      {ready && !empty && <Tenders home={ready} now={now} />}
      {empty && <p className="text-lg text-muted-foreground">{t(texts.empty)}</p>}

      <div className="flex-1" />
      <HomeBox blocked={ready?.blocked ?? null} conversationRef={conversation} />
    </main>
  );
}
