// AI settings: the AI Connectors (the Claude key, Standard Links, the engineer's own Claude Code), which model does
// each job, prices One does not know, and the Spending Caps. The engineer picks every model; nothing here is fixed.
// No Save or Check button: a key checks itself, a choice saves when it is made, an amount after a pause in typing
// or on leaving its field, a file path on leaving its field (never a half-typed path), each with its quiet line.
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { Feedback, secondary } from "../firstlaunch/parts";
import { fill, pick, t, type Text, texts, useLanguage } from "../i18n";
import { AutoHeight } from "../ui/AutoHeight";
import { looksLikeAmount, SaveNote, useSaving } from "../ui/live";
import { AiKey } from "./AiKey";

export type Role = "lead" | "checker" | "specialist" | "quick";
export type Choice = { connector: string; model: string };
/** How hard the Lead QS thinks; picked in the message box. */
export type Effort = "low" | "medium" | "high";
export type ModelCard = Choice & {
  name: string;
  provider: string;
  images: boolean;
  tools: boolean;
  context: number | null;
  price_in: string | null; // USD per million tokens, exact decimal text
  price_out: string | null;
  price_source: string | null;
  on_device: boolean;
  subscription: boolean;
  efforts?: Effort[]; // the levels it accepts; none: the message box shows no effort
  effort_default?: Effort | null; // its provider's own level when none is sent, when known
};
export type ConnectorInfo = {
  id: string; // "anthropic" | "standard:<id>" | "claude-code"
  kind: "model" | "agent";
  name: string;
  provider: string;
  on_device: boolean;
  key_set: boolean;
  error: Text | null; // why its models could not be listed just now
};
type Roles = Partial<Record<Role, Choice>>;
type Settings = {
  connectors: ConnectorInfo[];
  sheet: ModelCard[];
  roles: Roles;
  defaults: Roles;
  effort?: Effort | null; // the message box's last effort; none: the provider's own
  key_store?: "system" | "file"; // "file": this computer has no key store, so the core keeps keys in a file
};
type Loaded = { state: "loading" | "failed" } | { state: "ready"; settings: Settings };

const roleTexts = { lead: "roleLead", checker: "roleChecker", specialist: "roleSpecialist", quick: "roleQuick" } as const;
const roleOrder: Role[] = ["lead", "checker", "specialist", "quick"];

const field = "rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink";
const primary = "rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40";

/** One select value per model: the same model always gives the same text. */
export const keyOf = (choice: Choice) => JSON.stringify({ connector: choice.connector, model: choice.model });

/** Something can answer a Brief: a saved key, a Standard Link (a local one has no key) or Claude Code. */
function anyConnected(connectors: ConnectorInfo[]): boolean {
  return connectors.some((c) => c.key_set || c.kind === "agent" || c.id.startsWith("standard:"));
}

