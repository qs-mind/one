// Connectors (Plan 5, Task 12): the MCP servers the engineer adds, on this computer (a command) or over the internet
// (an address). Adding one starts it to see what it can do; the core answers with a connector card, shown here on its
// own (ConnectorCard), and the Connector is saved only after the engineer says yes. A token is sent once, kept in the
// key store by the core, and never shown again. Self-contained: whoever opens Settings places it.
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { ConnectorCard } from "../chat/parts/ConnectorCard";
import type { CardAnswer } from "../chat/parts/cardKinds";
import type { CardData } from "../chat/parts/types";
import { coreLine, send } from "../core";
import { count, pick, t, type Text, texts, useLanguage } from "../i18n";

/** One Connector, as GET /connectors sends it (core/qsone/connectors/routes.py). */
export type ConnectorRow = {
  name: string;
  transport: "stdio" | "http";
  runs: string; // the command or the address, as the engineer wrote it
  enabled: boolean;
  tools: number;
  read_without_asking: boolean;
  search_tool: string | null;
  token: boolean; // a token is kept in the key store
};
type Loaded = { state: "loading" | "failed" } | { state: "ready"; connectors: ConnectorRow[] };
type Pending = CardData & { id: string };

const field = "rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink";
const primary = "rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40";
const cardOptions: Record<string, keyof typeof texts> = { yes: "addConnector", no: "dontAdd" };

function Alert({ line }: { line: Text | undefined }) {
  return line ? (
    <p role="alert" className="text-copper">
      {pick(line)}
    </p>
  ) : null;
}

