// Plan 4's chat with the Lead QS, as it is, for one chat id: a project's id or "general". Each message starts a Brief,
// which runs in the core whether or not this page watches it. Opening a chat loads its earlier messages from the core
// (which stores them with their Briefs; the screen saves nothing) and joins a Brief still running. A message sent
// while the Brief runs steers it; Stop ends it. Switching project switches the chat.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport, generateId } from "ai";
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { SelectionItem } from "../canvas/types";
import type { Unfinished } from "../chat/parts/ContinueBriefs";
import { activeBrief, type OneMessage, type OnePart, partsOf } from "../chat/parts/types";
import { coreLine, send as sendJson } from "../core";
import { type Text, texts } from "../i18n";
import type { Choice, Effort } from "../settings/AiSettings";

// Only the new message goes to the core: it keeps the chat's history with its Briefs. The selection rides along.
// The transport's own URLs ("/chat", "/chat/<id>/stream") are core routes, so they go through api() too.
const transport = new DefaultChatTransport<OneMessage>({
  api: "/chat",
  fetch: (input, init) => api(String(input), init),
  prepareSendMessagesRequest: ({ id, messages, body }) => ({ body: { ...body, id, messages: messages.slice(-1) } }),
});

/** The Brief that kept the chat busy, when the core answered a new message with 409 {brief_id}. */
function busyWith(error: Error | undefined): string | undefined {
  try {
    const body = JSON.parse(error?.message ?? "") as { brief_id?: unknown };
    return typeof body.brief_id === "string" ? body.brief_id : undefined;
  } catch {
    return undefined;
  }
}

/** The Lead QS's model and effort, as picked in the message box; left out, the core uses its own. */
export type Picked = { model?: Choice; effort?: Effort };

const RESYNC_TRIES = 3;
const RESYNC_MS = 1000;

/** Whether these messages show a card still waiting for the engineer. */
export function showsWaitingCard(messages: OneMessage[]): boolean {
  return messages.some((message) =>
    partsOf(message.parts, "card").some((card) => card.data.status === "pending" || card.data.status === undefined),
  );
}

export function textOf(parts: OnePart[]): string {
  return parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}

// A request handed to another chat (the General chat's hand-off): sent there once that chat has loaded.
const queued = new Map<string, string>();
const queueListeners = new Set<() => void>();

/** Sends `text` in the chat `chatId` as soon as it is open and loaded. */
export function sendWhenOpen(chatId: string, text: string) {
  queued.set(chatId, text);
  for (const listener of queueListeners) listener();
}

