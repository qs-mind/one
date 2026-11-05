// What every chat's Briefs are doing, for the screen outside each chat: the top bar's mark, the projects' rows and
// one quiet notice at the open chat's foot. The core answers from memory (GET /briefs/activity, opening no project
// file), so the screen asks every 2 s while it shows: a poll needs no stream per project and no replay after the core
// restarts, and a mark two seconds late is still on time. The chat on the screen is "seen": its ended mark clears in
// the core (POST /chat/{id}/seen), and it never makes a notice.
import { useEffect, useSyncExternalStore } from "react";
import { api } from "../api";

export type ActivityState = "working" | "waiting" | "failed" | "done";
/** One chat as the core lists it; `name` is the project's, null for the General chat. */
export type ChatActivity = { chat_id: string; brief_id: string; state: ActivityState; name: string | null };
export type ActivityNotice = { chatId: string; name: string | null; state: Exclude<ActivityState, "working"> };

export const GENERAL = "general";
/** How often the screen asks; tests make it short. */
export const ACTIVITY_POLL = { ms: 2000 };

/** The top bar's one mark for many chats: what most needs the engineer first. */
const RANK: ActivityState[] = ["waiting", "failed", "working", "done"];

let chats: ChatActivity[] = [];
let notice: ActivityNotice | undefined;
let openChat = GENERAL;
let heard = new Map<string, string>(); // chat id: "brief:state" at the last answer, so each change tells once
let answered = false; // the first answer is only heard: what ended before the screen looked is a mark, not news
let users = 0;
let round = 0; // a stopped poll's late answer is dropped
let timer: ReturnType<typeof setTimeout> | undefined;
const listeners = new Set<() => void>();

function changed() {
  for (const listener of listeners) listener();
}

const ended = (state: ActivityState) => state === "done" || state === "failed";

function seenInCore(chatId: string) {
  void api(`/chat/${encodeURIComponent(chatId)}/seen`, { method: "POST" }).catch(() => undefined);
}

function take(next: ChatActivity[]) {
  const before = heard;
  heard = new Map(next.map((c) => [c.chat_id, `${c.brief_id}:${c.state}`]));
  const here = next.find((c) => c.chat_id === openChat && ended(c.state));
  if (here) seenInCore(here.chat_id); // it ended in front of the engineer
  chats = next.filter((c) => c !== here);
  for (const c of chats) {
    if (!answered || c.state === "working" || before.get(c.chat_id) === heard.get(c.chat_id)) continue;
    if (c.chat_id === openChat) continue; // the chat on the screen shows its own card: no «‹name› مستنيك» in it
    notice = { chatId: c.chat_id, name: c.name, state: c.state };
  }
  // a notice says what is true now: a chat that stopped waiting takes its notice with it
  if (notice && chats.find((c) => c.chat_id === notice!.chatId)?.state !== notice.state) notice = undefined;
  answered = true;
  changed();
}

async function poll(own: number) {
  const response = await api("/briefs/activity").catch(() => undefined);
  const found = response?.ok ? ((await response.json().catch(() => undefined)) as { chats?: ChatActivity[] } | undefined) : undefined;
  if (own !== round) return;
  if (Array.isArray(found?.chats)) take(found.chats);
  timer = setTimeout(() => void poll(own), ACTIVITY_POLL.ms);
}

function start() {
  users += 1;
  if (users === 1) void poll(++round);
}

function stop() {
  users -= 1;
  if (users > 0) return;
  round += 1;
  clearTimeout(timer);
  chats = [];
  notice = undefined;
  heard = new Map();
  answered = false;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  start();
  return () => {
    listeners.delete(listener);
    stop();
  };
}

/** Every chat with something to show (the open chat's ended Brief is seen at once); polled while a screen listens. */
export function useActivity(): ChatActivity[] {
  return useSyncExternalStore(subscribe, () => chats);
}

/** The newest change in another chat (done, failed, now waiting), until it is opened, dismissed or no longer true. */
export function useActivityNotice(): ActivityNotice | undefined {
  return useSyncExternalStore(subscribe, () => notice);
}

export function dismissNotice() {
  notice = undefined;
  changed();
}

/** The chat on the screen: its ended mark clears, here and in the core, and its notice goes. */
export function useOpenChat(chatId: string) {
  useEffect(() => {
    openChat = chatId;
    const here = chats.find((c) => c.chat_id === chatId);
    if (here && ended(here.state)) seenInCore(chatId);
    chats = chats.filter((c) => !(c.chat_id === chatId && ended(c.state)));
    if (notice?.chatId === chatId) notice = undefined;
    changed();
  }, [chatId]);
}

/** One chat's state, if it has one. */
export function stateOf(list: ChatActivity[], chatId: string): ActivityState | undefined {
  return list.find((c) => c.chat_id === chatId)?.state;
}

/** The top bar's mark: the state that most needs the engineer, among every chat but `openChatId`. */
export function elsewhere(list: ChatActivity[], openChatId: string): ActivityState | undefined {
  const states = new Set(list.filter((c) => c.chat_id !== openChatId).map((c) => c.state));
  return RANK.find((state) => states.has(state));
}
