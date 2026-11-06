// The live team: what each agent is doing now and where (Plan 7 decision 7). Its own small store, built like
// i18n.ts, so a moving cursor never re-renders the frames: events are queued and applied once per animation frame,
// however many arrive, and each part of the screen reads only its own slice. Nothing here is kept on disk.
import { useCallback, useRef, useSyncExternalStore } from "react";
import { texts } from "../../i18n";
import type { ActivityEvent, AgentInfo, ProjectSources, Team } from "../types";

/** An agent as the screen shows it: `noNews` once it has been silent for a minute while working. */
export type LiveAgent = AgentInfo & { noNews: boolean };
/** A change worth saying: a new state, or silence. Moves are never changes. */
export type Change = { agent: LiveAgent; before: LiveAgent | null };

export const NO_NEWS_MS = 60_000;
const TICK_MS = 1000;

const busy = (a: AgentInfo) => a.state === "working" || a.state === "thinking";

// Before Plan 4 sends a Lead QS, the Lead QS is the chat itself: thinking while a reply streams (leadFromChat).
const chatLead = (state: "idle" | "thinking"): LiveAgent => ({
  id: "chat-lead",
  kind: "lead",
  role: texts.roleLead,
  desk_id: null,
  model: "",
  state,
  line: null,
  brief_id: null,
  focus: null,
  at: "",
  noNews: false,
});
const chatLeads = { idle: chatLead("idle"), thinking: chatLead("thinking") };

type Running = { sources: ProjectSources; controller: AbortController; starters: number; timer: ReturnType<typeof setInterval> };

let agents = new Map<string, LiveAgent>();
let desks = new Set<string>();
let waiting: number | null = null;
let leadState: "idle" | "thinking" = "idle";
let list: readonly LiveAgent[] = [chatLeads.idle];
const lastHeard = new Map<string, number>();
let queue: ActivityEvent[] = [];
let frame: number | undefined;
let running: Running | undefined;

const listeners = new Set<() => void>();
const changeListeners = new Set<(changes: Change[]) => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Called with what changed state after each batch of events (the Announcer). */
export function subscribeChanges(listener: (changes: Change[]) => void): () => void {
  changeListeners.add(listener);
  return () => changeListeners.delete(listener);
}

function publish(changes: Change[] = []) {
  const all = [...agents.values()];
  list = all.some((a) => a.kind === "lead") ? all : [chatLeads[leadState], ...all];
  for (const listener of [...listeners]) listener();
  if (changes.length) for (const listener of [...changeListeners]) listener(changes);
}

function live(agent: AgentInfo): LiveAgent {
  return { ...agent, noNews: false };
}

/** The team from the core; agents an event already told about since `since` keep the event's word. */
function applyTeam(team: Team, since: number) {
  const heard = new Set([...lastHeard].filter(([, at]) => at >= since).map(([id]) => id));
  desks = new Set(team.desks.map((d) => d.id));
  const next = new Map<string, LiveAgent>();
  const now = Date.now();
  for (const a of team.agents) {
    if (heard.has(a.id)) continue;
    next.set(a.id, live(a));
    lastHeard.set(a.id, now);
  }
  for (const [id, a] of agents) if (heard.has(id)) next.set(id, a);
  agents = next;
  publish();
}

function loadTeam(run: Running) {
  const since = Date.now();
  run.sources.team().then(
    (team) => {
      if (running === run && !run.controller.signal.aborted) applyTeam(team, since);
    },
    () => {}, // the team stays as it was; the next reconnect tries again
  );
}

function enqueue(event: ActivityEvent) {
  queue.push(event);
  frame ??= requestAnimationFrame(flush);
}

function flush() {
  frame = undefined;
  const events = queue;
  queue = [];
  if (!events.length) return;
  const before = new Map(agents);
  const now = Date.now();
  let touched = false;
  for (const event of events) {
    if (event.type === "agent") {
      agents.set(event.agent.id, live(event.agent));
      lastHeard.set(event.agent.id, now);
      touched = true;
    } else if (event.type === "agent-gone") {
      touched = agents.delete(event.id) || touched;
      lastHeard.set(event.id, now);
    } else if (event.type === "desk") {
      desks.add(event.desk.id);
      touched = true;
    } else if (event.type === "waiting") {
      waiting = event.count;
      touched = true;
    }
  }
  if (!touched) return;
  agents = new Map(agents);
  const changes: Change[] = [];
  for (const [id, agent] of agents) {
    const was = before.get(id) ?? null;
    if (was?.state !== agent.state) changes.push({ agent, before: was });
  }
  publish(changes);
}

