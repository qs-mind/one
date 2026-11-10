// The Home conversation with the Lead QS (chat id "general", contract S28, S31, S36): its earlier messages from the
// core, a Brief still running joined from its start, a new message sent with POST /chat. While the Lead works, or a
// card holds its work, a message steers it (POST /briefs/{id}/steer); the reply's data-status part names the Brief.
import { useChat } from "@ai-sdk/react";
import { DefaultChatTransport } from "ai";
import { useEffect } from "react";
import { chatFetch, getChatMessages, steerBrief } from "@/api/existing";
import type { ComposerMessage, LeadActivity } from "@/conversation/Composer";
import { briefState, isData, type DataPart, type ThreadMessage } from "@/conversation/parts";

export const HOME_CHAT = "general";

// Only the new message goes: the core keeps the chat's history with its Briefs.
const transport = new DefaultChatTransport<ThreadMessage>({
  api: "/chat",
  fetch: chatFetch,
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
    void getChatMessages(HOME_CHAT).then(({ data }) => {
      if (!live || !data?.messages) return; // the conversation starts empty
      const earlier = data.messages as ThreadMessage[];
      setMessages((now) => (now.length ? now : earlier)); // never over a message sent meanwhile
      void resumeStream();
    });
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

  // Words only: Home's box sends no files (HomeBox says so; a tender's files come in its folder).
  const send = (message: ComposerMessage) => void sendMessage({ text: message.text });

  async function steer(message: ComposerMessage) {
    const brief = lastBrief(messages);
    if (!brief || (await steerBrief(brief, message.text)).error !== undefined) throw new Error("not steered");
  }

  return { messages, activity, send, steer };
}
