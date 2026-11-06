import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { texts } from "../../i18n";
import { fakeSources } from "../fake";
import type { AgentInfo, Team } from "../types";
import {
  leadFromChat,
  NO_NEWS_MS,
  startActivity,
  subscribeChanges,
  useAgent,
  useAgents,
  useDeskAgents,
  useTeamAgents,
  useWaiting,
} from "./activity";

const agent = (id: string, fields: Partial<AgentInfo> = {}): AgentInfo => ({
  id,
  kind: "specialist",
  role: { en: `Estimator ${id} (sample)`, ar: `مهندس التسعير ${id} - عينة` },
  desk_id: "pricing",
  model: "claude-sonnet-5",
  state: "working",
  line: null,
  brief_id: "b1",
  focus: { frame: "deliverable:boq", anchor: null },
  at: "2026-11-05T09:00:00+00:00",
  ...fields,
});

const desk = { id: "pricing", name: { en: "Pricing Desk (sample)", ar: "قسم التسعير - عينة" }, stage: "temporary" as const };

/** Starts the store on fake sources; the returned stop ends it. */
function start(team: Team = { desks: [desk], agents: [] }) {
  const fake = fakeSources({ team });
  const controller = new AbortController();
  startActivity(fake, controller.signal);
  return { fake, stop: () => act(() => controller.abort()) };
}

/** Waits for the store's team load and one animation frame of events. */
const settle = () => act(async () => {
  await Promise.resolve();
  await new Promise((r) => requestAnimationFrame(() => r(undefined)));
});

