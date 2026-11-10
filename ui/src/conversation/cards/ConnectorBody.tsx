// A Connector being added (kind "connector"): what it can do, tool by tool, with what its server says of each (the
// server's own text, shown as data), and the engineer's two choices: let its reading tools run without asking, and
// use one of them for web search. "no" takes nothing.
import { useState } from "react";
import { Field } from "@/design/Field";
import { Checkbox } from "@/design/ui/checkbox";
import { Label } from "@/design/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { cards } from "@/texts/cards";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import { ConfirmationAction, ConfirmationActions } from "../ai/confirmation";
import type { CardAnswer, CardData, ConnectorTool } from "../parts";

const REFUSE = "no"; // takes nothing (core/qsone/engine/types.py)
const READ = "read_without_asking"; // the card's question ids (core/qsone/connectors/hub.py)
const SEARCH = "search";
const NO_SEARCH = "none";

/** What a tool may do, in words: the strongest of its hints. */
const hint = (tool: ConnectorTool) =>
  tool.destructive ? cards.toolDeletes : tool.open_world ? cards.toolOpenWorld : tool.read_only ? cards.toolReadsOnly : cards.toolActs;

type ConnectorBodyProps = {
  card: CardData;
  open: boolean;
  busy: boolean;
  label: (option: string) => string;
  onAnswer: (choice: string, extra?: CardAnswer) => void;
};

export function ConnectorBody({ card, open, busy, label, onAnswer }: ConnectorBodyProps) {
  const t = useText();
  const [read, setRead] = useState(false);
  const [search, setSearch] = useState(NO_SEARCH);
  const tools = card.payload?.tools ?? [];
  const questions = card.payload?.questions ?? [];
  const asksRead = questions.some((q) => q.id === READ);
  const asksSearch = questions.some((q) => q.id === SEARCH);
  const searchable = questions.find((q) => q.id === SEARCH)?.options?.filter((o) => o !== NO_SEARCH) ?? [];
  const items = [{ value: NO_SEARCH, label: t(cards.noSearchTool) }, ...searchable.map((name) => ({ value: name, label: name }))];

  const send = (choice: string) => {
    if (choice === REFUSE) return onAnswer(choice);
    const answers: Record<string, string> = {};
    if (asksRead) answers[READ] = read ? "yes" : "no";
    if (asksSearch) answers[SEARCH] = search;
    onAnswer(choice, { answers });
  };

  return (
    <div className="flex flex-col gap-4">
      <ul className="flex flex-col gap-2">
        {tools.map((tool) => (
          <li key={tool.name} className="flex flex-col rounded-lg bg-muted px-4 py-2">
            <span dir={textDir(tool.name)} className="font-bold">
              {tool.name}
            </span>
            {tool.purpose && <span dir={textDir(tool.purpose)}>{tool.purpose}</span>}
            <span className="text-xs text-muted-foreground">{t(hint(tool))}</span>
          </li>
        ))}
      </ul>
      {open && asksRead && (
        <div className="flex flex-col gap-1">
          <Label className="flex items-center gap-3">
            <Checkbox checked={read} disabled={busy} onCheckedChange={(on) => setRead(Boolean(on))} />
            {t(cards.readWithoutAsking)}
          </Label>
          <p className="text-xs text-muted-foreground">{t(cards.readWithoutAskingHelp)}</p>
        </div>
      )}
      {open && searchable.length > 0 && (
        <Field label={t(cards.useForSearch)}>
          <Select items={items} value={search} disabled={busy} onValueChange={(next) => setSearch(String(next))}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {items.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  <span dir={textDir(item.label)}>{item.label}</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}
      <ConfirmationActions className="mt-1">
        {card.options.map((option) => (
          <ConfirmationAction key={option} variant={option === REFUSE ? "outline" : "default"} disabled={busy} onClick={() => send(option)}>
            {label(option)}
          </ConfirmationAction>
        ))}
      </ConfirmationActions>
    </div>
  );
}
