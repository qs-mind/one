// The tender's conversation with the Lead QS: its stored messages (GET /chat/{id}/messages), a reply that still
// runs joined (GET /chat/{id}/stream), a new message (POST /chat), and a message to work that runs (POST
// /briefs/{id}/steer, S98). Work ONE started by itself is joined when its `brief` event comes (S80); when it ends,
// the messages are read again so the thread holds what the core stored. A message the core refused says why
// (`refused`); one that found other work running (409 {brief_id}) goes to that work as a steer, and the thread joins it.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Schemas } from "@/api/client";
import { chatFetch, getChatMessages, steerBrief } from "@/api/existing";
import type { ComposerMessage, LeadActivity } from "@/conversation/Composer";
import { briefState, type DataPart, isData, textOf, type ThreadMessage } from "@/conversation/parts";
import { cards } from "@/texts/cards";

// Only the new message goes to the core: it keeps the history with its Briefs.
const transport = new DefaultChatTransport<ThreadMessage>({
  api: "/chat",
  fetch: chatFetch,
  prepareSendMessagesRequest: ({ id, messages, body }) => ({ body: { ...body, id, messages: messages.slice(-1) } }),
});

async function stored(chatId: string): Promise<ThreadMessage[] | null> {
  const got = await getChatMessages(chatId);
  return (got.data?.messages as ThreadMessage[] | undefined) ?? null;
}

/** Why a message got no answer: the core's words from the stream's error chunk ({en, ar, fix?}), or null when it gave
 * none; `busy` is the work it found running (409 {brief_id}), which the message is steered to. */
export function refusalOf(error: Error | undefined): { words: Schemas["Text"] | null; busy: string | null } | null {
  if (!error) return null;
  try {
    const said = JSON.parse(error.message) as Partial<Schemas["Text"]> & { brief_id?: unknown };
    if (typeof said.en === "string" && typeof said.ar === "string") return { words: { en: said.en, ar: said.ar }, busy: null };
    return { words: null, busy: typeof said.brief_id === "string" ? said.brief_id : null };
  } catch {
    return { words: null, busy: null };
  }
}

/** The Brief of the newest reply: the id of its status part. */
function briefOf(messages: readonly ThreadMessage[]): string | null {
  const reply = messages.findLast((m) => m.role === "assistant");
  const status = reply?.parts.findLast((p) => isData(p, "status")) as DataPart<"status"> | undefined;
  return status?.id ?? null;
}

export function useThread(projectId: string, brief: Schemas["BriefEvent"] | null) {
  const { messages, setMessages, sendMessage, resumeStream, status, error } = useChat<ThreadMessage>({ id: projectId, transport });

  const reread = useCallback(async () => {
    const earlier = await stored(projectId);
    if (earlier) setMessages(earlier);
  }, [projectId, setMessages]);

  useEffect(() => {
    let live = true;
    void stored(projectId).then((earlier) => {
      if (!live || !earlier) return;
      setMessages((now) => (now.length ? now : earlier)); // never over a message sent meanwhile
      void resumeStream();
    });
    return () => {
      live = false;
    };
  }, [projectId, setMessages, resumeStream]);

  // Work the driver started joins the thread; its end is read back from the core.
  useEffect(() => {
    if (!brief) return;
    if (brief.state === "running" || brief.state === "queued") void resumeStream();
    else void reread();
  }, [brief, resumeStream, reread]);

  // A message that found other work running was not stored: its words go to that work instead, and the thread joins
  // it (the steer comes back in the reply). When that work refuses them too, the bubble stays and a line says so.
  const found = useMemo(() => refusalOf(error), [error]);
  const [unsent, setUnsent] = useState<Error | null>(null);
  useEffect(() => {
    const busy = found?.busy;
    if (!busy || !error) return;
    let live = true;
    const last = messages.at(-1);
    const words = last?.role === "user" ? textOf(last) : "";
    void (words ? steerBrief(busy, words) : Promise.resolve({ error: null })).then((got) => {
      if (!live) return;
      if (got.error !== undefined) return setUnsent(error);
      setMessages((now) => (now.at(-1)?.id === last?.id ? now.slice(0, -1) : now));
      void resumeStream();
    });
    return () => {
      live = false;
    };
    // only once per refusal: the messages are read as they stood when it came
  }, [found, error]);
  const refused = useMemo(
    () => (found?.busy ? (unsent === error ? { words: cards.messageNotSent, busy: found.busy } : null) : found),
    [found, unsent, error],
  );

  const state = briefState(messages);
  const streaming = status === "submitted" || status === "streaming";
  const activity: LeadActivity =
    state === "waiting_engineer" ? "held" : state || streaming ? "working" : "idle";

  const send = useCallback(
    ({ text }: ComposerMessage) => {
      if (text.trim()) void sendMessage({ text: text.trim() });
    },
    [sendMessage],
  );

  const steer = useCallback(
    async ({ text }: ComposerMessage) => {
      const id = briefOf(messages);
      if (!id) throw new Error("no work runs");
      const got = await steerBrief(id, text);
      if (got.error !== undefined) throw new Error("the steer was refused");
    },
    [messages],
  );

  /** Joins work that runs again (cut-off work continued). */
  const resume = useCallback(() => void resumeStream(), [resumeStream]);

  return useMemo(
    () => ({ messages, activity, send, steer, resume, refused }),
    [messages, activity, send, steer, resume, refused],
  );
}