describe("the live store", () => {
  let stops: (() => void)[] = [];
  beforeEach(() => {
    stops = [];
  });
  afterEach(() => {
    for (const stop of stops) stop();
    vi.useRealTimers();
    leadFromChat(false);
  });

  it("loads the team when it starts and clears it when it stops", async () => {
    const run = start({ desks: [desk], agents: [agent("est")] });
    const { result } = renderHook(() => useAgents());
    await settle();
    expect(result.current.map((a) => a.id)).toContain("est");
    run.stop();
    expect(result.current.map((a) => a.id)).not.toContain("est");
  });

  it("applies many events in one animation frame, with one render", async () => {
    const run = start();
    stops.push(run.stop);
    await settle();
    let renders = 0;
    const { result } = renderHook(() => {
      renders += 1;
      return useAgent("est");
    });
    const before = renders;
    act(() => {
      for (let i = 0; i < 100; i++)
        run.fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "deliverable:boq", anchor: { row: `3/${i}` } } }) });
    });
    expect(result.current).toBeUndefined(); // queued, not applied yet
    await settle();
    expect(result.current?.focus?.anchor).toEqual({ row: "3/99" });
    expect(renders - before).toBe(1);
  });

  it("a finished agent is done; a gone one leaves the team", async () => {
    const run = start({ desks: [desk], agents: [agent("est")] });
    stops.push(run.stop);
    await settle();
    act(() => run.fake.emit({ type: "agent", agent: agent("est", { state: "done" }) }));
    await settle();
    const team = renderHook(() => useDeskAgents("pricing"));
    expect(team.result.current.map((a) => a.state)).toEqual(["done"]);
    act(() => run.fake.emit({ type: "agent-gone", id: "est" }));
    await settle();
    expect(team.result.current).toEqual([]);
  });

  it("a silent working agent turns to no news after 60 s; a new event clears it", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval", "Date", "requestAnimationFrame", "cancelAnimationFrame"] });
    const run = start({ desks: [desk], agents: [agent("est"), agent("wait", { state: "waiting" })] });
    stops.push(run.stop);
    await act(async () => {
      await Promise.resolve();
    });
    const { result } = renderHook(() => [useAgent("est"), useAgent("wait")] as const);
    act(() => vi.advanceTimersByTime(NO_NEWS_MS - 1000));
    expect(result.current[0]?.noNews).toBe(false);
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current[0]?.noNews).toBe(true);
    expect(result.current[0]?.focus).not.toBeNull(); // it still points where it was
    expect(result.current[1]?.noNews).toBe(false); // waiting for the engineer is not silence
    act(() => {
      run.fake.emit({ type: "agent", agent: agent("est") });
      vi.advanceTimersByTime(16);
    });
    expect(result.current[0]?.noNews).toBe(false);
  });

  it("tells listeners what changed state, not what only moved", async () => {
    const run = start({ desks: [desk], agents: [agent("est")] });
    stops.push(run.stop);
    await settle();
    const seen: string[] = [];
    const off = subscribeChanges((changes) => seen.push(...changes.map((c) => `${c.agent.id}:${c.before?.state}>${c.agent.state}`)));
    act(() => run.fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "deliverable:other", anchor: null } }) }));
    await settle();
    expect(seen).toEqual([]);
    act(() => run.fake.emit({ type: "agent", agent: agent("est", { state: "waiting" }) }));
    await settle();
    expect(seen).toEqual(["est:working>waiting"]);
    off();
  });

  it("before Plan 4: the Lead QS follows the chat's status", async () => {
    const run = start();
    stops.push(run.stop);
    await settle();
    const { result } = renderHook(() => useTeamAgents());
    const lead = () => result.current.find((a) => a.kind === "lead");
    expect(lead()).toMatchObject({ state: "idle", role: texts.roleLead });
    act(() => leadFromChat(true));
    expect(lead()?.state).toBe("thinking");
    act(() => leadFromChat(false));
    expect(lead()?.state).toBe("idle");
  });

  it("a real Lead QS from the core wins over the chat's status", async () => {
    const run = start({ desks: [], agents: [agent("lead1", { kind: "lead", desk_id: null, state: "working", focus: null })] });
    stops.push(run.stop);
    await settle();
    const { result } = renderHook(() => useTeamAgents());
    act(() => leadFromChat(true));
    expect(result.current.filter((a) => a.kind === "lead").map((a) => [a.id, a.state])).toEqual([["lead1", "working"]]);
  });

  it("agents outside every known Desk sit in the team", async () => {
    const run = start({ desks: [desk], agents: [agent("est"), agent("lost", { desk_id: "gone" })] });
    stops.push(run.stop);
    await settle();
    const { result } = renderHook(() => useTeamAgents());
    expect(result.current.map((a) => a.id)).toContain("lost");
    expect(result.current.map((a) => a.id)).not.toContain("est");
  });

  it("counts the cards waiting for the engineer", async () => {
    const run = start();
    stops.push(run.stop);
    const { result } = renderHook(() => useWaiting());
    expect(result.current).toBeNull();
    act(() => run.fake.emit({ type: "waiting", count: 2 }));
    await settle();
    expect(result.current).toBe(2);
  });

  it("reloads the team after the stream comes back", async () => {
    const run = start({ desks: [desk], agents: [] });
    stops.push(run.stop);
    await settle();
    vi.spyOn(run.fake, "team").mockResolvedValueOnce({ desks: [desk], agents: [agent("est")] });
    act(() => run.fake.reconnect());
    await settle();
    const { result } = renderHook(() => useDeskAgents("pricing"));
    expect(result.current.map((a) => a.id)).toEqual(["est"]);
  });

  it("an event that comes before the team answers is not overwritten by it", async () => {
    const run = start({ desks: [desk], agents: [agent("est", { state: "working" })] });
    stops.push(run.stop);
    act(() => run.fake.emit({ type: "agent", agent: agent("est", { state: "waiting" }) }));
    await settle();
    await settle();
    const { result } = renderHook(() => useAgent("est"));
    expect(result.current?.state).toBe("waiting");
  });

  it("two starters on the same sources share one store; it stops when both stop", async () => {
    const fake = fakeSources({ team: { desks: [desk], agents: [agent("est")] } });
    const a = new AbortController();
    const b = new AbortController();
    startActivity(fake, a.signal);
    startActivity(fake, b.signal);
    await settle();
    const { result } = renderHook(() => useAgent("est"));
    act(() => a.abort());
    expect(result.current).toBeDefined();
    act(() => b.abort());
    expect(result.current).toBeUndefined();
  });
});
