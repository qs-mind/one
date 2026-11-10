// "Waiting for you": every thing the engineer must answer, in every tender and in the Home conversation, oldest
// first, as the core lists them. An item opens where it is answered: its tender (with the id of the part that shows
// it, for the thread to find), or the Home conversation below. No copper here: these are Stone rows (4.23).
import { Link } from "react-router";
import type { Schemas } from "@/api/client";
import { ListRow } from "@/design/ListRow";
import { MetaLine } from "@/design/MetaLine";
import { SectionLabel } from "@/design/SectionLabel";
import { paths } from "@/app/paths";
import { home } from "@/texts/home";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";

type Item = Schemas["WaitingItem"];

type WaitingProps = {
  items: readonly Item[];
  /** The tender's name as its row shows it, by project id. */
  nameOf: (projectId: string) => string | null;
  /** Brings the Home conversation into view, for an item that waits there. */
  onHomeConversation: () => void;
};

export function Waiting({ items, nameOf, onHomeConversation }: WaitingProps) {
  const t = useText();
  if (items.length === 0) return null;
  return (
    <section aria-labelledby="home-waiting" className="flex flex-col gap-3">
      <SectionLabel id="home-waiting">{t(home.waiting)}</SectionLabel>
      {items.map((item) => {
        const where = item.project_id ? nameOf(item.project_id) : t(home.homeConversation);
        return (
          <ListRow
            key={`${item.kind}:${item.id}`}
            frame="panel"
            tone="strong"
            render={
              item.project_id ? (
                <Link to={paths.tender(item.project_id)} state={{ part: item.id }} />
              ) : (
                <button type="button" onClick={onHomeConversation} />
              )
            }
            title={t(item.title)}
            detail={item.text ? <bdi dir={textDir(item.text)}>{item.text}</bdi> : undefined}
            meta={
              <MetaLine
                items={[
                  where && <bdi dir={textDir(where)}>{where}</bdi>,
                  item.blocking && t(home.workStopped),
                ]}
              />
            }
          />
        );
      })}
    </section>
  );
}
