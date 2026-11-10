// The tender place (layout A, Main.dc.html): the conversation centred with its header and message box, and the side
// column beside it at desktop widths (under it below 900px). Opening a document, the team room or a member's card
// (their routes) replaces the side column: the document takes at least 60% of the width beside a narrow thread, the
// split moved by its handle (react-resizable-panels); Full screen leaves the document alone. One component serves
// the four addresses.
import { useSyncExternalStore } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import { useLocation, useNavigate, useParams, useSearchParams } from "react-router";
import type { Schemas } from "@/api/client";
import { paths } from "@/app/paths";
import type { Source } from "@/conversation/parts";
import { SourceLinks } from "@/conversation/SourceLinks";
import { MetaLine } from "@/design/MetaLine";
import { Pill } from "@/design/Pill";
import { common } from "@/texts/common";
import { formatDate } from "@/texts/format";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { type Translate, useText } from "@/texts/useText";
import type { SourceLocator } from "@/project/types";
import { openSourceFile } from "@/workspace/reveal";
import { DocumentHost, FULL, type Opened } from "./DocumentHost";
import { revealWaiting } from "./revealWaiting";
import { SideColumn } from "./SideColumn";
import { TenderThread } from "./TenderThread";
import { useTender } from "./useTender";
import { useThread } from "./useThread";
import { useKeptDocuments } from "./viewers/KeptDocument";

export type TenderView = "conversation" | "doc" | "room" | "member";

const DAY_MS = 86_400_000;
const WIDE = "(min-width: 56.25rem)"; // md: 900px

function useWide(): boolean {
  return useSyncExternalStore(
    (listener) => {
      const query = window.matchMedia?.(WIDE);
      query?.addEventListener("change", listener);
      return () => query?.removeEventListener("change", listener);
    },
    () => window.matchMedia?.(WIDE).matches ?? true,
  );
}

/** "Submission 16 November · 5 days left", from the tender fact and the screen's own clock (S39, S40). */
function dateLine(row: Schemas["TenderRow"], t: Translate): string[] {
  if (!row.submission_date) return [t(texts.noSubmission)];
  const day = new Date(`${row.submission_date}T00:00:00Z`);
  const today = new Date();
  const left = Math.round((day.getTime() - Date.UTC(today.getFullYear(), today.getMonth(), today.getDate())) / DAY_MS);
  const date = t(texts.submission, { date: formatDate(day, t.lang, { day: "numeric", month: "long", timeZone: "UTC" }) });
  return [date, left < 0 ? t(texts.submissionPassed) : t.plural(common.daysLeft, left)];
}

/** Where the submission date comes from (S39): the engineer's own word, or the place it was read, which opens, and
 * the mark of a local OCR read that was not sure. */
function DateSource({ source, onOpen }: { source: Source; onOpen: (source: Source) => void }) {
  const t = useText();
  if (source.kind === "engineer") return <span className="text-xs text-muted-foreground">{t(texts.submissionYours)}</span>;
  return (
    <>
      <span className="text-xs">
        <SourceLinks sources={[source]} onOpen={onOpen} />
      </span>
      {source.locator.ocr_low_confidence === true && <span className="text-xs text-copper">{t(texts.submissionUnsure)}</span>}
    </>
  );
}

function Header({ row, onOpenSource }: { row: Schemas["TenderRow"]; onOpenSource: (source: Source) => void }) {
  const t = useText();
  const name = row.name_pair ? t(row.name_pair) : row.name;
  return (
    <header className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
      <h1 className="text-2xl font-bold">
        <bdi dir={textDir(name)}>{name}</bdi>
      </h1>
      <MetaLine className="text-xs text-muted-foreground" items={dateLine(row, t)} />
      {row.submission_date && row.submission_source && <DateSource source={row.submission_source} onOpen={onOpenSource} />}
      {row.sample && <Pill>{t(common.sample)}</Pill>}
      {row.confidential && <Pill>{t(texts.confidential)}</Pill>}
    </header>
  );
}

export function Tender() {
  const t = useText();
  const { id = "", docId, memberId } = useParams();
  const end = useLocation().pathname.split("/")[3];
  const view: TenderView = end === "doc" || end === "room" || end === "member" ? end : "conversation";
  const full = useSearchParams()[0].has(FULL);
  const wide = useWide();
  const { brief, actions, ...data } = useTender(id);
  const thread = useThread(id, brief);
  const kept = useKeptDocuments(id, data.open);
  const navigate = useNavigate();
  const row = data.view?.tender;

  // A source in the thread opens its file beside it, at its place (only a source in a file has one to open).
  const openSource = (source: Source) => {
    if (!source.file_id) return;
    openSourceFile(source.file_id, source.locator as SourceLocator, []);
    navigate(paths.doc(id, `file:${source.file_id}`));
  };

  const opened: Opened | null =
    view === "doc" && docId ? { kind: "doc", docId } : view === "room" ? { kind: "room" } : view === "member" && memberId ? { kind: "member", memberId } : null;
  const conversation = <TenderThread data={data} actions={actions} thread={thread} narrow={opened !== null} onOpenSource={openSource} />;

  let body;
  if (!row)
    body = (
      <p role={data.refused ? "alert" : "status"} className="px-(--gutter) pt-7 text-muted-foreground">
        {data.refused === null ? t(texts.opening) : data.refused === "unreachable" ? t(texts.notOpened) : t(data.refused)}
      </p>
    );
  else if (opened) {
    const host = <DocumentHost projectId={id} opened={opened} sample={row.sample} kept={kept} />;
    body = full ? (
      host
    ) : (
      <Group orientation={wide ? "horizontal" : "vertical"} className="min-h-0 flex-1">
        <Panel id="thread" defaultSize="28" minSize={wide ? 300 : 240} maxSize="40" className="px-(--gutter) pt-7 pb-6 md:ps-7 md:pe-7">
          {conversation}
        </Panel>
        <Separator
          aria-label={t(texts.resize)}
          className="focus-inset relative bg-border after:absolute after:inset-y-0 after:-inset-x-[22px] aria-[orientation=horizontal]:h-px aria-[orientation=vertical]:w-px"
        />
        <Panel id="document" minSize="60">
          {host}
        </Panel>
      </Group>
    );
  } else
    body = (
      <div className="flex flex-col md:min-h-0 md:flex-1 md:flex-row">
        <div className="flex h-[80dvh] min-w-0 flex-col gap-8 px-(--gutter) pt-7 pb-6 md:h-auto md:flex-1">
          <div className="mx-auto w-full max-w-190">
            <Header row={row} onOpenSource={openSource} />
          </div>
          <div className="mx-auto min-h-0 w-full max-w-190 flex-1">{conversation}</div>
        </div>
        <SideColumn projectId={id} waiting={data.view?.waiting ?? []} plan={data.plan} members={data.members} docs={kept.docs} onReveal={revealWaiting} />
      </div>
    );

  return (
    <main
      data-place="tender"
      data-tender={id}
      data-view={view}
      data-doc={docId}
      data-member={memberId}
      className="flex min-h-full flex-col md:h-full"
    >
      {body}
    </main>
  );
}
