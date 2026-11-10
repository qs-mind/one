// One message of the team room: who wrote to whom, the text in its own direction, and its sources as links. A
// message the Lead raised to the engineer that still waits is the waiting block (a Stone panel under the copper
// label, as TeamRoom.dc.html draws it) with the way to answer; once answered it is an ordinary message that says so.
import { Link } from "react-router";
import { paths } from "@/app/paths";
import { SourceLinks } from "@/conversation/SourceLinks";
import { IconForward } from "@/design/icons";
import { WaitingLabel } from "@/design/now-waiting";
import { buttonVariants } from "@/design/ui/button";
import { textDir } from "@/texts/language";
import { team } from "@/texts/team";
import { type Translate, useText } from "@/texts/useText";
import { nameOf, type TeamMember } from "./useTeam";
import type { RoomMessage as Message } from "./useRoom";

type Source = Message["sources"][number];

type RoomMessageProps = {
  projectId: string;
  message: Message;
  members: readonly TeamMember[];
  onOpenSource?: (source: Source) => void;
};

/** Who an id names in the room: a member of this tender, the engineer, or the whole team. */
export function who(id: string, members: readonly TeamMember[], t: Translate): string {
  if (id === "engineer") return t(team.you);
  if (id === "team") return t(team.everyone);
  const name = nameOf(members, id);
  return name ? t(name) : t(team.unknownMember);
}

function Words({ text }: { text: string }) {
  return (
    <p dir={textDir(text)} className="whitespace-pre-wrap">
      {text}
    </p>
  );
}

export function RoomMessage({ projectId, message, members, onOpenSource }: RoomMessageProps) {
  const t = useText();
  const from = who(message.from_id, members, t);
  const to = who(message.to_id, members, t);

  if (message.raised && !message.raised.answered)
    return (
      <article data-message={message.id} data-raised="waiting" className="flex flex-col gap-3 rounded-2xl bg-muted px-6 py-5">
        <WaitingLabel>{t(team.raised, { name: from })}</WaitingLabel>
        <Words text={message.text} />
        <SourceLinks sources={message.sources} onOpen={onOpenSource} />
        <Link to={paths.tender(projectId)} className={buttonVariants({ variant: "link", className: "self-start" })}>
          {t(team.answer)}
        </Link>
      </article>
    );

  return (
    <article data-message={message.id} data-raised={message.raised ? "answered" : undefined} className="flex flex-col gap-2">
      {message.raised ? (
        <p className="text-xs text-muted-foreground">{t(team.answered, { name: from })}</p>
      ) : (
        <p className="text-xs text-muted-foreground">
          <span className="sr-only">{t(team.fromTo, { from, to })}</span>
          <span aria-hidden className="inline-flex flex-wrap items-center gap-2">
            <bdi dir={textDir(from)}>{from}</bdi>
            <IconForward className="size-4" />
            <bdi dir={textDir(to)}>{to}</bdi>
          </span>
        </p>
      )}
      <Words text={message.text} />
      <SourceLinks sources={message.sources} onOpen={onOpenSource} />
    </article>
  );
}
