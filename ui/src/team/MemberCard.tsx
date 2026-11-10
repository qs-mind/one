// A member's identity card (contract routes 15-16): its QS title, kind, speciality, working style, tools and model,
// and the record of its real work in ONE (tenders, Checking QS results, paid cost). A temporary member reads "first
// tender with you". Nothing here is invented: every line comes from the member the core sends.
import type { ReactNode } from "react";
import { Link } from "react-router";
import { paths } from "@/app/paths";
import { MetaLine } from "@/design/MetaLine";
import { SectionLabel } from "@/design/SectionLabel";
import { Button, buttonVariants } from "@/design/ui/button";
import { common } from "@/texts/common";
import { formatNumber } from "@/texts/format";
import { textDir } from "@/texts/language";
import { team as texts } from "@/texts/team";
import { useText } from "@/texts/useText";
import { doingWord, kindWord, recordWord } from "./MemberList";
import { type TeamMember, useTeam } from "./useTeam";

function Part({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <SectionLabel>{label}</SectionLabel>
      {children}
    </section>
  );
}

function Said({ text, className }: { text: string; className?: string }) {
  return (
    <p dir={textDir(text)} className={className}>
      {text}
    </p>
  );
}

function Card({ projectId, member }: { projectId: string; member: TeamMember }) {
  const t = useText();
  const name = t(member.name);
  const { record, model } = member;
  const cost = formatNumber(Number(record.cost_usd), t.lang, { style: "currency", currency: "USD" });
  const kind = [kindWord(member, t), member.role === "checker" && t(texts.independent), member.proposed && t(texts.proposed)];
  return (
    <article aria-label={t(texts.cardLabel)} className="flex flex-col gap-10">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-bold">
          <bdi dir={textDir(name)}>{name}</bdi>
        </h1>
        <Said text={t(member.title)} className="text-lg text-muted-foreground" />
        <MetaLine items={kind} className="text-xs text-muted-foreground" />
      </header>

      {(member.doing || member.state === "failed" || member.state === "working") && (
        <Part label={t(texts.now)}>
          <Said text={member.doing || member.state === "failed" ? doingWord(member, t) : t(texts.working)} />
        </Part>
      )}
      <Part label={t(texts.speciality)}>
        <Said text={t(member.speciality)} />
      </Part>
      <Part label={t(texts.style)}>
        <Said text={t(member.style)} />
      </Part>
      <Part label={t(texts.tools)}>
        {member.tools.length === 0 ? (
          <p className="text-muted-foreground">{t(texts.noTools)}</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {member.tools.map((tool) => (
              <li key={tool.name} dir={textDir(t(tool.title))}>
                {t(tool.title)}
              </li>
            ))}
          </ul>
        )}
      </Part>
      <Part label={t(texts.model)}>
        {model ? (
          <div className="flex flex-col gap-1">
            <Said text={t(texts.modelBy, { name: model.name, provider: model.provider })} />
            <p className="text-xs text-muted-foreground">{t(model.on_device ? texts.onDevice : texts.offDevice)}</p>
          </div>
        ) : (
          <p className="text-muted-foreground">{t(texts.noModel)}</p>
        )}
      </Part>
      <Part label={t(texts.record)}>
        <ul className="flex flex-col gap-2">
          <li>{recordWord(member, t)}</li>
          <li>
            {record.checks_total === 0
              ? t(texts.checksNone)
              : t(texts.checks, { passed: record.checks_passed, total: record.checks_total })}
          </li>
          <li>{t(texts.cost, { cost })}</li>
        </ul>
      </Part>

      <Link to={paths.room(projectId)} className={buttonVariants({ variant: "link", className: "self-start" })}>
        {t(texts.backToRoom)}
      </Link>
    </article>
  );
}

export function MemberCard({ projectId, memberId }: { projectId: string; memberId: string }) {
  const t = useText();
  const { team, reload } = useTeam(projectId);
  const member = team.state === "ready" ? team.members.find((it) => it.id === memberId) : undefined;

  return (
    <div data-place="member" data-member={memberId} className="mx-auto w-full max-w-190 px-(--gutter) pt-7 pb-12">
      {team.state === "loading" && <p className="text-muted-foreground">{t(common.loading)}</p>}
      {team.state === "failed" && (
        <div className="flex flex-col items-start gap-4">
          <p>{team.error ? t(team.error) : t(texts.cardFailed)}</p>
          <Button variant="outline" onClick={reload}>
            {t(texts.tryAgain)}
          </Button>
        </div>
      )}
      {team.state === "ready" &&
        (member ? (
          <Card projectId={projectId} member={member} />
        ) : (
          <div className="flex flex-col items-start gap-4">
            <p>{t(texts.notInTender)}</p>
            <Link to={paths.room(projectId)} className={buttonVariants({ variant: "link" })}>
              {t(texts.backToRoom)}
            </Link>
          </div>
        ))}
    </div>
  );
}
