// Adding a Connector (the existing POST /connectors and POST /connectors/cards/{id}): its name, where it runs (a
// command on this computer, or an address on the internet) and an optional token. "See what it can do" starts it; the
// core answers with what its tools may do, and the Connector is saved only when the engineer says Add it. The token
// is sent once and cleared from the page whatever the answer; the core keeps it in the key store.
import { type FormEvent, useId, useState } from "react";
import { addConnector, answerConnector, type ConnectorAsk, type ConnectorIn, type ConnectorTool } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { ListRow } from "@/design/ListRow";
import { notify } from "@/design/notify";
import { Button } from "@/design/ui/button";
import { Checkbox } from "@/design/ui/checkbox";
import { Input } from "@/design/ui/input";
import { RadioGroup, RadioGroupItem } from "@/design/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/design/ui/select";
import { textDir } from "@/texts/language";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

const READ = "read_without_asking"; // the card's question ids (core/qsone/connectors/hub.py)
const SEARCH = "search";
const NO_SEARCH = "none";

/** What a tool may do, in words: the strongest of its marks. */
const hint = (tool: ConnectorTool): TextPair =>
  tool.destructive ? texts.toolDeletes : tool.open_world ? texts.toolOpenWorld : tool.read_only ? texts.toolReadsOnly : texts.toolActs;