function tick() {
  const now = Date.now();
  const changes: Change[] = [];
  for (const [id, agent] of agents) {
    if (agent.noNews || !busy(agent) || now - (lastHeard.get(id) ?? now) < NO_NEWS_MS) continue;
    const quiet = { ...agent, noNews: true };
    agents.set(id, quiet);
    changes.push({ agent: quiet, before: agent });
  }
  if (changes.length) {
    agents = new Map(agents);
    publish(changes);
  }
}

function reset() {
  if (frame !== undefined) cancelAnimationFrame(frame);
  frame = undefined;
  queue = [];
  agents = new Map();
  desks = new Set();
  waiting = null;
  lastHeard.clear();
  publish();
}

function stop(run: Running) {
  run.controller.abort();
  clearInterval(run.timer);
  if (running === run) {
    running = undefined;
    reset();
  }
}

/** Starts the live team of these sources until `signal` aborts; `team`, when the caller has just read it (the
 * canvas does), saves reading it again. Several parts of the screen may start the same sources: they share one
 * store, which stops when the last of them stops. Other sources replace the running ones. */
export function startActivity(sources: ProjectSources, signal: AbortSignal, team?: Team) {
  if (signal.aborted) return;
  if (running?.sources !== sources) {
    if (running) stop(running);
    reset();
    const controller = new AbortController();
    const run: Running = { sources, controller, starters: 0, timer: setInterval(tick, TICK_MS) };
    running = run;
    if (team) applyTeam(team, Date.now());
    else loadTeam(run);
    sources.activity(enqueue, controller.signal, () => loadTeam(run));
  }
  const run = running!;
  run.starters += 1;
  signal.addEventListener(
    "abort",
    () => {
      run.starters -= 1;
      if (run.starters === 0) stop(run);
    },
    { once: true },
  );
}

/** Before Plan 4 sends the team, the Lead QS shows the chat's status: thinking while a reply is on its way. */
export function leadFromChat(thinking: boolean) {
  const next = thinking ? "thinking" : "idle";
  if (next === leadState) return;
  leadState = next;
  publish();
}

// Hooks -----------------------------------------------------------------------------------------------------------

const getList = () => list;
const getWaiting = () => waiting;

/** Everyone on the team now, the Lead QS first when it comes from the chat. */
export function useAgents(): readonly LiveAgent[] {
  return useSyncExternalStore(subscribe, getList);
}

export function useAgent(id: string): LiveAgent | undefined {
  return useSyncExternalStore(
    subscribe,
    useCallback(() => agents.get(id), [id]),
  );
}

/** A derived list that keeps its identity while its items stay the same. */
function useDerived<T>(compute: () => readonly T[], deps: unknown[]): readonly T[] {
  const cache = useRef<readonly T[]>([]);
  const get = useCallback(() => {
    const next = compute();
    const old = cache.current;
    if (next.length === old.length && next.every((x, i) => x === old[i])) return old;
    cache.current = next;
    return next;
  }, deps);
  return useSyncExternalStore(subscribe, get);
}

/** The team frame's members: the Lead QS, the Checking QS, and any agent outside every known Desk. */
export function useTeamAgents(): readonly LiveAgent[] {
  return useDerived(() => list.filter((a) => a.desk_id === null || !desks.has(a.desk_id)), []);
}

export function useDeskAgents(deskId: string): readonly LiveAgent[] {
  return useDerived(() => list.filter((a) => a.desk_id === deskId && desks.has(deskId)), [deskId]);
}

/** Cards waiting for the engineer, from the live stream; null until it says. */
export function useWaiting(): number | null {
  return useSyncExternalStore(subscribe, getWaiting);
}
