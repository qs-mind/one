// Settings, Team: the members who stay from tender to tender (GET /team/members), each with its identity and the
// record of its work in ONE. Nothing to change here (contract Q11: no route lets a member go).
import { useEffect, useState } from "react";
import { client, type Schemas } from "@/api/client";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { settings as texts } from "@/texts/settings";
import { useText } from "@/texts/useText";

function MemberRow({ member }: { member: Schemas["Member"] }) {
  const t = useText();
  const { record } = member;
  return (
    <ListRow
      frame="divided"
      size="lg"
      title={t(member.name)}
      meta={<MetaLine items={[t(member.title), member.model ? t(texts.model, { name: member.model.name }) : null]} />}
      detail={
        <MetaLine
          items={[
            t.plural(texts.tenders, record.tenders),
            record.checks_total > 0 ? t(texts.checks, { passed: record.checks_passed, total: record.checks_total }) : null,
            t(texts.costUsd, { cost: record.cost_usd }),
          ]}
        />
      }
    />
  );
}

export function Team() {
  const t = useText();
  const [members, setMembers] = useState<Schemas["Member"][] | "failed">();

  useEffect(() => {
    let live = true;
    void client
      .GET("/team/members")
      .then(({ data }) => live && setMembers(data ? data.members : "failed"))
      .catch(() => live && setMembers("failed"));
    return () => {
      live = false;
    };
  }, []);

  if (members === undefined) return <div aria-busy="true" className="min-h-14" />;
  if (members === "failed") return <p className="text-xs font-bold">{t(texts.notLoaded)}</p>;
  if (members.length === 0) return <p className="text-muted-foreground">{t(texts.noMembers)}</p>;
  return (
    <div className="flex flex-col">
      {members.map((member) => (
        <MemberRow key={member.id} member={member} />
      ))}
    </div>
  );
}