export function useChats(chatId: string) {
  const { messages, setMessages, sendMessage, status, stop, error, clearError, resumeStream } = useChat<OneMessage>({
    id: chatId,
    transport,
  });
  const [failed, setFailed] = useState<Text>(); // a steer or stop the core did not take
  const [stopped, setStopped] = useState<ReadonlySet<string>>(new Set());
  const [loaded, setLoaded] = useState<string>(); // the chat whose earlier messages came
  const [queueTick, setQueueTick] = useState(0);
  const streaming = status === "submitted" || status === "streaming";
  const found = activeBrief(messages);
  const brief = found && !stopped.has(found) ? found : undefined;
  const elsewhere = busyWith(error);

  useEffect(() => {
    // the chat's earlier messages, then the Brief still running in it, replayed from its start (204: none)
    let live = true;
    setLoaded(undefined);
    api(`/chat/${encodeURIComponent(chatId)}/messages`)
      .then((response) => (response.ok ? (response.json() as Promise<{ messages?: OneMessage[] }>) : undefined))
      .then((body) => {
        if (!live || !body?.messages) return;
        const earlier = body.messages;
        setMessages((now) => (now.length ? now : earlier)); // never over a message sent meanwhile
        void resumeStream();
      })
      .catch(() => undefined) // the chat starts empty
      .finally(() => live && setLoaded(chatId));
    return () => {
      live = false;
    };
  }, [chatId, setMessages, resumeStream]);

  /** The chat as the core has it now: its messages again, then the running Brief's stream replayed from its start.
   * For when this page may have missed part of a Brief (its stream dropped, or the core says a card waits that the
   * chat does not show). */
  const resync = useCallback(async () => {
    await stop(); // the old stream, if any, must not write over the core's messages
    const body = await api(`/chat/${encodeURIComponent(chatId)}/messages`)
      .then((response) => (response.ok ? (response.json() as Promise<{ messages?: OneMessage[] }>) : undefined))
      .catch(() => undefined);
    if (body?.messages?.length) setMessages(body.messages);
    void resumeStream();
  }, [chatId, stop, setMessages, resumeStream]);

  // A stream that ended while its Brief still runs (a dropped connection) is joined again, a few times at most.
  const tries = useRef(new Map<string, number>());
  const before = useRef(status);
  useEffect(() => {
    const was = before.current;
    before.current = status;
    const ended = (was === "streaming" || was === "submitted") && (status === "ready" || status === "error");
    if (!ended || !brief || elsewhere) return;
    const n = tries.current.get(brief) ?? 0;
    if (n >= RESYNC_TRIES) return;
    tries.current.set(brief, n + 1);
    const timer = setTimeout(() => void resync(), RESYNC_MS * (n + 1));
    return () => clearTimeout(timer);
  }, [status, brief, elsewhere, resync]);

  useEffect(() => {
    // the chat already had a Brief running (started elsewhere): the message steers it, and the page joins its stream
    if (!elsewhere) return;
    clearError();
    const last = messages.findLast((message) => message.role === "user");
    if (!last) return;
    setMessages((now) => now.map((m) => (m.id === last.id ? { ...m, metadata: { steering: true } } : m)));
    void steerWith(elsewhere, textOf(last.parts)).then((ok) => ok && void resumeStream());
  }, [elsewhere]); // runs once per refused message; the rest is read as it is then

  async function steerWith(id: string, text: string): Promise<boolean> {
    setFailed(undefined);
    const response = await sendJson(`/briefs/${encodeURIComponent(id)}/steer`, "POST", { text });
    if (!response?.ok) setFailed(await coreLine(response, texts.steerFailed));
    return response?.ok === true;
  }

  /** Sends a message to the Lead QS, with the canvas selection and the model and effort picked in the message box
   * (for the Brief it starts); while a Brief runs it steers it instead. Answers false when the text was not taken (a
   * refused steer), so the box can keep it. */
  async function send(text: string, selection: readonly SelectionItem[] = [], picked: Picked = {}): Promise<boolean> {
    const trimmed = text.trim();
    if (!trimmed) return false;
    if (brief) {
      if (!(await steerWith(brief, trimmed))) return false;
      const steering: OneMessage = { id: generateId(), role: "user", parts: [{ type: "text", text: trimmed }], metadata: { steering: true } };
      setMessages((now) => [...now, steering]);
      return true;
    }
    if (streaming) return false; // the Brief is starting; its id comes with its first status
    setFailed(undefined);
    const chosen = [...selection];
    const body = {
      ...(chosen.length ? { selection: chosen } : {}),
      ...(picked.model ? { model: picked.model } : {}),
      ...(picked.effort ? { effort: picked.effort } : {}),
    };
    void sendMessage(
      { text: trimmed, ...(chosen.length ? { metadata: { selection: chosen } } : {}) },
      Object.keys(body).length ? { body } : undefined,
    );
    return true;
  }
  const sendRef = useRef(send);
  sendRef.current = send;

  useEffect(() => {
    const listener = () => setQueueTick((n) => n + 1);
    queueListeners.add(listener);
    return () => void queueListeners.delete(listener);
  }, []);

  useEffect(() => {
    const text = loaded === chatId ? queued.get(chatId) : undefined;
    if (text === undefined) return;
    queued.delete(chatId);
    void sendRef.current(text);
  }, [loaded, chatId, queueTick]);

  async function halt() {
    const id = brief;
    void stop(); // the stream ends here at once; the Brief itself ends only by the stop call
    if (!id) return;
    setStopped((now) => new Set(now).add(id));
    const response = await sendJson(`/briefs/${encodeURIComponent(id)}/stop`, "POST");
    if (!response?.ok) {
      setStopped((now) => new Set([...now].filter((other) => other !== id)));
      setFailed(await coreLine(response, texts.stopFailed));
    }
  }

  const continued = useCallback(
    (unfinished: Unfinished) => {
      if (unfinished.chat_id === chatId) void resumeStream();
    },
    [chatId, resumeStream],
  );

  return {
    chatId,
    messages,
    status,
    error: elsewhere ? undefined : error,
    failed,
    /** A reply is streaming, or a Brief runs: Stop shows. */
    running: streaming || brief !== undefined,
    /** A new message can go now (or steer the running Brief). */
    canSend: !(streaming && !brief),
    send,
    halt,
    continued,
    resync,
  };
}

export type ChatState = ReturnType<typeof useChats>;
