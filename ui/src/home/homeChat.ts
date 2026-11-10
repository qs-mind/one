// The Home conversation with the Lead QS (chat id "general", contract S28, S31, S36): its earlier messages from the
// core, a Brief still running joined from its start, a new message sent with POST /chat. While the Lead works, or a
// card holds its work, a message steers it (POST /briefs/{id}/steer); the reply's data-status part names the Brief.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useEffect } from "react";
import { api } from "@/api";
import type { ComposerMessage, LeadActivity } from "@/conversation/Composer";
import { briefState, isData, type DataPart, type ThreadMessage } from "@/conversation/parts";

export const HOME_CHAT = "general";

// Only the new message goes: the core keeps the chat's history with its Briefs. Its URLs are core routes, so they
// go through api() too.
const transport = new DefaultChatTransport<ThreadMessage>({
  api: "/chat",
  fetch: (input, init) => api(String(input), init),
  prepareSendMessagesRequest: ({ id, messages }) => ({ body: { id, messages: messages.slice(-1) } }),
});

/** The Brief the last reply belongs to (its data-status part's id). */
function lastBrief(messages: readonly ThreadMessage[]): string | undefined {
  const reply = messages.findLast((message) => message.role === "assistant");
  return (reply?.parts.findLast((part) => isData(part, "status")) as DataPart<"status"> | undefined)?.id;
}

export function useHomeChat() {
  const { messages, setMessages, sendMessage, status, resumeStream } = useChat<ThreadMessage>({ id: HOME_CHAT, transport });

  useEffect(() => {
    let live = true;
    api(`/chat/${HOME_CHAT}/messages`)
      .then((response) => (response.ok ? (response.json() as Promise<{ messages?: ThreadMessage[] }>) : undefined))
      .then((body) => {
        if (!live || !body?.messages) return;
        const earlier = body.messages;
        setMessages((now) => (now.length ? now : earlier)); // never over a message sent meanwhile
        void resumeStream();
      })
      .catch(() => undefined); // the conversation starts empty
    return () => {
      live = false;
    };
  }, [setMessages, resumeStream]);

  const state = briefState(messages);
  const activity: LeadActivity =
    status === "submitted" || status === "streaming" || state === "queued" || state === "running"
      ? "working"
      : state
        ? "held"
        : "idle";

  const send = (message: ComposerMessage) => void sendMessage({ text: message.text });

  async function steer(message: ComposerMessage) {
    const brief = lastBrief(messages);
    const answer = brief
      ? await api(`/briefs/${encodeURIComponent(brief)}/steer`, {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ text: message.text }),
        })
      : undefined;
    if (answer?.status !== 202) throw new Error("not steered");
  }

  return { messages, activity, send, steer };
}
