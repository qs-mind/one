// The team room of a tender (TeamRoom.dc.html): the team's messages in the order they were written, the newest at
// the bottom beside the message box; older pages load as the engineer scrolls up (or presses Earlier messages). The
// side column lists the team. Everything moves with the tender's activity stream, with no reload.
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { client, type Schemas } from "@/api/client";
import { paths } from "@/app/paths";
import { Pill } from "@/design/Pill";
import { SectionLabel } from "@/design/SectionLabel";
import { Button } from "@/design/ui/button";
import { common } from "@/texts/common";
import { textDir } from "@/texts/language";
import { team as texts } from "@/texts/team";
import { useText } from "@/texts/useText";
import { MemberList } from "./MemberList";
import { RoomComposer } from "./RoomComposer";
import { RoomMessage } from "./RoomMessage";
import { type RoomMessage as Message, useRoom } from "./useRoom";
import { useTeam } from "./useTeam";

type Source = Message["sources"][number];

/** The tender's name and its sample flag for the header; nothing until they come. */
function useTenderRow(projectId: string): Schemas["TenderRow"] | null {
  const [row, setRow] = useState<Schemas["TenderRow"] | null>(null);
  useEffect(() => {
    let live = true;
    client
      .GET("/projects/{project_id}/tender", { params: { path: { project_id: projectId } } })
      .then(({ data }) => live && data && setRow(data.tender))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [projectId]);
  return row;
}

const NEAR = 48; // px from an edge that still counts as at it

export function Room({ projectId }: { projectId: string }) {
  const t = useText();
  const navigate = useNavigate();
  const row = useTenderRow(projectId);
  const { team } = useTeam(projectId);
  const { room, loadOlder, send, reload } = useRoom(projectId);
  const members = team.state === "ready" ? team.members : [];
  const teamLabel = useId();

  const scroller = useRef<HTMLDivElement>(null);
  const top = useRef<HTMLDivElement>(null);
  const keep = useRef<number | null>(null); // distance from the bottom while an older page loads
  const atBottom = useRef(true);
  const mine = useRef(false); // the engineer just sent: follow the newest message

  const messages = room.state === "ready" ? room.messages : [];
  const canOlder = room.state === "ready" && room.cursor !== null;
  const newest = messages[0]?.id;
  const oldest = messages.at(-1)?.id;

  const older = () => {
    const el = scroller.current;
    if (el) keep.current = el.scrollHeight - el.scrollTop;
    void loadOlder();
  };

  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el || keep.current === null) return;
    el.scrollTop = el.scrollHeight - keep.current;
    keep.current = null;
  }, [oldest]);

  useLayoutEffect(() => {
    const el = scroller.current;
    if (el && (atBottom.current || mine.current)) el.scrollTop = el.scrollHeight;
    mine.current = false;
  }, [newest]);

  // Text that grows after it is drawn (a font arriving, the window narrowing) keeps the newest message in view.
  useEffect(() => {
    const el = scroller.current;
    const content = el?.firstElementChild;
    if (!el || !content || typeof ResizeObserver === "undefined") return;
    const grows = new ResizeObserver(() => {
      if (atBottom.current) el.scrollTop = el.scrollHeight;
    });
    grows.observe(content);
    return () => grows.disconnect();
  }, []);

  // The top of the room in view, by whichever box scrolls: the next older page.
  useEffect(() => {
    const el = top.current;
    if (!el || !canOlder || typeof IntersectionObserver === "undefined") return;
    const seen = new IntersectionObserver((entries) => entries.some((it) => it.isIntersecting) && older());
    seen.observe(el);
    return () => seen.disconnect();
  });

  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR;
    if (el.scrollTop < NEAR && canOlder) older();
  };

  const openSource = (source: Source) => {
    if (source.file_id) void navigate(paths.doc(projectId, source.file_id), { state: { source } });
  };

  const name = row?.name ?? "";
  return (
    <div data-place="room" className="flex h-full min-h-0 flex-col overflow-y-auto md:flex-row md:overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col gap-8 px-(--gutter) pt-7 pb-8 md:min-h-0">
        <header className="flex flex-wrap items-baseline gap-x-5 gap-y-2">
          <h1 className="text-2xl font-bold">{t(texts.roomTitle)}</h1>
          {name && (
            <span dir={textDir(name)} className="text-muted-foreground">
              {name}
            </span>
          )}
          {row?.sample && <Pill className="ms-auto">{t(common.sample)}</Pill>}
        </header>

        <div ref={scroller} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto">
          <section role="log" aria-label={t(texts.roomLabel)} aria-busy={room.state === "loading"} className="mx-auto flex w-full max-w-(--measure) flex-col gap-7">
            <div ref={top} />
            {canOlder && (
              <Button variant="ghost" className="self-center" loading={room.older} onClick={older}>
                {t(texts.older)}
              </Button>
            )}
            {room.state === "loading" && <p className="text-muted-foreground">{t(common.loading)}</p>}
            {room.state === "failed" && (
              <div className="flex flex-col items-start gap-4">
                <p>{room.error ? t(room.error) : t(texts.roomFailed)}</p>
                <Button variant="outline" onClick={reload}>
                  {t(texts.tryAgain)}
                </Button>
              </div>
            )}
            {room.state === "ready" && messages.length === 0 && (
              <div className="flex flex-col gap-2">
                <p className="font-bold">{t(texts.roomEmpty)}</p>
                <p className="text-muted-foreground">{t(texts.roomEmptyBody)}</p>
              </div>
            )}
            {/* Held newest first; drawn in the order written, the newest last. Never sorted by time. */}
            {messages.toReversed().map((message) => (
              <RoomMessage key={message.id} projectId={projectId} message={message} members={members} onOpenSource={openSource} />
            ))}
          </section>
        </div>

        {room.state === "ready" && (
          <div className="mx-auto w-full max-w-(--measure)">
            <RoomComposer
              onSend={async (text) => {
                mine.current = true;
                const sent = await send(text);
                if (!sent.ok) mine.current = false;
                return sent;
              }}
            />
          </div>
        )}
      </div>

      <aside
        aria-labelledby={teamLabel}
        className="flex flex-col gap-3 border-t border-border px-8 py-7 md:w-75 md:shrink-0 md:overflow-y-auto md:border-t-0 md:border-s lg:w-(--side-w)"
      >
        <SectionLabel id={teamLabel}>{t(texts.teamTitle)}</SectionLabel>
        {team.state === "ready" && <MemberList projectId={projectId} members={team.members} />}
        {team.state === "failed" && <p className="text-muted-foreground">{team.error ? t(team.error) : t(texts.roomFailed)}</p>}
      </aside>
    </div>
  );
}
