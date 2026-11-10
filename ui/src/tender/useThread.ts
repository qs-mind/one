// The tender's conversation with the Lead QS: its stored messages (GET /chat/{id}/messages), a reply that still
// runs joined (GET /chat/{id}/stream), a new message (POST /chat), and a message to work that runs (POST
// /briefs/{id}/steer, S98). Work ONE started by itself is joined when its `brief` event comes (S80); when it ends,
// the messages are read again so the thread holds what the core stored.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useCallback, useEffect, useMemo } from "react";
import { api } from "@/api";
import type { Schemas } from "@/api/client";
import type { ComposerMessage, LeadActivity } from "@/conversation/Composer";
import { briefState, type DataPart, isData, type ThreadMessage } from "@/conversation/parts";

// Only the new message goes to the core: it keeps the history with its Briefs.
const transport = new DefaultChatTransport<ThreadMessage>({
  api: "/chat",
  fetch: (input, init) => api(String(input), init),
  prepareSendMessagesRequest: ({ id, messages, body }) => ({ body: { ...body, id, messages: messages.slice(-1) } }),
});

async function stored(chatId: string): Promise<ThreadMessage[] | null> {
  const response = await api(`/chat/${encodeURIComponent(chatId)}/messages`).catch(() => undefined);
  if (!response?.ok) return null;
  const body = (await response.json().catch(() => undefined)) as { messages?: ThreadMessage[] } | undefined;
  return body?.messages ?? null;
}

/** The Brief of the newest reply: the id of its status part. */
function briefOf(messages: readonly ThreadMessage[]): string | null {
  const reply = messages.findLast((m) => m.role === "assistant");
  const status = reply?.parts.findLast((p) => isData(p, "status")) as DataPart<"status"> | undefined;
  return status?.id ?? null;
}

export function useThread(projectId: string, brief: Schemas["BriefEvent"] | null) {
  const { messages, setMessages, sendMessage, resumeStream, status } = useChat<ThreadMessage>({ id: projectId, transport });

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
      const response = await api(`/briefs/${encodeURIComponent(id)}/steer`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error(String(response.status));
    },
    [messages],
  );

  return useMemo(() => ({ messages, activity, send, steer }), [messages, activity, send, steer]);
}
