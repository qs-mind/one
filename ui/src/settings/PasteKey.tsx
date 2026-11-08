import { useId, useRef, useState } from "react";
import { ProviderLogo } from "../brand/providers/ProviderLogo";
import { api } from "../api";
import { coreAnswer, type Fix, send } from "../core";
import { fill, pick, t, texts, useLanguage } from "../i18n";
import { FixAction } from "../shell/FixAction";
import { useLiveKey } from "../ui/live";
import type { Choice } from "./AiSettings";

// Only unambiguous prefixes identify an endpoint. A generic sk- can belong to many providers.
function detect(key: string) {
  if (key.startsWith("sk-ant-")) return { name: "Anthropic", connector: "anthropic" };
  if (key.startsWith("sk-or-")) return { name: "OpenRouter", url: "https://openrouter.ai/api/v1" };
  if (key.startsWith("AIza")) return { name: "Google Gemini", url: "https://generativelanguage.googleapis.com/v1beta/openai" };
  return undefined;
}

export function PasteKey({ onSaved, currentModel }: { onSaved: () => void; currentModel?: string }) {
  useLanguage();
  const id = useId();
  const [url, setUrl] = useState("");
  const [needsUrl, setNeedsUrl] = useState(false);
  const [ready, setReady] = useState<{ provider: string; model: string }>();
  const fix = useRef<Fix>(undefined);
  // Keep a failed Standard Link for retry, avoiding a duplicate each time.
  const pending = useRef<{ key: string; url: string; id: string } | undefined>(undefined);
  const key = useLiveKey(1, async (value, signal) => {
    setReady(undefined);
    fix.current = undefined;
    const known = detect(value);
    setNeedsUrl(!known);
    let endpoint = known && "url" in known ? known.url : undefined;
    if (!known) {
      try {
        const address = new URL(url.trim());
        if (address.protocol !== "https:") return texts.providerUrlRefused;
        endpoint = address.href.replace(/\/$/, "");
      } catch { return texts.aiUnknownKey; }
    }
    const provider = known?.name ?? new URL(endpoint!).hostname;
    let connector = known && "connector" in known ? known.connector : undefined;
    if (connector) {
      const saved = await send("/settings/ai-key", "PUT", { provider: connector, value }, signal);
      if (signal.aborted) return null;
      if (!saved?.ok) return (await coreAnswer(saved, texts.keyFailed)).line;
    } else {
      if (pending.current && (pending.current.key !== value || pending.current.url !== endpoint)) {
        await send(`/settings/ai/standard/${encodeURIComponent(pending.current.id)}`, "DELETE");
        pending.current = undefined;
      }
      if (!pending.current) {
        const added = await send("/settings/ai/standard", "POST", { name: provider, base_url: endpoint, key: value }, signal);
        if (!added?.ok) return (await coreAnswer(added, texts.providerNotAdded)).line;
        const link = await added.json() as { id: string };
        pending.current = { key: value, url: endpoint!, id: link.id };
      }
      connector = pending.current.id;
    }
    if (signal.aborted) return null;
    // Ranking belongs to the core, using exact prices and capability cards; no hardcoded model names.
    const response = await api("/settings/ai", { signal }).catch(() => undefined);
    const settings = response?.ok ? await response.json() as { cheapest?: Record<string, Choice>; connectors?: { id: string; error: { en: string; ar: string } | null }[] } : undefined;
    const choice = settings?.cheapest?.[connector!];
    if (!choice) {
      onSaved(); // the new link must be available for an explicit model choice in Advanced settings
      return settings?.connectors?.find(link => link.id === connector)?.error ?? texts.aiNoCheapModel;
    }
    // Save only the lead; the core derives the other roles, including the Checking QS.
    const selected = await send("/settings/model", "PUT", {
      id: choice.model,
      ...(choice.connector === "anthropic" ? {} : { connector: choice.connector }),
    }, signal);
    if (!selected?.ok) return (await coreAnswer(selected, texts.roleNotSaved)).line;
    const checked = await send("/settings/ai/check", "POST", connector === "anthropic" ? { via: "api_key" } : { via: "standard", connector }, signal);
    if (signal.aborted) return null;
    if (!checked?.ok) {
      onSaved();
      const answer = await coreAnswer(checked, texts.keyFailed);
      fix.current = answer.fix;
      return answer.line;
    }
    pending.current = undefined;
    setReady({ provider, model: choice.model });
    onSaved();
    return null;
  });
  return <div className="flex flex-col gap-2">
    <label htmlFor={id}>{t("pasteAiKey")}</label>
    <input id={id} type="password" dir="ltr" autoComplete="off" spellCheck={false} {...key.field}
      aria-invalid={key.live.state === "failed" || undefined} className="rounded-md border border-slate bg-paper px-3 py-2" />
    {needsUrl && <label className="flex flex-col gap-1">{t("aiProviderUrl")}
      <input type="url" dir="ltr" value={url} onChange={event => setUrl(event.target.value)} onBlur={key.again}
        onKeyDown={event => { if (event.key === "Enter") key.again(); }} className="rounded-md border border-slate bg-paper px-3 py-2" />
    </label>}
    <div data-key-line aria-live="polite">
      {key.live.state === "busy" && <p>{t("aiLinkChecking")}</p>}
      {key.live.state === "done" && ready && (!currentModel || currentModel === ready.model) && <p role="status" className="flex items-center gap-2"><ProviderLogo provider={ready.provider === "Anthropic" ? "anthropic" : ready.provider === "Google Gemini" ? "google" : ready.provider === "OpenRouter" ? "openrouter" : ready.provider} />{fill(t("aiReadyModel"), ready)}</p>}
      {key.live.state === "failed" && <p role="alert" className="text-copper">{pick(key.live.line)}</p>}
      {key.live.state === "failed" && fix.current === "retry" && <button onClick={key.again}>{t("tryAgain")}</button>}
      {key.live.state === "failed" && fix.current === "consent" && <FixAction fix="consent" />}
    </div>
  </div>;
}
