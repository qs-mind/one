// The place beside the narrow thread where something opens (Document.dc.html): a document, a file or the Project Map
// through the kept engines, the team room, or a member's card. Its header names it and holds Full screen and Close;
// both change the route (Close goes back to the conversation; Full screen, a toggle, adds or drops `?full`).
import { XIcon } from "lucide-react";
import { Link, useNavigate, useSearchParams } from "react-router";
import type { Schemas } from "@/api/client";
import { paths } from "@/app/paths";
import { Pill } from "@/design/Pill";
import { Button, buttonVariants } from "@/design/ui/button";
import { MemberCard } from "@/team/MemberCard";
import { Room } from "@/team/Room";
import { common } from "@/texts/common";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { useText } from "@/texts/useText";
import { docKeyOf, KeptDocument, type KeptDocuments, keptTitle } from "./viewers/KeptDocument";

export type Opened = { kind: "doc"; docId: string } | { kind: "room" } | { kind: "member"; memberId: string };

/** The address with or without `?full`, the same place otherwise. */
export const FULL = "full";

type DocumentHostProps = {
  projectId: string;
  opened: Opened;
  members: readonly Schemas["TeamMember"][];
  sample: boolean;
  kept: KeptDocuments;
};

export function DocumentHost({ projectId, opened, members, sample, kept }: DocumentHostProps) {
  const t = useText();
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const full = search.has(FULL);
  const docKey = opened.kind === "doc" ? docKeyOf(opened.docId) : null;

  let title: string;
  if (opened.kind === "room") title = t(texts.roomTitle);
  else if (opened.kind === "member") {
    const member = members.find((m) => m.id === opened.memberId);
    title = member ? t(member.name) : t(texts.memberTitle);
  } else title = (docKey && keptTitle(kept.docs, docKey)) || t(texts.documentTitle);

  const here =
    opened.kind === "room"
      ? paths.room(projectId)
      : opened.kind === "member"
        ? paths.member(projectId, opened.memberId)
        : paths.doc(projectId, opened.docId);

  return (
    <section aria-label={t(texts.documentLabel)} className="flex h-full min-h-0 flex-col gap-7 px-(--gutter) pt-7 pb-10 lg:px-12">
      <header className="flex flex-wrap items-center gap-5">
        <h1 className="min-w-0 flex-[1_1_17.5rem] text-2xl font-bold">
          <bdi dir={textDir(title)}>{title}</bdi>
        </h1>
        {sample && <Pill>{t(common.sample)}</Pill>}
        <Button variant="outline" aria-pressed={full} onClick={() => navigate(full ? here : `${here}?${FULL}`)}>
          {t(texts.fullScreen)}
        </Button>
        <Link to={paths.tender(projectId)} aria-label={t(texts.closeDocument)} className={buttonVariants({ variant: "outline", size: "icon" })}>
          <XIcon aria-hidden />
        </Link>
      </header>
      <div className="min-h-0 flex-1">
        {opened.kind === "room" ? (
          <Room projectId={projectId} />
        ) : opened.kind === "member" ? (
          <MemberCard projectId={projectId} memberId={opened.memberId} />
        ) : docKey ? (
          <KeptDocument projectId={projectId} docKey={docKey} sources={kept.sources} docs={kept.docs} />
        ) : (
          <p role="alert">{t(texts.noDocument)}</p>
        )}
      </div>
    </section>
  );
}
