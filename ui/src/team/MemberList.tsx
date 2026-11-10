// The tender's team in the room's side column (TeamRoom.dc.html, the aside): each member's short name, its kind and
// record, and what it is doing. Pressing a member opens its identity in place, with the way to its whole card.
import { useState } from "react";
import { Link } from "react-router";
import { paths } from "@/app/paths";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { buttonVariants } from "@/design/ui/button";
import { intlLocale } from "@/texts/format";
import { textDir } from "@/texts/language";
import { team } from "@/texts/team";
import { type Translate, useText } from "@/texts/useText";
import type { TeamMember } from "./useTeam";

/** fixed, permanent or temporary in words. */
export function kindWord(member: TeamMember, t: Translate): string {
  return t(member.kind === "fixed" ? team.fixed : member.kind === "permanent" ? team.permanent : team.temporary);
}

/** Its record in one line: a temporary member is in its first tender with the engineer (contract 15-16). */
export function recordWord(member: TeamMember, t: Translate): string {
  return member.kind === "temporary" ? t(team.firstTender) : t.plural(team.workedWith, member.record.tenders);
}

/** What it is doing now; else that its last work failed; else what it is for. */
export function doingWord(member: TeamMember, t: Translate): string {
  if (member.doing) return t(member.doing);
  return member.state === "failed" ? t(team.failed) : t(member.speciality);
}

export const toolList = (member: TeamMember, t: Translate): string =>
  member.tools.length === 0
    ? t(team.noTools)
    : new Intl.ListFormat(intlLocale(t.lang), { type: "conjunction" }).format(member.tools.map((tool) => t(tool.title)));

function Meta({ member }: { member: TeamMember }) {
  const t = useText();
  const second = member.role === "checker" ? t(team.independent) : recordWord(member, t);
  return <MetaLine items={[kindWord(member, t), second, member.proposed && t(team.proposed)]} />;
}

function Line({ text }: { text: string }) {
  return (
    <span dir={textDir(text)} className="text-xs">
      {text}
    </span>
  );
}

type MemberListProps = { projectId: string; members: readonly TeamMember[] };

export function MemberList({ projectId, members }: MemberListProps) {
  const t = useText();
  const [open, setOpen] = useState<string | null>(null);

  return (
    <ul className="flex flex-col gap-2">
      {members.map((member) => {
        const name = t(member.name);
        const toggle = () => setOpen((now) => (now === member.id ? null : member.id));
        const row = (
          <ListRow
            frame="plain"
            size="lg"
            render={<button type="button" aria-expanded={open === member.id} onClick={toggle} />}
            title={<bdi dir={textDir(name)}>{name}</bdi>}
            meta={<Meta member={member} />}
            detail={open === member.id ? undefined : <bdi dir={textDir(doingWord(member, t))}>{doingWord(member, t)}</bdi>}
          />
        );
        if (open !== member.id)
          return (
            <li key={member.id} data-member={member.id}>
              {row}
            </li>
          );
        return (
          <li key={member.id} data-member={member.id} data-open="" className="flex flex-col gap-1 rounded-2xl border border-line px-5 pb-4 pt-1">
            {row}
            <Line text={t(team.specialityLine, { value: t(member.speciality) })} />
            <Line text={t(team.styleLine, { value: t(member.style) })} />
            <Line text={t(team.toolsLine, { value: toolList(member, t) })} />
            <Line text={t(team.recordLine, { value: recordWord(member, t) })} />
            {member.doing && <Line text={t(member.doing)} />}
            <Link to={paths.member(projectId, member.id)} className={buttonVariants({ variant: "link", className: "self-start text-xs" })}>
              {t(team.openCard)}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
