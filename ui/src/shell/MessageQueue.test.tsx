// The message queue while ONE works: Enter queues a message instead of interrupting, Ctrl/⌘+Enter steers the Brief
// now, the next queued message goes by itself when the Brief ends, Stop pauses the queue, and the queue survives a
// reload. Against the shell with a mocked core, as the other shell tests.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { bodyOf, calls, core, reply } from "./testing";

vi.mock("../workspace/Workspace", async () => ({ Workspace: (await import("./testing")).WorkspaceStandIn, DocumentHead: () => null }));

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
const queueRegion = () => screen.queryByRole("list", { name: texts.queueLabel.ar });
const sentTexts = (fetch: ReturnType<typeof core>) =>
  calls(fetch, "POST", "/api/chat").map(([, init]) => (bodyOf(init) as { messages: { parts: { text: string }[] }[] }).messages[0]!.parts[0]!.text);

/** A Brief that runs until the test ends it: its reply streams, then waits; `end()` says it is done. */
function briefs() {
  const open: { end: () => void }[] = [];
  const route = (init: RequestInit) => {
    const n = open.length + 1;
    const encoder = new TextEncoder();
    const chunk = (c: object) => encoder.encode(`data: ${JSON.stringify(c)}\n\n`);
    let control!: ReadableStreamDefaultController<Uint8Array>;
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        control = c;
        for (const part of [...reply.slice(0, 4), { type: "data-status", id: `b${n}`, data: { state: "running", step: null } }])
          c.enqueue(chunk(part));
        init.signal?.addEventListener("abort", () => c.error(new DOMException("aborted", "AbortError")));
      },
    });
    open.push({
      end: () => {
        control.enqueue(chunk({ type: "data-status", id: `b${n}`, data: { state: "done", step: null } }));
        for (const part of reply.slice(5)) control.enqueue(chunk(part));
        control.enqueue(encoder.encode("data: [DONE]\n\n"));
        control.close();
      },
    });
    return new Response(body, { headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" } });
  };
  return { route, end: (i: number) => act(() => open[i]!.end()), count: () => open.length };
}

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("the message queue", () => {
  it("Enter sends when ONE is idle, and queues while a Brief runs; the queue shows above the box", async () => {
    const run = briefs();
    const fetch = core({ routes: { "POST /api/chat": run.route, "POST /api/briefs/b1/steer": () => new Response(null, { status: 202 }) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر الخرسانة - عينة{enter}");
    await screen.findByText(/مرحبا/);
    expect(sentTexts(fetch)).toEqual(["سعّر الخرسانة - عينة"]);

    await user.type(await box(), "بعدين الكهرباء - عينة{enter}");
    await user.type(await box(), "وبعدين الصحي - عينة{enter}");
    expect(await box()).toHaveValue("");
    expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(0); // not steering
    expect(sentTexts(fetch)).toHaveLength(1);
    const list = queueRegion()!;
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText(fill(texts.queueCount.ar, { n: 2 }))).toBeInTheDocument();
  });

  it("Ctrl+Enter (or ⌘+Enter) steers the running Brief now, as sending did", async () => {
    const run = briefs();
    const fetch = core({ routes: { "POST /api/chat": run.route, "POST /api/briefs/b1/steer": () => new Response(null, { status: 202 }) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر - عينة{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "استخدم أسعار الشهر ده");
    await user.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(1));
    expect(bodyOf(calls(fetch, "POST", "/api/briefs/b1/steer")[0]![1])).toEqual({ text: "استخدم أسعار الشهر ده" });
    const bubble = (await screen.findByText("استخدم أسعار الشهر ده")).closest("li")!;
    expect(within(bubble).getByText(texts.steering.ar)).toBeInTheDocument();
    await user.type(await box(), "كمان");
    await user.keyboard("{Meta>}{Enter}{/Meta}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(2));
    expect(queueRegion()).toBeNull();
  });

  it("when the Brief ends, the next queued message goes by itself, one at a time", async () => {
    const run = briefs();
    const fetch = core({ routes: { "POST /api/chat": run.route } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "أول - عينة{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "تاني - عينة{enter}");
    await user.type(await box(), "تالت - عينة{enter}");
    run.end(0);
    await waitFor(() => expect(sentTexts(fetch)).toEqual(["أول - عينة", "تاني - عينة"]));
    expect(within(queueRegion()!).getAllByRole("listitem")).toHaveLength(1);
    await waitFor(() => expect(run.count()).toBe(2));
    run.end(1);
    await waitFor(() => expect(sentTexts(fetch)).toEqual(["أول - عينة", "تاني - عينة", "تالت - عينة"]));
    await waitFor(() => expect(queueRegion()).toBeNull());
  });

  it("Stop pauses the queue rather than clearing it; «كمّل الطابور» sends the next", async () => {
    const run = briefs();
    const fetch = core({ routes: { "POST /api/chat": run.route, "POST /api/briefs/b1/stop": () => Response.json({ state: "stopped" }) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "أول - عينة{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "تاني - عينة{enter}");
    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/stop")).toHaveLength(1));
    expect(within(queueRegion()!).getAllByRole("listitem")).toHaveLength(1);
    expect(sentTexts(fetch)).toHaveLength(1);
    await user.click(await screen.findByRole("button", { name: texts.queueResume.ar }));
    await waitFor(() => expect(sentTexts(fetch)).toEqual(["أول - عينة", "تاني - عينة"]));
    await waitFor(() => expect(queueRegion()).toBeNull());
  });

  it("each queued message can be removed or edited in place", async () => {
    const run = briefs();
    const fetch = core({ routes: { "POST /api/chat": run.route } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "أول - عينة{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "تاني - عينة{enter}");
    await user.type(await box(), "تالت - عينة{enter}");
    await user.click(screen.getByRole("button", { name: fill(texts.queueRemove.ar, { text: "تاني - عينة" }) }));
    expect(within(queueRegion()!).getAllByRole("listitem")).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: fill(texts.queueEdit.ar, { text: "تالت - عينة" }) }));
    const field = screen.getByRole("textbox", { name: texts.queueEditField.ar });
    await user.clear(field);
    await user.type(field, "الصحي بس - عينة{enter}"); // saved as typed; Enter closes the field
    expect(within(queueRegion()!).getByText("الصحي بس - عينة")).toBeInTheDocument();
    run.end(0);
    await waitFor(() => expect(sentTexts(fetch)).toEqual(["أول - عينة", "الصحي بس - عينة"]));
  });

  it("the queue survives a reload; with nothing running, «كمّل الطابور» sends it", async () => {
    const run = briefs();
    const fetch = core({ routes: { "POST /api/chat": run.route } });
    const user = userEvent.setup();
    const first = render(<App />);
    await user.type(await box(), "أول - عينة{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "تاني - عينة{enter}");
    first.unmount();

    render(<App />);
    await box();
    expect(within(queueRegion()!).getByText("تاني - عينة")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: texts.queueResume.ar }));
    await waitFor(() => expect(sentTexts(fetch)).toEqual(["أول - عينة", "تاني - عينة"]));
  });

  it("the first queued message shows «Ctrl+Enter يقاطع ONE» once under the box; never again after", async () => {
    const run = briefs();
    core({ routes: { "POST /api/chat": run.route } });
    const user = userEvent.setup();
    const first = render(<App />);
    await user.type(await box(), "أول - عينة{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "تاني - عينة{enter}");
    expect(screen.getByText(fill(texts.queueHint.ar, { keys: "Ctrl+Enter" }))).toBeInTheDocument();
    first.unmount();
    render(<App />);
    await box();
    expect(screen.queryByText(fill(texts.queueHint.ar, { keys: "Ctrl+Enter" }))).toBeNull();
  });
});
