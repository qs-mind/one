// The chat with the Lead QS. Each message starts a Brief, which runs in the core whether or not this page watches it:
// its stream shows the reply, the Progress Line, the Coordination Room, cards and Review codes as they come. A message
// sent while the Brief runs steers it; Stop ends it. Opening a chat loads its earlier messages and joins a running Brief.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, generateId } from "ai";
import { useEffect, useRef, useState } from "react";
import { coreLine, send } from "../core";
import { DeliverableCard } from "../deliverables/DeliverableCard";
import { DeliverableViewer } from "../deliverables/DeliverableViewer";
import { ProjectIndex } from "../deliverables/ProjectIndex";
import { language, pick, setLanguage, t, type Text, texts, useLanguage } from "../i18n";
import { restoreProject, useProject } from "../records/project";
import { ProjectPicker } from "../records/ProjectPicker";
import { RecordsPanel } from "../records/RecordsPanel";
import { AiSettings, useAiSettings } from "../settings/AiSettings";
import { ApprovalCard } from "./parts/ApprovalCard";
import { ContinueBriefs, type Unfinished } from "./parts/ContinueBriefs";
import { CoordinationRoom } from "./parts/CoordinationRoom";
import { CostNotice } from "./parts/CostNotice";
import { ProgressLine } from "./parts/ProgressLine";
import { ReviewBadge } from "./parts/ReviewBadge";
import { activeBrief, type OneMessage, type OnePart, partsOf } from "./parts/types";
import { Reply } from "./Reply";

// Only the new message goes to the core: it keeps the chat's history with its Briefs.
const transport = new DefaultChatTransport<OneMessage>({
  api: "/api/chat",
  prepareSendMessagesRequest: ({ id, messages }) => ({ body: { id, messages: messages.slice(-1) } }),
});

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

/** The Brief that kept the chat busy, when the core answered a new message with 409 {brief_id}. */
function busyWith(error: Error | undefined): string | undefined {
  try {
    const body = JSON.parse(error?.message ?? "") as { brief_id?: unknown };
    return typeof body.brief_id === "string" ? body.brief_id : undefined;
  } catch {
    return undefined;
  }
}

function textOf(parts: OnePart[]): string {
  return parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}

function BriefReply({ parts, deliverables }: { parts: OnePart[]; deliverables?: Deliverables }) {
  const text = textOf(parts);
  return (
    <div className="flex flex-col gap-3">
      <ProgressLine items={partsOf(parts, "progress")} />
      <CoordinationRoom messages={partsOf(parts, "team")} />
      {text && <Reply text={text} unsourced={partsOf(parts, "unsourced").flatMap((part) => part.data.values)} />}
      {partsOf(parts, "card").map((card) => (
        <ApprovalCard key={card.id} id={card.id} card={card.data} />
      ))}
      {partsOf(parts, "cost").map((cost) => (
        <CostNotice key={cost.id} cost={cost.data} />
      ))}
      {partsOf(parts, "review").map((review) => (
        <ReviewBadge key={review.id} review={review.data} />
      ))}
      {deliverables &&
        partsOf(parts, "deliverable").map((part) => (
          <DeliverableCard key={part.id} projectId={deliverables.projectId} id={part.data.id} onOpen={deliverables.open} />
        ))}
    </div>
  );
}

// Plan 6: the Deliverables beside the chat (the Project Index, and one Deliverable open in the side panel). Kept in
// one place so Plan 7's shell can move it.
type Deliverables = { projectId: string; open: (id: string) => void };

/** Which Deliverable is open beside the chat, and the element that opened it, so Esc can give focus back. */
function useDeliverablePanel(projectId: string | undefined) {
  const [indexOpen, setIndexOpen] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const opener = useRef<HTMLElement | null>(null);
  useEffect(() => {
    setIndexOpen(false);
    setOpen(null);
  }, [projectId]);
  return {
    indexOpen,
    open,
    toggleIndex: () => setIndexOpen((now) => !now),
    closeIndex: () => setIndexOpen(false),
    show(id: string) {
      opener.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      setOpen(id);
    },
    close() {
      setOpen(null);
      const back = opener.current;
      queueMicrotask(() => back?.focus());
    },
  };
}