function Ask({ card, onAnswered }: { card: ConnectorAsk; onAnswered: (added: string | null, problem?: TextPair) => void }) {
  const t = useText();
  const [read, setRead] = useState(false);
  const [search, setSearch] = useState(NO_SEARCH);
  const [busy, setBusy] = useState(false);
  const { tools, questions } = card.payload;
  const asksRead = questions.some((q) => q.id === READ);
  const searchable = questions.find((q) => q.id === SEARCH)?.options?.filter((o) => o !== NO_SEARCH) ?? [];
  const items = [{ value: NO_SEARCH, label: t(texts.noSearchTool) }, ...searchable.map((name) => ({ value: name, label: name }))];

  async function answer(choice: "yes" | "no") {
    const answers: Record<string, string> = {};
    if (asksRead) answers[READ] = read ? "yes" : "no";
    if (questions.some((q) => q.id === SEARCH)) answers[SEARCH] = search;
    setBusy(true);
    const answered = await answerConnector(card.id, choice, choice === "yes" ? answers : undefined);
    setBusy(false);
    if (!answered.data) return onAnswered(null, answered.error ?? texts.connectorNotAdded);
    onAnswered(answered.data.connector?.name ?? null);
  }

  return (
    <section aria-labelledby="connector-ask" className="flex flex-col gap-4 rounded-xl border border-input px-4 py-4">
      <h3 id="connector-ask" className="font-bold">
        {t(card.title)}
      </h3>
      <p className="text-xs text-muted-foreground">
        {t(card.detail)}
      </p>
      <ul className="flex flex-col gap-2">
        {tools.map((tool) => (
          <ListRow key={tool.name} frame="boxed" title={<bdi dir={textDir(tool.name)}>{tool.name}</bdi>} meta={tool.purpose ? <bdi dir={textDir(tool.purpose)}>{tool.purpose}</bdi> : undefined} detail={t(hint(tool))} />
        ))}
      </ul>
      {asksRead ? (
        <ListRow
          frame="boxed"
          render={<label />}
          leading={<Checkbox checked={read} onCheckedChange={setRead} />}
          title={t(texts.readWithoutAsking)}
          meta={t(texts.readWithoutAskingHelp)}
        />
      ) : null}
      {searchable.length > 0 ? (
        <Field label={t(texts.useForSearch)}>
          <Select items={items} value={search} onValueChange={(value) => typeof value === "string" && setSearch(value)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {items.map((item) => (
                <SelectItem key={item.value} value={item.value}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      ) : null}
      <div className="flex flex-wrap gap-3">
        <Button loading={busy} onClick={() => void answer("yes")}>
          {t(texts.addIt)}
        </Button>
        <Button variant="outline" disabled={busy} onClick={() => void answer("no")}>
          {t(texts.dontAdd)}
        </Button>
      </div>
    </section>
  );
}

export function AddConnector({ onAdded }: { onAdded: () => void }) {
  const t = useText();
  const where = useId();
  const [form, setForm] = useState({ name: "", transport: "stdio" as ConnectorIn["transport"], runs: "", token: "" });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<TextPair>();
  const [card, setCard] = useState<ConnectorAsk>();
  const set = (part: Partial<typeof form>) => setForm((now) => ({ ...now, ...part }));

  async function start(event: FormEvent) {
    event.preventDefault();
    const name = form.name.trim();
    const runs = form.runs.trim();
    const token = form.token.trim();
    const body: ConnectorIn = { name, transport: form.transport, ...(form.transport === "stdio" ? { command: runs } : { url: runs }), ...(token ? { token } : {}) };
    set({ token: "" }); // sent once, never kept on the page
    setProblem(undefined);
    setBusy(true);
    const answer = await addConnector(body);
    setBusy(false);
    if (answer.data) setCard(answer.data.card);
    else setProblem(answer.error ?? texts.connectorNotAdded);
  }

  function answered(added: string | null, words?: TextPair) {
    setCard(undefined);
    if (words) return setProblem(words);
    if (added === null) return;
    setForm({ name: "", transport: "stdio", runs: "", token: "" });
    notify(t(texts.connectorAdded, { name: added }));
    onAdded();
  }

  const problemLine = problem ? (
    <p role="alert" className="text-xs font-bold">
      {t(problem)}
    </p>
  ) : null;
  if (card)
    return (
      <>
        <Ask card={card} onAnswered={answered} />
        {problemLine}
      </>
    );
  const ready = form.name.trim() !== "" && form.runs.trim() !== "";
  return (
    <form onSubmit={(event) => void start(event)} aria-labelledby={`${where}-title`} className="flex flex-col gap-4">
      <h2 id={`${where}-title`} className="text-lg font-bold">
        {t(texts.addConnector)}
      </h2>
      <Field label={t(texts.connectorName)}>
        <Input dir="ltr" autoComplete="off" spellCheck={false} value={form.name} onChange={(event) => set({ name: event.target.value })} />
      </Field>
      <div className="flex flex-col gap-2">
        <p id={`${where}-where`}>{t(texts.connectorWhere)}</p>
        <RadioGroup aria-labelledby={`${where}-where`} value={form.transport} onValueChange={(next) => (next === "stdio" || next === "http") && set({ transport: next })} className="gap-2">
          {(["stdio", "http"] as const).map((transport) => (
            <ListRow
              key={transport}
              frame="boxed"
              render={<label />}
              current={form.transport === transport}
              leading={<RadioGroupItem value={transport} />}
              title={t(transport === "stdio" ? texts.onThisComputer : texts.overInternet)}
            />
          ))}
        </RadioGroup>
      </div>
      <Field label={t(form.transport === "stdio" ? texts.connectorCommand : texts.connectorAddress)}>
        <Input dir="ltr" autoComplete="off" spellCheck={false} value={form.runs} onChange={(event) => set({ runs: event.target.value })} />
      </Field>
      <Field label={t(texts.connectorToken)}>
        <Input type="password" dir="ltr" autoComplete="off" spellCheck={false} value={form.token} onChange={(event) => set({ token: event.target.value })} />
      </Field>
      <div className="flex flex-wrap items-center gap-4">
        <Button type="submit" loading={busy} disabled={!ready}>
          {t(texts.connectorStart)}
        </Button>
        <p aria-live="polite" className="text-xs text-muted-foreground">
          {busy ? t(texts.connectorChecking) : null}
        </p>
      </div>
      {problemLine}
    </form>
  );
}
