// The live team in the top bar: who is working now (a count that opens the list, never Arabic initials, which
// would split the names by letter) and "Following Estimator" with its stop button while the view follows an agent.
import { pick, fill, t, useLanguage } from "../../i18n";
import { Popover, PopoverContent, PopoverTrigger } from "../../ui/popover";
import { useAgent, useAgents, type LiveAgent } from "./activity";
import { stateText } from "./AgentCard";
import { stopFollowing, useFollowing } from "./follow";

const button = "whitespace-nowrap rounded-md px-2 py-1 hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-ink";
const now = (a: LiveAgent) => a.state === "working" || a.state === "thinking" || a.state === "waiting";

export function TeamNow() {
  useLanguage();
  const team = useAgents().filter(now);
  if (!team.length) return null;
  return (
    <Popover>
      <PopoverTrigger className={button}>{fill(t("teamNowCount"), { n: team.length })}</PopoverTrigger>
      <PopoverContent align="end">
        <ul aria-label={t("teamNow")} className="flex flex-col gap-1">
          {team.map((a) => (
            <li key={a.id} className="flex justify-between gap-4">
              <span dir="auto" className="font-semibold">
                {pick(a.role)}
              </span>
              <span className={a.state === "waiting" ? "text-copper" : "text-slate"}>{t(stateText[a.state])}</span>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}

export function Following() {
  useLanguage();
  const id = useFollowing();
  const agent = useAgent(id ?? "");
  if (!agent) return null;
  return (
    <span className="flex shrink-0 items-center gap-1 whitespace-nowrap">
      <bdi dir="auto">{fill(t("following"), { role: pick(agent.role) })}</bdi>
      <button type="button" className={button} onClick={stopFollowing}>
        {t("stopFollowing")}
      </button>
    </span>
  );
}
