// The chat with the Lead QS. Replies stream word by word from the core; Stop ends the reply and the request.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useEffect, useRef, useState } from "react";
import { language, pick, setLanguage, t, type Text, useLanguage } from "../i18n";
import { restoreProject, useProject } from "../records/project";
import { ProjectPicker } from "../records/ProjectPicker";
import { RecordsPanel } from "../records/RecordsPanel";
import { AiKey } from "../settings/AiKey";
import { ModelPanel, useModel } from "../settings/Model";
import { Reply } from "./Reply";

const transport = new DefaultChatTransport({ api: "/api/chat" });

// The core sends a model error as an {en, ar} pair in the error text; any other failure gets the plain line.
function errorLine(error: Error): string {
  try {
    const text = JSON.parse(error.message) as Partial<Text>;
    if (typeof text.en === "string" && typeof text.ar === "string") return pick(text as Text);
  } catch {
    // not from the core
  }
  return t("chatError");
}

function textOf(parts: { type: string; text?: string }[]): string {
  return parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}

export function Chat() {
  const lang = useLanguage();
  const { messages, sendMessage, status, stop, error } = useChat({ transport });
  const [draft, setDraft] = useState("");
  const [keySet, setKeySet] = useState<boolean>();
  const [keyOpen, setKeyOpen] = useState(false);
  const model = useModel(keySet);
  const [modelOpen, setModelOpen] = useState(false);
  const project = useProject();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [recordsOpen, setRecordsOpen] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const busy = status === "submitted" || status === "streaming";

  useEffect(() => {
    let live = true;
    fetch("/api/settings/ai-key")
      .then((response) => (response.ok ? (response.json() as Promise<{ set?: boolean }>) : undefined))
      .then((body) => live && body && setKeySet(body.set === true))
      .catch(() => undefined); // the core will answer the first message with how to add a key
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    // a remembered project that no longer opens is forgotten, and the picker shows
    void restoreProject().then((result) => result === "failed" && setPickerOpen(true));
  }, []);

  useEffect(() => {
    list.current?.scrollTo?.({ top: list.current.scrollHeight });
  }, [messages]);

  function send() {
    const text = draft.trim();
    if (!text || busy) return;
    setDraft("");
    void sendMessage({ text });
  }

  function toggleModels() {
    const state = model.list.state;
    if (!modelOpen && (state === "idle" || state === "no-key" || state === "failed")) void model.load();
    setModelOpen(!modelOpen);
  }

  return (
    <div className="flex h-dvh flex-col">
      <header className="flex items-center justify-between gap-4 border-b border-stone px-4 py-2">
        <div className="flex min-w-0 items-center gap-4">
          <span className="font-semibold">{t("appName")}</span>
          <button
            type="button"
            dir="auto"
            title={t("projects")}
            aria-expanded={pickerOpen}
            onClick={() => setPickerOpen(!pickerOpen)}
            className="max-w-48 truncate hover:text-copper"
          >
            {project?.name ?? t("projects")}
          </button>
          <button
            type="button"
            aria-expanded={recordsOpen}
            onClick={() => setRecordsOpen(!recordsOpen)}
            className="text-slate hover:text-ink"
          >
            {t("records")}
          </button>
        </div>
        <div className="flex items-center gap-4 text-slate">
          <button
            type="button"
            dir="auto"
            title={t("modelTitle")}
            aria-expanded={modelOpen}
            onClick={toggleModels}
            className="hover:text-ink"
          >
            {model.name ?? t("model")}
          </button>
          <button type="button" onClick={() => setKeyOpen(true)} className="hover:text-ink">
            {t("aiKey")}
          </button>
          <button
            type="button"
            lang={lang === "ar" ? "en" : "ar"}
            onClick={() => setLanguage(language() === "ar" ? "en" : "ar")}
            className="hover:text-ink"
          >
            {t("otherLanguage")}
          </button>
        </div>
      </header>

      {(keySet === false || keyOpen) && (
        <AiKey
          onSaved={() => {
            setKeySet(true);
            setKeyOpen(true); // stay open to say the key was added
          }}
          onClose={keySet === false ? undefined : () => setKeyOpen(false)}
        />
      )}

      {modelOpen && <ModelPanel model={model} onClose={() => setModelOpen(false)} />}

      {pickerOpen && <ProjectPicker onClose={() => setPickerOpen(false)} />}

      {recordsOpen && <RecordsPanel onClose={() => setRecordsOpen(false)} onPickProject={() => setPickerOpen(true)} />}

      {keySet !== false && (
        <>
          <div ref={list} className="flex-1 overflow-y-auto px-4 py-4">
            <ol className="mx-auto flex max-w-2xl flex-col gap-4">
              {messages.length === 0 && <li className="text-slate">{t("empty")}</li>}
              {messages.map((message) => (
                <li
                  key={message.id}
                  className={message.role === "user" ? "max-w-[85%] self-end rounded-lg bg-stone px-3 py-2" : ""}
                >
                  {message.role === "user" ? (
                    <p dir="auto" className="whitespace-pre-wrap">
                      {textOf(message.parts)}
                    </p>
                  ) : (
                    <Reply text={textOf(message.parts)} />
                  )}
                </li>
              ))}
              {status === "submitted" && <li className="text-slate">{t("thinking")}</li>}
              {error && (
                <li role="alert" className="text-copper">
                  {errorLine(error)}
                </li>
              )}
            </ol>
          </div>

          <form
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
            className="border-t border-stone px-4 py-3"
          >
            <div className="mx-auto flex max-w-2xl items-end gap-2">
              <textarea
                aria-label={t("message")}
                placeholder={t("message")}
                dir="auto"
                rows={2}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                    event.preventDefault();
                    send();
                  }
                }}
                className="flex-1 resize-none rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink"
              />
              {busy ? (
                <button type="button" onClick={() => void stop()} className="rounded-md border border-ink px-4 py-2">
                  {t("stop")}
                </button>
              ) : (
                <button
                  type="submit"
                  disabled={!draft.trim()}
                  className="rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40"
                >
                  {t("send")}
                </button>
              )}
            </div>
          </form>
        </>
      )}
    </div>
  );
}
