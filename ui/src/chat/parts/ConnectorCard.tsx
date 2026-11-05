// A connector card (Plan 5, Task 12): what a Connector being added can do, tool by tool, each with what its server
// says of it in words, and the engineer's two choices: let its reading tools run without asking, and use one of them
// for web search. The tool names and purposes are the server's own text, shown as data (dir="auto"). It answers in the
// chat (ApprovalCard posts it) and in Settings (Connectors posts it to the Connector's own card route).
import { useId, useState } from "react";
import { t, type texts } from "../../i18n";
import type { CardKindProps } from "./cardKinds";
import type { ConnectorTool } from "./types";

const REFUSE = "no"; // takes nothing (core/qsone/engine/types.py)
const READ = "read_without_asking"; // the card's question ids (core/qsone/connectors/hub.py)
const SEARCH = "search";
const NO_SEARCH = "none";

/** What a tool may do, in words: the strongest of its hints. */
function hint(tool: ConnectorTool): keyof typeof texts {
  if (tool.destructive) return "toolDeletes";
  if (tool.open_world) return "toolOpenWorld";
  return tool.read_only ? "toolReadsOnly" : "toolActs";
}

export function ConnectorCard({ card, onAnswer, sending, label }: CardKindProps) {
  const ids = useId();
  const [read, setRead] = useState(false);
  const [search, setSearch] = useState(NO_SEARCH);
  const tools = card.payload?.tools ?? [];
  const questions = card.payload?.questions ?? [];
  const searchable = questions.find((q) => q.id === SEARCH)?.options?.filter((o) => o !== NO_SEARCH) ?? [];
  const asksRead = questions.some((q) => q.id === READ);
  const open = card.status !== "settled" && card.status !== "withdrawn";

  function send(choice: string) {
    if (choice === REFUSE) return onAnswer(choice);
    const answers: Record<string, string> = {};
    if (asksRead) answers[READ] = read ? "yes" : "no";
    if (questions.some((q) => q.id === SEARCH)) answers[SEARCH] = search;
    onAnswer(choice, { answers });
  }

  return (
    <>
      <ul className="flex flex-col gap-2">
        {tools.map((tool) => (
          <li key={tool.name} className="flex flex-col rounded-lg bg-stone px-4 py-2">
            <span dir="auto" className="font-semibold">
              {tool.name}
            </span>
            {tool.purpose && <span dir="auto">{tool.purpose}</span>}
            <span className="text-slate">{t(hint(tool))}</span>
          </li>
        ))}
      </ul>
      {open && (
        <fieldset className="flex flex-col gap-2" disabled={sending}>
          {asksRead && (
            <div className="flex flex-col">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={read} onChange={(e) => setRead(e.target.checked)} />
                {t("readWithoutAsking")}
              </label>
              <p className="text-slate">{t("readWithoutAskingHelp")}</p>
            </div>
          )}
          {searchable.length > 0 && (
            <label className="flex flex-col gap-1">
              <span id={`${ids}-search`}>{t("useForSearch")}</span>
              <select
                aria-labelledby={`${ids}-search`}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="rounded-md border border-slate bg-paper px-3 py-2"
              >
                <option value={NO_SEARCH}>{t("noSearchTool")}</option>
                {searchable.map((name) => (
                  <option key={name} value={name} dir="auto">
                    {name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="flex flex-wrap gap-2">
            {card.options.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => send(option)}
                className={`rounded-lg px-4 py-2 disabled:opacity-40 ${option === REFUSE ? "border border-ink" : "bg-ink text-paper"}`}
              >
                {label(option)}
              </button>
            ))}
          </div>
        </fieldset>
      )}
    </>
  );
}