/** The AI settings from the core; `connected` is undefined until they load (or when they cannot). */
export function useAiSettings() {
  const [loaded, setLoaded] = useState<Loaded>({ state: "loading" });

  const load = useCallback(async () => {
    setLoaded((now) => (now.state === "ready" ? now : { state: "loading" })); // a reload keeps what is shown
    const response = await api("/settings/ai").catch(() => undefined);
    const settings = response?.ok ? ((await response.json().catch(() => undefined)) as Settings | undefined) : undefined;
    setLoaded(settings ? { state: "ready", settings } : { state: "failed" });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const setRoles = useCallback((roles: Roles) => {
    setLoaded((now) => (now.state === "ready" ? { state: "ready", settings: { ...now.settings, roles } } : now));
  }, []);

  /** The message box's pick for the next Brief: the Lead QS's model and effort. Shown here at once (`picked` is what
   * the box sends); the core saves them when a message goes with them. Until then the core's own choice stands. */
  const [picked, setPicked] = useState<{ lead?: Choice; effort?: Effort }>({});
  const pick = useCallback((next: { lead?: Choice; effort?: Effort }) => {
    setPicked((now) => ({ ...now, ...next }));
    setLoaded((now) => {
      if (now.state !== "ready") return now;
      const { roles, effort } = now.settings;
      const lead = next.lead ? { ...roles, lead: next.lead } : roles;
      return { state: "ready", settings: { ...now.settings, roles: lead, effort: next.effort ?? effort } };
    });
  }, []);

  const connected = loaded.state === "ready" ? anyConnected(loaded.settings.connectors) : undefined;
  return { loaded, load, setRoles, pick, picked, connected };
}

export type Ai = ReturnType<typeof useAiSettings>;

function Alert({ line }: { line: Text | undefined }) {
  return line ? (
    <p role="alert" className="text-copper">
      {pick(line)}
    </p>
  ) : null;
}

export function AiSettings({ ai, onClose }: { ai: Ai; onClose?: () => void }) {
  useLanguage();
  const title = useId();
  const { loaded } = ai;

  return (
    <section aria-labelledby={title} className="border-b border-stone px-4 py-4">
      {/* eases to its new height (loading, then the settings; a link added or taken out), so nothing under it jumps */}
      <AutoHeight className="mx-auto flex max-w-2xl flex-col gap-6">
        <div className="flex items-center justify-between gap-4">
          <h2 id={title} className="font-semibold">
            {t("aiTitle")}
          </h2>
          {onClose && (
            <button type="button" onClick={onClose} className="text-slate hover:text-ink">
              {t("close")}
            </button>
          )}
        </div>
        {loaded.state === "loading" && <p className="text-slate">{t("aiLoading")}</p>}
        {loaded.state === "failed" && (
          <div className="flex items-center gap-3">
            <p role="alert" className="text-copper">
              {t("aiFailed")}
            </p>
            <button type="button" onClick={() => void ai.load()} className="rounded-md border border-ink px-4 py-2">
              {t("retry")}
            </button>
          </div>
        )}
        {loaded.state === "ready" && (
          <>
            {!ai.connected && <p>{t("noAiYet")}</p>}
            <ClaudeKey settings={loaded.settings} onSaved={() => void ai.load()} />
            <StandardLinks connectors={loaded.settings.connectors} onChanged={() => void ai.load()} />
            <ClaudeCode connectors={loaded.settings.connectors} onChanged={() => void ai.load()} />
            {ai.connected && (
              <>
                <RoleModels settings={loaded.settings} onSaved={ai.setRoles} />
                <PriceForm sheet={loaded.settings.sheet} onSaved={() => void ai.load()} />
                <div className="flex flex-col gap-3">
                  <h3 className="font-semibold">{t("caps")}</h3>
                  <p className="text-slate">{t("capsHelp")}</p>
                  <CapsForm />
                </div>
              </>
            )}
          </>
        )}
      </AutoHeight>
    </section>
  );
}

function ClaudeKey({ settings, onSaved }: { settings: Settings; onSaved: () => void }) {
  const saved = settings.connectors.some((c) => c.id === "anthropic" && c.key_set);
  return (
    <div className="flex flex-col gap-1">
      <h3 className="font-semibold">{t("aiKey")}</h3>
      {saved && <p className="text-slate">{t("claudeKeySaved")}</p>}
      {settings.key_store === "file" && <p className="text-slate">{t("keyStoreFile")}</p>}
      <Alert line={settings.connectors.find((c) => c.id === "anthropic" && c.key_set)?.error ?? undefined} />
      <AiKey onChecked={onSaved} />
    </div>
  );
}

function StandardLinks({ connectors, onChanged }: { connectors: ConnectorInfo[]; onChanged: () => void }) {
  const links = connectors.filter((c) => c.id.startsWith("standard:"));
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [key, setKey] = useState("");
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState<Text>();

  async function add(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFailed(undefined);
    const body = { name: name.trim(), base_url: baseUrl.trim(), ...(key.trim() ? { key: key.trim() } : {}) };
    const response = await send("/settings/ai/standard", "POST", body);
    setSaving(false);
    setKey(""); // the key is sent once and never kept on the page, whatever the answer
    if (response?.ok) {
      setName("");
      setBaseUrl("");
      onChanged();
    } else {
      // a refused address comes back as technical detail, so the screen says it in its own words
      setFailed(await coreLine(response, response?.status === 422 ? texts.providerUrlRefused : texts.providerNotAdded));
    }
  }

  async function remove(id: string) {
    setFailed(undefined);
    const response = await send(`/settings/ai/standard/${encodeURIComponent(id)}`, "DELETE");
    if (response?.ok) onChanged();
    else setFailed(await coreLine(response, texts.removeFailed));
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-semibold">{t("standardLink")}</h3>
      <p className="text-slate">{t("standardLinkHelp")}</p>
      {links.length > 0 && (
        <ul className="flex flex-col gap-1">
          {links.map((link) => (
            <li key={link.id} className="flex items-center justify-between gap-4 rounded-md bg-stone px-3 py-2">
              <span className="flex flex-wrap gap-x-2">
                <span dir="auto">{link.name}</span>
                {link.on_device && <span className="text-slate">{t("onDevice")}</span>}
                {link.error && <span className="text-copper">{pick(link.error)}</span>}
              </span>
              <button type="button" onClick={() => void remove(link.id)} className="text-slate hover:text-ink">
                {t("remove")}
              </button>
            </li>
          ))}
        </ul>
      )}
      <form onSubmit={add} className="flex flex-col gap-2">
        <label className="flex flex-col gap-1">
          <span>{t("providerName")}</span>
          <input dir="auto" value={name} onChange={(event) => setName(event.target.value)} className={field} />
        </label>
        <label className="flex flex-col gap-1">
          <span>{t("baseUrl")}</span>
          <input
            type="url"
            dir="ltr"
            spellCheck={false}
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            className={field}
          />
        </label>
        <label className="flex flex-col gap-1">
          <span>{t("providerKey")}</span>
          <input
            type="password"
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            value={key}
            onChange={(event) => setKey(event.target.value)}
            className={field}
          />
        </label>
        <div>
          <button type="submit" disabled={saving || !name.trim() || !baseUrl.trim()} className={primary}>
            {t("addProvider")}
          </button>
        </div>
      </form>
      <Alert line={failed} />
    </div>
  );
}

type ClaudeCodeStatus = {
  installed: boolean;
  compatible: boolean;
  signed_in: boolean | null;
  version: string | null;
  code: string | null; // the name of a core text, e.g. "CLAUDE_CODE_TOO_OLD"
  models: string[];
};

const statusTexts: Record<string, keyof typeof texts> = {
  CLAUDE_CODE_MISSING: "claudeCodeMissing",
  CLAUDE_CODE_TOO_OLD: "claudeCodeTooOld",
  CLAUDE_CODE_SHIM: "claudeCodeShim",
  CLAUDE_CODE_SIGNED_OUT: "claudeCodeSignedOut",
};

function statusLine(status: ClaudeCodeStatus): string {
  if (status.code) return t(statusTexts[status.code] ?? "claudeCodeCheckFailed");
  if (status.signed_in === false) return t("claudeCodeSignedOut");
  return fill(t("claudeCodeReady"), { version: status.version ?? "" });
}

/** The Subscription Link. Checked when it opens switched on, when it is switched on, and when its file changes: once
 * each, no timer, no polling. The file is saved on leaving its field (or Enter), never while it is typed. */
function ClaudeCode({ connectors, onChanged }: { connectors: ConnectorInfo[]; onChanged: () => void }) {
  const on = connectors.some((c) => c.id === "claude-code");
  const [path, setPath] = useState("");
  const kept = useRef(""); // the file last saved from this field
  const [status, setStatus] = useState<"checking" | ClaudeCodeStatus | Text>();
  const [switchedOn, setSwitchedOn] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const checks = useRef(0); // only the latest check's answer shows

  async function save(nextOn: boolean): Promise<boolean> {
    setFailed(undefined);
    const response = await send("/settings/ai/claude-code", "PUT", { path: path.trim() || null, on: nextOn });
    if (!response?.ok) setFailed(await coreLine(response, texts.claudeCodeNotSaved));
    else kept.current = path.trim();
    return response?.ok === true;
  }

  const check = useCallback(async () => {
    const mine = ++checks.current;
    setStatus("checking");
    const response = await api("/settings/ai/claude-code").catch(() => undefined);
    const answer = response?.ok
      ? ((await response.json()) as ClaudeCodeStatus)
      : await coreLine(response, texts.claudeCodeCheckFailed);
    if (mine === checks.current) setStatus(answer);
  }, []);

  const opened = useRef(on);
  useEffect(() => {
    if (opened.current) void check(); // switched on already: say how it is now
  }, [check]);

  async function leave() {
    if (path.trim() === kept.current) return;
    if (await save(on)) void check(); // the file the engineer picked
  }

  async function toggle() {
    if (await save(!on)) {
      setSwitchedOn(!on);
      onChanged();
      if (!on) void check();
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-semibold">{t("claudeCode")}</h3>
      <p className="text-slate">{t("claudeCodeHelp")}</p>
      <label className="flex flex-col gap-1">
        <span>{t("claudeCodePath")}</span>
        <input
          dir="ltr"
          spellCheck={false}
          value={path}
          onChange={(event) => setPath(event.target.value)}
          onBlur={() => void leave()}
          onKeyDown={(event) => event.key === "Enter" && void leave()}
          className={field}
        />
      </label>
      <label className="flex items-center gap-2 self-start">
        <input type="checkbox" checked={on} onChange={() => void toggle()} className="accent-ink" />
        <span>{t("useClaudeCode")}</span>
      </label>
      <div className="min-h-7">
        {failed ? (
          <Feedback state="failed">{pick(failed)}</Feedback>
        ) : (
          status && <StatusLine status={status} onAgain={() => void check()} />
        )}
      </div>
      {(on || switchedOn) && <p className="text-slate">{t("claudeCodeCopy")}</p>}
    </div>
  );
}

/** How Claude Code is now. A failed line ends "then try again" (or "pick it", the file field above): its Try again
 * checks once more, as no timer does. */
function StatusLine({ status, onAgain }: { status: "checking" | ClaudeCodeStatus | Text; onAgain: () => void }) {
  if (status === "checking") return <Feedback state="busy">{t("claudeCodeChecking")}</Feedback>;
  const ready = !("en" in status) && !status.code && status.signed_in !== false;
  if (ready) return <Feedback state="done">{statusLine(status)}</Feedback>;
  return (
    <div className="flex flex-col gap-2">
      <Feedback state="failed">{"en" in status ? pick(status) : statusLine(status)}</Feedback>
      <button type="button" onClick={onAgain} className={`${secondary} self-start`}>
        {t("tryAgain")}
      </button>
    </div>
  );
}

function priceText(card: ModelCard): string {
  if (card.on_device) return t("onDevice");
  if (card.price_in == null || card.price_out == null) return t("priceUnknown");
  const price = fill(t("pricePerMillion"), { in: card.price_in, out: card.price_out });
  return card.price_source ? `${price} · ${fill(t("priceSource"), { source: card.price_source })}` : price;
}

/** One select per role, from the Model Data Sheet; the Recommended Setting is marked. */
function RoleModels({ settings, onSaved }: { settings: Settings; onSaved: (roles: Roles) => void }) {
  const { saving, n, now } = useSaving();
  const { sheet, roles, defaults } = settings;

  function choose(role: Role, value: string) {
    const card = sheet.find((item) => keyOf(item) === value);
    if (!card) return;
    const next = { ...roles, [role]: { connector: card.connector, model: card.model } };
    void now(async () => {
      const response = await send("/settings/ai/roles", "PUT", next);
      if (!response?.ok) return coreLine(response, texts.roleNotSaved);
      onSaved(((await response.json().catch(() => undefined)) as Roles | undefined) ?? next);
      return null;
    });
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="font-semibold">{t("roles")}</h3>
      {sheet.length === 0 ? (
        <p className="text-slate">{t("noModels")}</p>
      ) : (
        roleOrder.map((role) => {
          const current = roles[role];
          const value = current ? keyOf(current) : "";
          const chosen = sheet.find((card) => keyOf(card) === value);
          const recommended = defaults[role] ? keyOf(defaults[role]) : undefined;
          return (
            <label key={role} className="flex flex-col gap-1">
              <span>{t(roleTexts[role])}</span>
              <select
                dir="ltr"
                value={value}
                disabled={saving.state === "busy"}
                onChange={(event) => choose(role, event.target.value)}
                className={field}
              >
                {!chosen && <option value={value}>{current?.model ?? ""}</option>}
                {sheet.map((card) => {
                  const key = keyOf(card);
                  return (
                    <option key={key} value={key}>
                      {`${card.name} · ${priceText(card)}${key === recommended ? ` · ${t("recommended")}` : ""}`}
                    </option>
                  );
                })}
              </select>
              {chosen?.subscription && <span className="text-slate">{t("equivalentCost")}</span>}
            </label>
          );
        })
      )}
      <SaveNote saving={saving} n={n} />
    </div>
  );
}

/** Prices for models genai-prices does not know; the core keeps them with "engineer, <date>" as the source. Saved once
 * both amounts are typed: after a pause when both are whole amounts, or on leaving a field. */
function PriceForm({ sheet, onSaved }: { sheet: ModelCard[]; onSaved: () => void }) {
  const unknown = sheet.filter((card) => !card.on_device && (card.price_in == null || card.price_out == null));
  const [picked, setPicked] = useState<string>();
  const [priceIn, setPriceIn] = useState("");
  const [priceOut, setPriceOut] = useState("");
  const { saving, n, later, drop, flush } = useSaving();
  const title = useId();
  if (unknown.length === 0) return null;
  const card = unknown.find((item) => keyOf(item) === picked) ?? unknown[0]!;

  function changed(next: { in: string; out: string }) {
    setPriceIn(next.in);
    setPriceOut(next.out);
    if (!next.in.trim() || !next.out.trim()) return drop(); // nothing to save yet
    const body = { connector: card.connector, model: card.model, in: next.in.trim(), out: next.out.trim() };
    later(async () => {
      const response = await send("/settings/ai/prices", "PUT", body);
      if (!response?.ok) return coreLine(response, texts.priceNotSaved);
      setPriceIn("");
      setPriceOut("");
      onSaved();
      return null;
    }, looksLikeAmount(next.in) && looksLikeAmount(next.out));
  }

  return (
    <form onSubmit={(event) => event.preventDefault()} onBlur={() => void flush()} aria-labelledby={title} className="flex flex-col gap-2">
      <h3 id={title} className="font-semibold">
        {t("enterPrice")}
      </h3>
      <p className="text-slate">{t("enterPriceHelp")}</p>
      <label className="flex flex-col gap-1">
        <span>{t("priceModel")}</span>
        <select dir="ltr" value={keyOf(card)} onChange={(event) => setPicked(event.target.value)} className={field}>
          {unknown.map((item) => (
            <option key={keyOf(item)} value={keyOf(item)}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <Amount label={t("priceIn")} value={priceIn} onChange={(value) => changed({ in: value, out: priceOut })} />
      <Amount label={t("priceOut")} value={priceOut} onChange={(value) => changed({ in: priceIn, out: value })} />
      <SaveNote saving={saving} n={n} />
    </form>
  );
}

/** An amount typed as exact text, never turned into a float on the way; `hint` is a line under it. */
function Amount({
  label,
  value,
  onChange,
  hint,
  invalid = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  /** The core refused it: its border turns Copper until it saves. */
  invalid?: boolean;
}) {
  const hintId = useId();
  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1">
        <span>{label}</span>
        <input
          type="text"
          inputMode="decimal"
          dir="ltr"
          spellCheck={false}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={hint ? hintId : undefined}
          aria-invalid={invalid || undefined}
          className={`${field} ${invalid ? "border-copper" : ""}`}
        />
      </label>
      {hint && (
        <span id={hintId} className="text-slate">
          {hint}
        </span>
      )}
    </div>
  );
}

type Amounts = { brief: string; day: string; month: string; budget_above: string };
type Caps = Amounts & { subscription_stops: boolean };
/** GET and PUT /settings/ai/caps: the caps in force and the Recommended Setting, in USD as exact text. */
type CapsAnswer = { caps: Caps; recommended: Caps };
const capFields = [
  ["brief", "capBrief"],
  ["day", "capDay"],
  ["month", "capMonth"],
  ["budget_above", "budgetAbove"],
] as const;

/** The three Spending Caps and the Brief Budget line, in USD, each saved as it is typed: after a pause when it is a
 * whole amount, or on leaving its field. Also used by a cap card's "Raise the cap", whose `go` button goes on once
 * the last change is saved. */
export function CapsForm({ go }: { go?: { label: string; onGo: () => void } }) {
  useLanguage();
  const [caps, setCaps] = useState<Amounts>();
  const [recommended, setRecommended] = useState<Amounts>();
  const { saving, n, later, flush } = useSaving();
  const [bad, setBad] = useState<string>();

  const shown = useCallback((body: CapsAnswer) => {
    const amounts = (from: Caps): Amounts => ({
      brief: from.brief,
      day: from.day,
      month: from.month,
      budget_above: from.budget_above,
    });
    setCaps(amounts(body.caps));
    setRecommended(amounts(body.recommended));
  }, []);

  useEffect(() => {
    let live = true;
    api("/settings/ai/caps")
      .then((response) => (response.ok ? (response.json() as Promise<CapsAnswer>) : undefined))
      .then((body) => live && body?.caps && shown(body))
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [shown]);

  function changed(name: keyof Amounts, value: string) {
    if (!caps) return;
    const next = { ...caps, [name]: value };
    setCaps(next);
    // only the amounts on this form: whether the subscription stops is not changed here. What the engineer typed
    // stays as typed: the core's answer never rewrites a field under their hands.
    later(async () => {
      const response = await send("/settings/ai/caps", "PUT", next);
      if (response?.ok) {
        setBad(undefined);
        return null;
      }
      const body = (await response?.clone().json().catch(() => undefined)) as { field?: string } | undefined;
      setBad(body?.field); // the amount the core refused, when it says
      return coreLine(response, texts.capsNotSaved);
    }, Object.values(next).every(looksLikeAmount));
  }

  async function goOn() {
    if (await flush()) go?.onGo();
  }

  return (
    <form onSubmit={(event) => event.preventDefault()} onBlur={() => void flush()} className="flex flex-col gap-2">
      {capFields.map(([name, label]) => (
        <Amount
          key={name}
          label={t(label)}
          value={caps?.[name] ?? ""}
          hint={recommended ? fill(t("recommendedAmount"), { value: recommended[name] }) : undefined}
          onChange={(value) => changed(name, value)}
          invalid={bad === name}
        />
      ))}
      <SaveNote saving={saving} n={n} />
      {go && (
        <div>
          <button type="button" disabled={!caps} onClick={() => void goOn()} className={primary}>
            {go.label}
          </button>
        </div>
      )}
    </form>
  );
}