export function Connectors({ onClose }: { onClose?: () => void }) {
  useLanguage();
  const title = useId();
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });
  const [failed, setFailed] = useState<Text>();
  const [added, setAdded] = useState(false);

  const load = useCallback(async () => {
    const response = await fetch("/api/connectors").catch(() => undefined);
    const body = response?.ok
      ? ((await response.json().catch(() => undefined)) as { connectors?: ConnectorRow[] } | undefined)
      : undefined;
    setLoaded(body?.connectors ? { state: "ready", connectors: body.connectors } : { state: "failed" });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(row: ConnectorRow) {
    setFailed(undefined);
    const url = `/api/connectors/${encodeURIComponent(row.name)}/enabled`;
    const response = await send(url, "PUT", { enabled: !row.enabled });
    if (!response?.ok) setFailed(await coreLine(response, texts.connectorNotSaved));
    void load();
  }

  async function remove(row: ConnectorRow) {
    setFailed(undefined);
    const response = await send(`/api/connectors/${encodeURIComponent(row.name)}`, "DELETE");
    if (!response?.ok) setFailed(await coreLine(response, texts.removeFailed));
    void load();
  }

  return (
    <section aria-labelledby={title} className="border-b border-stone px-4 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <h2 id={title} className="font-semibold">
            {t("connectors")}
          </h2>
          {onClose && (
            <button type="button" onClick={onClose} className="text-slate hover:text-ink">
              {t("close")}
            </button>
          )}
        </div>
        <p className="text-slate">{t("connectorsHelp")}</p>
        {loaded.state === "loading" && <p className="text-slate">{t("connectorsLoading")}</p>}
        {loaded.state === "failed" && (
          <div className="flex items-center gap-3">
            <p role="alert" className="text-copper">
              {t("connectorsFailed")}
            </p>
            <button type="button" onClick={() => void load()} className="rounded-md border border-ink px-4 py-2">
              {t("retry")}
            </button>
          </div>
        )}
        {loaded.state === "ready" &&
          (loaded.connectors.length === 0 ? (
            <p>{t("noConnectors")}</p>
          ) : (
            <ul className="flex flex-col gap-1">
              {loaded.connectors.map((row) => (
                <li key={row.name} className="flex items-center justify-between gap-4 rounded-md bg-stone px-3 py-2">
                  <span className="flex flex-col">
                    <span dir="auto" className="font-semibold">
                      {row.name}
                    </span>
                    <span className="flex flex-wrap gap-x-2 text-slate">
                      <span>{t(row.transport === "stdio" ? "onThisComputer" : "overInternet")}</span>
                      <span>{count("connectorTools", row.tools)}</span>
                      {row.token && <span>{t("connectorTokenKept")}</span>}
                    </span>
                    <span dir="ltr" className="text-slate">
                      {row.runs}
                    </span>
                  </span>
                  <span className="flex items-center gap-3">
                    <label className="flex items-center gap-1">
                      <input type="checkbox" checked={row.enabled} onChange={() => void toggle(row)} />
                      {t("connectorSwitchedOn")}
                    </label>
                    <button type="button" onClick={() => void remove(row)} className="text-slate hover:text-ink">
                      {t("remove")}
                    </button>
                  </span>
                </li>
              ))}
            </ul>
          ))}
        <Alert line={failed} />
        {added && <p className="text-slate">{t("connectorAdded")}</p>}
        <AddConnector
          onAdded={() => {
            setAdded(true);
            void load();
          }}
          onStarted={() => setAdded(false)}
        />
      </div>
    </section>
  );
}

function AddConnector({ onAdded, onStarted }: { onAdded: () => void; onStarted: () => void }) {
  const where = useId();
  const [name, setName] = useState("");
  const [transport, setTransport] = useState<"stdio" | "http">("stdio");
  const [command, setCommand] = useState("");
  const [url, setUrl] = useState("");
  const [token, setToken] = useState("");
  const [tokenEnv, setTokenEnv] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [card, setCard] = useState<Pending>();

  async function start(event: FormEvent) {
    event.preventDefault();
    onStarted();
    setBusy(true);
    setFailed(undefined);
    const body = {
      name: name.trim(),
      transport,
      ...(transport === "stdio" ? { command: command.trim() } : { url: url.trim() }),
      ...(token.trim() ? { token: token.trim() } : {}),
      ...(transport === "stdio" && tokenEnv.trim() ? { token_env: tokenEnv.trim() } : {}),
    };
    const response = await send("/api/connectors", "POST", body);
    setToken(""); // the token is sent once and never kept on the page, whatever the answer
    const answer = response?.ok ? ((await response.json().catch(() => undefined)) as { card?: Pending } | undefined) : undefined;
    setBusy(false);
    if (answer?.card) setCard({ ...answer.card, status: "pending" });
    else setFailed(await coreLine(response, texts.connectorNotAdded));
  }

  async function settle(choice: string, extra: CardAnswer = {}) {
    if (!card) return;
    setBusy(true);
    setFailed(undefined);
    const body = { choice, ...(extra.answers ? { answers: extra.answers } : {}) };
    const response = await send(`/api/connectors/cards/${encodeURIComponent(card.id)}`, "POST", body);
    const answer = response?.ok
      ? ((await response.json().catch(() => undefined)) as { connector?: unknown } | undefined)
      : undefined;
    setBusy(false);
    if (!answer) {
      setFailed(await coreLine(response, texts.connectorNotAdded));
      if (response?.status === 404) setCard(undefined); // the card is gone: add it again
      return;
    }
    setCard(undefined);
    if (answer.connector) {
      setName("");
      setCommand("");
      setUrl("");
      setTokenEnv("");
      onAdded();
    }
  }

  if (card) {
    return (
      <div className="flex flex-col gap-2">
        <section className="flex flex-col gap-2 rounded-md border border-copper px-3 py-2">
          <h3 className="font-semibold">{pick(card.title)}</h3>
          <p dir="auto">{pick(card.detail)}</p>
          <ConnectorCard
            card={card}
            sending={busy}
            onAnswer={(choice, extra) => void settle(choice, extra)}
            label={(option) => (cardOptions[option] ? t(cardOptions[option]) : option)}
          />
        </section>
        <Alert line={failed} />
      </div>
    );
  }

  const ready = name.trim() !== "" && (transport === "stdio" ? command.trim() : url.trim()) !== "";
  return (
    <form onSubmit={start} className="flex flex-col gap-2">
      <h3 className="font-semibold">{t("connectorAdd")}</h3>
      <label className="flex flex-col gap-1">
        <span>{t("connectorName")}</span>
        <input dir="ltr" spellCheck={false} value={name} onChange={(e) => setName(e.target.value)} className={field} />
      </label>
      <fieldset className="flex flex-col gap-1">
        <legend id={where}>{t("connectorWhere")}</legend>
        <label className="flex items-center gap-2">
          <input type="radio" name={where} checked={transport === "stdio"} onChange={() => setTransport("stdio")} />
          {t("onThisComputer")}
        </label>
        <label className="flex items-center gap-2">
          <input type="radio" name={where} checked={transport === "http"} onChange={() => setTransport("http")} />
          {t("overInternet")}
        </label>
      </fieldset>
      {transport === "stdio" ? (
        <label className="flex flex-col gap-1">
          <span>{t("connectorCommand")}</span>
          <input dir="ltr" spellCheck={false} value={command} onChange={(e) => setCommand(e.target.value)} className={field} />
        </label>
      ) : (
        <label className="flex flex-col gap-1">
          <span>{t("connectorAddress")}</span>
          <input type="url" dir="ltr" spellCheck={false} value={url} onChange={(e) => setUrl(e.target.value)} className={field} />
        </label>
      )}
      <label className="flex flex-col gap-1">
        <span>{t("connectorToken")}</span>
        <input
          type="password"
          dir="ltr"
          autoComplete="off"
          spellCheck={false}
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className={field}
        />
      </label>
      {transport === "stdio" && (
        <label className="flex flex-col gap-1">
          <span>{t("connectorTokenEnv")}</span>
          <input dir="ltr" spellCheck={false} value={tokenEnv} onChange={(e) => setTokenEnv(e.target.value)} className={field} />
        </label>
      )}
      <div>
        <button type="submit" disabled={busy || !ready} className={primary}>
          {t("connectorAdd")}
        </button>
      </div>
      {busy && <p className="text-slate">{t("connectorChecking")}</p>}
      <Alert line={failed} />
    </form>
  );
}
