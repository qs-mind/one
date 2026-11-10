// "The team now" in the side column (specimen 1, S66 to S70): each member of this tender with what it does now, in
// the core's order. A member opens its identity card in the document's place; the last row opens the team room.
// Someone working or waiting reads strong; an idle member reads muted. A temporary member says it is new here.
import { UsersIcon } from "lucide-react";
import { Link } from "react-router";
import type { Schemas } from "@/api/client";
import { paths } from "@/app/paths";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { SectionLabel } from "@/design/SectionLabel";
import { textDir } from "@/texts/language";
import { tender as texts } from "@/texts/tender";
import { type Translate, useText } from "@/texts/useText";

type Member = Schemas["TeamMember"];

const STATE = {
  working: texts.working,
  waiting: texts.waiting,
  idle: texts.idle,
  failed: texts.memberFailed,
} as const;

function line(member: Member, t: Translate): string {
  if (member.doing) return t(member.doing);
  if (member.proposed) return t(texts.proposed);
  return t(STATE[member.state as keyof typeof STATE] ?? texts.idle);
}

export function TeamNow({ projectId, members, open }: { projectId: string; members: readonly Member[]; open: string | null }) {
  const t = useText();
  return (
    <section aria-labelledby="tender-team" className="flex flex-col gap-3">
      <SectionLabel id="tender-team">{t(texts.teamTitle)}</SectionLabel>
      <ul className="flex flex-col">
        {members.map((member) => {
          const name = t(member.name);
          const doing = line(member, t);
          const busy = member.state === "working" || member.state === "waiting";
          return (
            <li key={member.id}>
              <ListRow
                render={<Link to={paths.member(projectId, member.id)} aria-current={open === member.id ? "page" : undefined} />}
                frame="plain"
                current={open === member.id}
                tone={busy ? "strong" : "muted"}
                title={<bdi dir={textDir(name)}>{name}</bdi>}
                meta={
                  <MetaLine
                    items={[
                      <span key="doing" dir={textDir(doing)}>
                        {doing}
                      </span>,
                      member.kind === "temporary" ? t(texts.temporary) : null,
                    ]}
                  />
                }
              />
            </li>
          );
        })}
        <li>
          <ListRow
            render={<Link to={paths.room(projectId)} aria-current={open === "room" ? "page" : undefined} />}
            frame="plain"
            current={open === "room"}
            leading={<UsersIcon aria-hidden className="size-4" />}
            title={t(texts.openRoom)}
          />
        </li>
      </ul>
    </section>
  );
}