export function Chat() {
  const lang = useLanguage();
  const project = useProject();
  const chatId = project?.id ?? "general";
  const { messages, setMessages, sendMessage, status, stop, error, clearError, resumeStream } = useChat<OneMessage>({
    id: chatId,
    transport,
  });
  const [draft, setDraft] = useState("");
  const [failed, setFailed] = useState<Text>(); // a steer or stop the core did not take
  const [stopped, setStopped] = useState<ReadonlySet<string>>(new Set());
  const ai = useAiSettings();
  // where AI settings show: "main", in place of the chat when nothing is connected yet; "side" beside the chat
  const [aiOpen, setAiOpen] = useState<false | "main" | "side">(false);
  const [wasConnected, setWasConnected] = useState(ai.connected);
  if (wasConnected !== ai.connected) {
    // the first AI connected: the settings stay open to say so, with Close, and the chat opens below. Set while
    // rendering, so the open settings are never unmounted in between.
    setWasConnected(ai.connected);
    if (wasConnected === false && ai.connected) setAiOpen("main");
  }
  const [pickerOpen, setPickerOpen] = useState(false);
  const [recordsOpen, setRecordsOpen] = useState(false);
  const panel = useDeliverablePanel(project?.id);
  const list = useRef<HTMLDivElement>(null);
  const streaming = status === "submitted" || status === "streaming";
  const found = activeBrief(messages);
  const brief = found && !stopped.has(found) ? found : undefined;
  const running = streaming || brief !== undefined;
  const aiMain = ai.connected === false || aiOpen === "main";
  const sideOpen = (aiOpen === "side" && !aiMain) || pickerOpen || recordsOpen || panel.indexOpen || panel.open !== null;
  const deliverables: Deliverables | undefined = project ? { projectId: project.id, open: panel.show } : undefined;
  const elsewhere = busyWith(error);

  useEffect(() => {
    // a remembered project that no longer opens is forgotten, and the picker shows
    void restoreProject().then((result) => result === "failed" && setPickerOpen(true));
  }, []);

  useEffect(() => {
    // the chat's earlier messages, then the Brief still running in it, replayed from its start (204: none)
    let live = true;
    fetch(`/api/chat/${encodeURIComponent(chatId)}/messages`)
      .then((response) => (response.ok ? (response.json() as Promise<{ messages?: OneMessage[] }>) : undefined))
      .then((body) => {
        if (!live || !body?.messages) return;
        const earlier = body.messages;
        setMessages((now) => (now.length ? now : earlier)); // never over a message sent meanwhile
        void resumeStream();
      })
      .catch(() => undefined); // the chat starts empty
    return () => {
      live = false;
    };
  }, [chatId, setMessages, resumeStream]);

  useEffect(() => {
    // the chat already had a Brief running (started elsewhere): the message steers it, and the page joins its stream
    if (!elsewhere) return;
    clearError();
    const last = messages.findLast((message) => message.role === "user");
    if (!last) return;
    setMessages((now) => now.map((m) => (m.id === last.id ? { ...m, metadata: { steering: true } } : m)));
    void steerWith(elsewhere, textOf(last.parts)).then((ok) => ok && void resumeStream());
  }, [elsewhere]); // runs once per refused message; the rest is read as it is then

  useEffect(() => {
    list.current?.scrollTo?.({ top: list.current.scrollHeight });
  }, [messages]);

  async function steerWith(id: string, text: string): Promise<boolean> {
    setFailed(undefined);
    const response = await send(`/api/briefs/${encodeURIComponent(id)}/steer`, "POST", { text });
    if (!response?.ok) setFailed(await coreLine(response, texts.steerFailed));
    return response?.ok === true;
  }

  /** Sends the typed message, or `given` (a Review comment's "Fix it"), which leaves the box as it is. */
  async function submit(given?: string) {
    const typed = given === undefined;
    const text = (given ?? draft).trim();
    if (!text) return;
    if (brief) {
      if (typed) setDraft("");
      if (await steerWith(brief, text)) {
        const steering: OneMessage = {
          id: generateId(),
          role: "user",
          parts: [{ type: "text", text }],
          metadata: { steering: true },
        };
        setMessages((now) => [...now, steering]);
      } else if (typed) {
        setDraft(text);
      }
      return;
    }
    if (streaming) return; // the Brief is starting; its id comes with its first status
    if (typed) setDraft("");
    setFailed(undefined);
    void sendMessage({ text });
  }

  async function halt() {
    const id = brief;
    void stop(); // the stream ends here at once; the Brief itself ends only by the stop call
    if (!id) return;
    setStopped((now) => new Set(now).add(id));
    const response = await send(`/api/briefs/${encodeURIComponent(id)}/stop`, "POST");
    if (!response?.ok) {
      setStopped((now) => new Set([...now].filter((other) => other !== id)));
      setFailed(await coreLine(response, texts.stopFailed));
    }
  }

  function continued(unfinished: Unfinished) {
    if (unfinished.chat_id === chatId) void resumeStream();
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
          {project && (
            <button type="button" aria-expanded={panel.indexOpen} onClick={panel.toggleIndex} className="text-slate hover:text-ink">
              {t("deliverablesButton")}
            </button>
          )}
        </div>
        <div className="flex items-center gap-4 text-slate">
          <button
            type="button"
            aria-expanded={aiOpen !== false || aiMain}
            onClick={() => setAiOpen(aiOpen === "side" ? false : "side")}
            className="hover:text-ink"
          >
            {t("ai")}
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

      {/* Panels sit beside the chat at the inline end (left in Arabic, right in English); below 900 px they take
          the whole width until closed. They come first in the page, so Tab still reaches an open panel before the
          chat, as before. */}
      <div className="flex min-h-0 flex-1">
        {sideOpen && (
          <div
            className={`w-full overflow-y-auto min-[900px]:order-last min-[900px]:shrink-0 min-[900px]:border-s min-[900px]:border-stone ${
              panel.open ? "flex flex-col min-[900px]:w-[min(60vw,1100px)]" : "min-[900px]:w-md"
            }`}
            onKeyDown={(event) => {
              // Esc closes the open Deliverable, unless it closes something inside it first (an editor, a popover)
              const target = event.target as HTMLElement;
              if (event.key !== "Escape" || !panel.open || event.defaultPrevented) return;
              if (target.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) return;
              panel.close();
            }}
          >
            {aiOpen === "side" && !aiMain && <AiSettings ai={ai} onClose={() => setAiOpen(false)} />}
            {pickerOpen && <ProjectPicker onClose={() => setPickerOpen(false)} />}
            {recordsOpen && (
              <RecordsPanel onClose={() => setRecordsOpen(false)} onPickProject={() => setPickerOpen(true)} />
            )}
            {project && panel.indexOpen && (
              <div hidden={panel.open !== null}>
                <ProjectIndex projectId={project.id} onOpen={panel.show} onClose={panel.closeIndex} />
              </div>
            )}
            {project && panel.open && (
              <div className="flex min-h-[70dvh] flex-1 flex-col">
                <div className="flex justify-end border-b border-stone px-2 py-1">
                  {/* focus moves into the panel, so Esc there closes it and gives focus back to the opener */}
                  <button type="button" autoFocus className="rounded px-2 hover:bg-stone" onClick={panel.close}>
                    {t("close")}
                  </button>
                </div>
                <div className="min-h-0 flex-1">
                  <DeliverableViewer
                    key={panel.open}
                    projectId={project.id}
                    deliverableId={panel.open}
                    mode="full"
                    onSend={(text) => void submit(text)}
                  />
                </div>
              </div>
            )}
          </div>
        )}

        <div className={`flex min-w-0 flex-1 flex-col ${sideOpen ? "max-[899px]:hidden" : ""}`}>
          {aiMain && (
            <div className={ai.connected === false ? "overflow-y-auto" : "max-h-[50%] shrink-0 overflow-y-auto"}>
              <AiSettings ai={ai} onClose={ai.connected === false ? undefined : () => setAiOpen(false)} />
            </div>
          )}

          {ai.connected !== false && (
            <>
              <ContinueBriefs onContinued={continued} />
              <div ref={list} className="flex-1 overflow-y-auto px-4 py-4">
                <ol className="mx-auto flex max-w-2xl flex-col gap-4">
                  {messages.length === 0 && <li className="text-slate">{t("empty")}</li>}
                  {messages.map((message) =>
                    message.role === "user" ? (
                      <li key={message.id} className="max-w-[85%] self-end rounded-lg bg-stone px-3 py-2">
                        {message.metadata?.steering && <p className="text-slate">{t("steering")}</p>}
                        <p dir="auto" className="whitespace-pre-wrap">
                          {textOf(message.parts)}
                        </p>
                      </li>
                    ) : (
                      <li key={message.id}>
                        <BriefReply parts={message.parts} deliverables={deliverables} />
                      </li>
                    ),
                  )}
                  {status === "submitted" && <li className="text-slate">{t("thinking")}</li>}
                  {error && !elsewhere && (
                    <li role="alert" className="text-copper">
                      {errorLine(error)}
                    </li>
                  )}
                  {failed && (
                    <li role="alert" className="text-copper">
                      {pick(failed)}
                    </li>
                  )}
                </ol>
              </div>

              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  void submit();
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
                        void submit();
                      }
                    }}
                    className="flex-1 resize-none rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink"
                  />
                  <button
                    type="submit"
                    disabled={!draft.trim() || (streaming && !brief)}
                    className="rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40"
                  >
                    {t("send")}
                  </button>
                  {running && (
                    <button type="button" onClick={() => void halt()} className="rounded-md border border-ink px-4 py-2">
                      {t("stop")}
                    </button>
                  )}
                </div>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
