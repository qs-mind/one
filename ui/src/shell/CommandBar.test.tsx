// The command bar: the one composer. It sends the selection with the message, and every action in it becomes a
// message to the Lead QS.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { select } from "../canvas/selection";
import { fill, setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { bodyOf, calls, core, P1, reply, running, streamed } from "./testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }));

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
/** Matches the element whose whole text is `text` (the name inside it is its own <bdi>). */
const whole = (text: string) => (_: string, el: Element | null) => el?.textContent === text && el.tagName === "SPAN";
const pricing = { kind: "deliverable" as const, id: "d1", title: "تسعير المقايسة - عينة", label: "البنود 3/01–3/04" };

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(P1);
  select([]);
});

describe("CommandBar", () => {
  it("shows the selection and sends it with the message; the user message keeps it as a chip", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await box();
    act(() => select([pricing]));
    const bar = screen.getByRole("region", { name: texts.commandBar.ar });
    const chip = fill(texts.selected.ar, { name: "تسعير المقايسة - عينة، البنود 3/01–3/04" });
    expect(within(bar).getByText(whole(chip))).toBeInTheDocument();
    expect(await box()).toHaveAttribute("placeholder", texts.commandBox.ar);

    await user.type(await box(), "سعّرها{enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1));
    const body = bodyOf(calls(fetch, "POST", "/api/chat")[0]![1]) as {
      id: string;
      selection: unknown;
      messages: { metadata?: { selection?: unknown } }[];
    };
    expect(body.id).toBe("p1");
    expect(body.selection).toEqual([pricing]);
    expect(body.messages[0]!.metadata?.selection).toEqual([pricing]);
    const bubble = (await screen.findByText("سعّرها")).closest("li")!;
    expect(within(bubble).getByText(whole(chip))).toBeInTheDocument();
  });

  it("several frames selected say how many, and ✕ clears the selection", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    await box();
    act(() => select([pricing, { kind: "file", id: "f1", title: "مواصفات - عينة.pdf" }, { kind: "files", id: "all", title: "ملفات المشروع" }]));
    expect(screen.getByText(fill(texts.selectedMany.ar, { n: 3 }))).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.clearSelection.ar }));
    expect(screen.queryByText(fill(texts.selectedMany.ar, { n: 3 }))).toBeNull();
    expect(await box()).toHaveAttribute("placeholder", texts.commandBoxEmpty.ar);
  });

  it("a quick action only sends a message to the Lead QS, with the selection", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await box();
    act(() => select([pricing]));
    expect(screen.queryByRole("button", { name: texts.actionAskFile.ar })).toBeNull(); // a file's action
    await user.click(screen.getByRole("button", { name: texts.actionCheck.ar }));
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1));
    const body = bodyOf(calls(fetch, "POST", "/api/chat")[0]![1]) as { selection: unknown; messages: { parts: { text: string }[] }[] };
    expect(body.messages[0]!.parts[0]!.text).toBe(texts.actionCheck.ar);
    expect(body.selection).toEqual([pricing]);
    expect(fetch.mock.calls.every(([url]) => !String(url).includes("/agents/"))).toBe(true); // never an agent directly
  });

  it("each selection kind has its own actions", async () => {
    core();
    render(<App />);
    await box();
    act(() => select([{ kind: "file", id: "f1", title: "مواصفات - عينة.pdf" }]));
    expect(screen.getByRole("button", { name: texts.actionAskFile.ar })).toBeInTheDocument();
    act(() => select([{ kind: "desk", id: "pricing", title: "قسم التسعير - عينة" }]));
    expect(screen.getByRole("button", { name: texts.actionSaveDesk.ar })).toBeInTheDocument();
    act(() => select([{ kind: "agent", id: "est", title: "مهندس التسعير - عينة" }]));
    expect(screen.getByRole("button", { name: texts.actionWhatDoing.ar })).toBeInTheDocument();
  });

  it("sending opens the chat panel", async () => {
    core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.closeChat.ar }));
    expect(screen.queryByRole("log")).toBeNull();
    await user.type(await box(), "سعّر{enter}");
    expect(await screen.findByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument();
  });

  it("Stop ends the reply and the box is ready again", async () => {
    const signals: AbortSignal[] = [];
    core({
      routes: {
        "POST /api/chat": (init) => {
          signals.push(init.signal!);
          return streamed(reply.slice(0, 4), init, false);
        },
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "hello{enter}");
    await screen.findByText(/مرحبا/);

    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    expect(signals[0]!.aborted).toBe(true); // no request is left running
    expect(await screen.findByRole("button", { name: texts.send.ar })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: texts.message.ar }), "again{enter}");
    await waitFor(() => expect(signals).toHaveLength(2));
  });

  it("a steer the core refuses puts the text back in the box", async () => {
    core({
      routes: {
        "POST /api/chat": (init) => streamed([...reply.slice(0, 4), running], init, false),
        "POST /api/briefs/b1/steer": () => Response.json({ error: { en: "Not running.", ar: "مش شغال." } }, { status: 409 }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    await screen.findByText(/مرحبا/);
    await user.type(await box(), "كمان{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("مش شغال.");
    expect(await box()).toHaveValue("كمان");
  });

  it("/ on the canvas goes to the command bar, also with the Arabic layout", async () => {
    core();
    render(<App />);
    await box();
    const frame = screen.getByRole("button", { name: "frame" });
    frame.focus();
    fireEvent.keyDown(frame, { code: "Slash", key: "ظ" });
    expect(await box()).toHaveFocus();
  });

  it("rests as a pill and opens on focus: the model and effort show only then; Escape folds it", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    const field = await box();
    const composer = field.closest("[data-composer]")!;
    expect(composer).not.toHaveAttribute("data-open");
    await user.click(field);
    expect(composer).toHaveAttribute("data-open");
    const model = await screen.findByRole("button", { name: fill(texts.modelChip.ar, { name: "Claude Opus 5.5" }) });
    expect(model).toBeVisible();
    await user.keyboard("{Escape}");
    expect(composer).not.toHaveAttribute("data-open");
    expect(field).toHaveFocus(); // folded, not left
    await user.type(field, "x");
    expect(composer).toHaveAttribute("data-open");
  });

  it("the effort moves straight to the next level on each click, with no list, and goes with the message", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await box());
    const level = (now: string, next: string) =>
      fill(texts.effortChip.ar, { level: texts[`effort${now}` as "efforthigh"].ar, next: texts[`effort${next}` as "effortlow"].ar });
    // Claude's own default is High: shown, but nothing is sent until the engineer picks
    await user.click(await screen.findByRole("button", { name: level("high", "low") }));
    expect(screen.queryByRole("menu")).toBeNull();
    await user.click(screen.getByRole("button", { name: level("low", "medium") }));
    expect(screen.getByRole("button", { name: level("medium", "high") })).toBeInTheDocument();
    await user.type(await box(), "سعّر{enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1));
    const body = bodyOf(calls(fetch, "POST", "/api/chat")[0]![1]);
    expect(body.effort).toBe("medium");
    expect(body.model).toBeUndefined(); // not picked: the core's own choice stands
  });

  it("the model card lists the models from the core; a pick goes with the message, and a model with no effort hides it", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await box());
    await user.click(await screen.findByRole("button", { name: fill(texts.modelChip.ar, { name: "Claude Opus 5.5" }) }));
    const menu = await screen.findByRole("menu", { name: texts.models.ar });
    const items = within(menu).getAllByRole("menuitemradio");
    expect(items.map((item) => item.textContent)).toEqual(["Claude Opus 5.5", "Claude Haiku (sample)"]);
    expect(items[0]).toHaveAttribute("aria-checked", "true");
    expect(items[0]).toHaveFocus();
    await user.keyboard("{ArrowDown}{Enter}");
    expect(screen.queryByRole("menu")).toBeNull();
    expect(screen.getByRole("button", { name: fill(texts.modelChip.ar, { name: "Claude Haiku (sample)" }) })).toHaveFocus();
    expect(screen.queryByRole("button", { name: /^عمق التفكير/ })).toBeNull();
    await user.type(await box(), "سعّر{enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1));
    const body = bodyOf(calls(fetch, "POST", "/api/chat")[0]![1]);
    expect(body.model).toEqual({ connector: "anthropic", model: "claude-haiku-sample" });
    expect(body.effort).toBeUndefined();
  });

  it("typing in Arabic while composing (IME) does not send on Enter", async () => {
    const fetch = core();
    render(<App />);
    const field = await box();
    fireEvent.change(field, { target: { value: "سعّر" } });
    fireEvent.keyDown(field, { key: "Enter", code: "Enter", isComposing: true });
    expect(calls(fetch, "POST", "/api/chat")).toHaveLength(0);
  });
});
