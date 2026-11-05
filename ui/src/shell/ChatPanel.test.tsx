// Plan 4's chat, as the shell wraps it: the General chat and a project's floating chat. Moved from Chat.test.tsx;
// every behaviour there still holds, with the command bar as the composer.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { canvasApi } from "../canvas/api";
import { D, entry, sheet } from "../deliverables/fixtures";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { bodyOf, calls, core, P1, reply, running, streamed } from "./testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }));

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
/** A reply's paragraph by its whole text (its English runs sit in their own <bdi>). */
const findReply = (text: RegExp) => screen.findByText((_, el) => el?.tagName === "P" && text.test(el.textContent ?? ""));

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("the chat in the shell", () => {
  it("streams the reply and sends only the new message, under the chat's id", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر البند ده{enter}");

    const answer = await findReply(/مرحبا Hello/);
    expect(answer.closest("[dir]")).toHaveAttribute("dir", "auto"); // mixed Arabic and English lines render right
    expect(screen.getByText("سعّر البند ده")).toBeInTheDocument();
    const [, init] = calls(fetch, "POST", "/api/chat")[0]!;
    const body = bodyOf(init) as { id: string; messages: { parts: { text: string }[] }[] };
    expect(body.id).toBe("general");
    expect(body.messages).toHaveLength(1);
    expect(body.messages[0]!.parts[0]!.text).toBe("سعّر البند ده");
  });

  it("a project's chat has the project's id, and floats beside the canvas", async () => {
    setCurrentProject(P1);
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await waitFor(() => expect(calls(fetch, "GET", "/api/chat/p1/messages")).toHaveLength(1));
    expect(screen.getByRole("region", { name: "canvas stand-in" })).toBeInTheDocument();
    expect(screen.getByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument();
    await user.type(await box(), "hello{enter}");
    await screen.findByText(/مرحبا/);
    const [, init] = calls(fetch, "POST", "/api/chat")[0]!;
    expect(bodyOf(init).id).toBe("p1");
  });

  it("Enter sends, Shift+Enter starts a new line", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سطر{Shift>}{Enter}{/Shift}تاني");
    expect(calls(fetch, "POST", "/api/chat")).toHaveLength(0);
    expect(await box()).toHaveValue("سطر\nتاني");
    await user.keyboard("{Enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1));
  });

  it("stop posts the Brief's stop call and the box is ready", async () => {
    const signals: AbortSignal[] = [];
    const fetch = core({
      routes: {
        "POST /api/chat": (init) => {
          signals.push(init.signal!);
          return streamed([...reply.slice(0, 4), running], init, false);
        },
        "POST /api/briefs/b1/stop": () => Response.json({ state: "stopped" }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر البنود - عينة{enter}");
    await screen.findByText(/مرحبا/);

    await user.click(screen.getByRole("button", { name: texts.stop.ar }));
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/stop")).toHaveLength(1));
    expect(signals[0]!.aborted).toBe(true);
    expect(await screen.findByRole("button", { name: texts.send.ar })).toBeInTheDocument();

    await user.type(screen.getByRole("textbox", { name: texts.message.ar }), "again{enter}");
    await waitFor(() => expect(signals).toHaveLength(2)); // a new Brief, not steering the stopped one
    expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(0);
  });

  it("sending while a Brief runs steers it, and shows it as steering", async () => {
    const fetch = core({
      routes: {
        "POST /api/chat": (init) => streamed([...reply.slice(0, 4), running], init, false),
        "POST /api/briefs/b1/steer": () => new Response(null, { status: 202 }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر البنود - عينة{enter}");
    await screen.findByText(/مرحبا/);

    const field = screen.getByRole("textbox", { name: texts.message.ar });
    expect(field).toBeEnabled();
    await user.type(field, "استخدم أسعار الشهر ده{enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/briefs/b1/steer")).toHaveLength(1));
    const [, init] = calls(fetch, "POST", "/api/briefs/b1/steer")[0]!;
    expect(bodyOf(init)).toEqual({ text: "استخدم أسعار الشهر ده" });
    const bubble = (await screen.findByText("استخدم أسعار الشهر ده")).closest("li")!;
    expect(within(bubble).getByText(texts.steering.ar)).toBeInTheDocument();
    expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1);
  });

  it("a message to a chat whose Brief runs elsewhere steers that Brief and joins its stream", async () => {
    let joined = false;
    const fetch = core({
      routes: {
        "POST /api/chat": () => Response.json({ brief_id: "b9" }, { status: 409 }),
        "POST /api/briefs/b9/steer": () => {
          joined = true;
          return new Response(null, { status: 202 });
        },
        "GET /api/chat/general/stream": (init) => (joined ? streamed(reply, init) : new Response(null, { status: 204 })),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "كمان بند 04/01{enter}");
    expect(await findReply(/مرحبا Hello/)).toBeInTheDocument();
    const [, init] = calls(fetch, "POST", "/api/briefs/b9/steer")[0]!;
    expect(bodyOf(init)).toEqual({ text: "كمان بند 04/01" });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows the Progress Line, the team's messages, cards, costs and the Review code", async () => {
    const progress = (text: string) => ({
      type: "data-progress",
      id: "run-1",
      data: { agent: { en: "Estimator", ar: "مهندس التسعير" }, text: { en: text, ar: text } },
    });
    const parts = [
      reply[0]!,
      progress("بيقرا صفحة 3"),
      progress("بيقرا صفحة 12"),
      { type: "data-team", id: "tm1", data: { sender: { en: "Lead QS", ar: "كبير مهندسي الكميات" }, recipient: { en: "Estimator", ar: "مهندس التسعير" }, text: "سعّر بند 03/02" } },
      { type: "data-card", id: "c1", data: { kind: "outside", title: { en: "Send?", ar: "نبعت؟" }, detail: { en: "Lead QS: emailing the BOQ.", ar: "كبير مهندسي الكميات: بيبعت المقايسة بالإيميل." }, options: ["yes", "no"], status: "pending" } },
      { type: "data-cost", id: "brief", data: { level: "info", scope: "brief", spent: "1.20", cap: "3.00", equivalent: false, text: { en: "1.20 of 3.00 USD", ar: "1.20 من 3.00 دولار" } } },
      { type: "data-review", id: "d1", data: { code: "B", comments: [{ about: "03/02", text: "quote is old" }], same_provider: false } },
      ...reply.slice(1),
    ];
    core({ routes: { "POST /api/chat": (init) => streamed(parts, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر{enter}");
    const line = await screen.findByRole("list", { name: texts.progressLine.ar });
    expect(within(line).getByRole("listitem")).toHaveTextContent("بيقرا صفحة 12");
    expect(await screen.findByText("غرفة التنسيق، رسالة واحدة")).toBeInTheDocument();
    expect(screen.getByText("كبير مهندسي الكميات: بيبعت المقايسة بالإيميل.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.allowOnce.ar })).toBeInTheDocument();
    expect(screen.getByText("1.20 من 3.00 دولار")).toBeInTheDocument();
    expect(screen.getByText(texts.codeB.ar)).toBeInTheDocument();
  });

  it("marks unsourced numbers; the reply's Markdown shows, the engineer's own message stays plain", async () => {
    const parts = [
      reply[0]!,
      { type: "text-start", id: "t1" },
      { type: "text-delta", id: "t1", delta: "The **total** is 7,500 EGP from 39,850.50 EGP" },
      { type: "text-end", id: "t1" },
      { type: "data-unsourced", id: "u1", data: { values: ["7,500"] } },
      { type: "finish" },
    ];
    core({ routes: { "POST /api/chat": (init) => streamed(parts, init) } });
    const user = userEvent.setup();
    const { container } = render(<App />);
    await user.type(await box(), "**as typed**{enter}");
    await screen.findByText(texts.noSourceNote.ar);
    expect([...container.querySelectorAll("mark")].map((mark) => mark.textContent)).toEqual(["7,500"]);
    expect(screen.getByText("total").tagName).toBe("STRONG");
    expect(screen.getByText("**as typed**")).toBeInTheDocument();
  });

  it("loads earlier messages when the chat opens, and joins a Brief still running", async () => {
    const earlier = [
      { id: "u1", role: "user", parts: [{ type: "text", text: "سعّر بند الخرسانة - عينة" }] },
      { id: "a1", role: "assistant", parts: [{ type: "text", text: "Done." }, { type: "data-review", id: "d1", data: { code: "A", comments: [], same_provider: false } }] },
      { id: "u2", role: "user", parts: [{ type: "text", text: "والحديد؟" }] },
    ];
    const live = [{ type: "start", messageId: "a2" }, running, ...reply.slice(2, 5)];
    const fetch = core({
      routes: {
        "GET /api/chat/general/messages": () => Response.json({ messages: earlier }),
        "GET /api/chat/general/stream": (init) => streamed(live, init, false),
      },
    });
    render(<App />);
    expect(await screen.findByText("سعّر بند الخرسانة - عينة")).toBeInTheDocument();
    expect(screen.getByText(texts.codeA.ar)).toBeInTheDocument();
    expect(await findReply(/مرحبا Hello/)).toBeInTheDocument();
    const items = screen.getAllByRole("listitem").map((item) => item.textContent);
    expect(items.findIndex((text) => text?.includes("والحديد؟"))).toBeLessThan(
      items.findIndex((text) => text?.includes("مرحبا Hello")),
    );
    expect(screen.getByRole("button", { name: texts.stop.ar })).toBeInTheDocument(); // the Brief runs
    expect(calls(fetch, "GET", "/api/chat/general/stream")).toHaveLength(1);
  });

  it("offers to continue an unfinished Brief, and continues only on press", async () => {
    let continued = false;
    const fetch = core({
      routes: {
        "GET /api/briefs/unfinished": () =>
          Response.json({
            briefs: continued
              ? []
              : [{ id: "b1", chat_id: "general", project_name: null, step: { en: "pricing", ar: "بيسعّر البنود" }, state: "running" }],
          }),
        "POST /api/briefs/b1/continue": () => {
          continued = true;
          return Response.json({ state: "running" });
        },
        "GET /api/chat/general/stream": (init) => (continued ? streamed(reply, init) : new Response(null, { status: 204 })),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText("التكليف ده وقف عند: بيسعّر البنود. نكمّله؟")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls(fetch, "POST", "/api/briefs/b1/continue")).toHaveLength(0); // never by itself

    await user.click(screen.getByRole("button", { name: texts.continue.ar }));
    expect(await findReply(/مرحبا Hello/)).toBeInTheDocument(); // its stream joined
    expect(calls(fetch, "POST", "/api/briefs/b1/continue")).toHaveLength(1);
  });

  it("shows a plain line when the reply fails, and the core's {en, ar} line in the engineer's language", async () => {
    const refused = {
      en: "The Claude key was refused. Check it, or add a new one.",
      ar: "مفتاح Claude اترفض. راجعه، أو ضيف مفتاح جديد.",
    };
    let first = true;
    core({
      routes: {
        "POST /api/chat": (init) => {
          if (first) {
            first = false;
            return new Response("boom", { status: 500 });
          }
          return streamed([...reply.slice(0, 2), { type: "error", errorText: JSON.stringify(refused) }], init);
        },
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "hello{enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(texts.chatError.ar);

    await user.type(await box(), "again{enter}");
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(refused.ar));
    await user.click(screen.getByRole("button", { name: texts.otherLanguage.ar }));
    expect(screen.getByRole("alert")).toHaveTextContent(refused.en);
  });

  it("no AI connected: AI settings show in place of the chat, in both languages", async () => {
    core({ keySet: false });
    const { unmount } = render(<App />);
    expect(await screen.findByRole("heading", { name: texts.aiTitle.ar })).toBeInTheDocument();
    expect(screen.getByText(texts.noAiYet.ar)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: texts.message.ar })).not.toBeInTheDocument();
    unmount();

    setLanguage("en");
    render(<App />);
    expect(await screen.findByRole("heading", { name: texts.aiTitle.en })).toBeInTheDocument();
  });

  it("saving the first key stores it in the core, shows only that it was added, and opens the chat", async () => {
    const fetch = core({ keySet: false });
    const user = userEvent.setup();
    render(<App />);
    const field = await screen.findByLabelText(texts.aiKeyLabel.ar);
    expect(field).toHaveAttribute("type", "password");
    await user.type(field, "sk-ant-test");
    await user.click(screen.getByRole("button", { name: texts.save.ar }));

    expect(await screen.findByText(texts.keyAdded.ar)).toBeInTheDocument();
    expect(screen.queryByDisplayValue("sk-ant-test")).not.toBeInTheDocument();
    expect(await box()).toBeInTheDocument(); // the chat is open now
    const [, init] = calls(fetch, "PUT", "/api/settings/ai-key")[0]!;
    expect(bodyOf(init)).toEqual({ provider: "anthropic", value: "sk-ant-test" });
  });

  it("“AI” opens its one settings panel while the chat stays, and closes again", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.ai.ar }));
    const panel = await screen.findByRole("region", { name: texts.aiTitle.ar });
    expect(await within(panel).findByRole("combobox", { name: texts.roleLead.ar })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: texts.message.ar })).toBeInTheDocument();
    expect(screen.getAllByRole("region", { name: texts.aiTitle.ar })).toHaveLength(1);
    await user.click(within(panel).getByRole("button", { name: texts.close.ar }));
    expect(screen.queryByRole("region", { name: texts.aiTitle.ar })).not.toBeInTheDocument();
  });

  it("switches the language from the top bar; the chrome mirrors", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.otherLanguage.ar }));
    expect(document.documentElement.dir).toBe("ltr");
    expect(await screen.findByRole("button", { name: texts.send.en })).toBeInTheDocument();
  });

  it("a Deliverable card's Open focuses its frame on the canvas", async () => {
    setCurrentProject(P1);
    const parts = [reply[0]!, { type: "data-deliverable", id: D, data: { id: D } }, ...reply.slice(1)];
    core({
      routes: {
        "POST /api/chat": (init) => streamed(parts, init),
        "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }),
      },
    });
    vi.spyOn(canvasApi, "frames").mockReturnValue([{ key: `deliverable:${D}`, x: 0, y: 0, w: 960, h: 640, z: 0, collapsed: false }]);
    const focus = vi.spyOn(canvasApi, "focusFrame").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "اعمل المقايسة{enter}");
    const card = await screen.findByRole("article", { name: "جدول الكميات - عينة" });
    await user.click(within(card).getByRole("button", { name: new RegExp(texts.deliverableOpen.ar) }));
    expect(focus).toHaveBeenCalledWith(`deliverable:${D}`);
    expect(screen.queryByRole("tablist", { name: texts.reviewPanels.ar })).toBeNull();
  });

  it("a Deliverable not on the canvas opens beside it; focus goes to Close, and Esc gives it back", async () => {
    setCurrentProject(P1);
    const parts = [reply[0]!, { type: "data-deliverable", id: D, data: { id: D } }, ...reply.slice(1)];
    const d = `/api/projects/p1/deliverables/${D}`;
    core({
      routes: {
        "POST /api/chat": (init) => streamed(parts, init),
        "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }),
        [`GET ${d}`]: () => Response.json(sheet()),
        [`GET ${d}/changes?status=pending`]: () => Response.json({ changes: [] }),
        [`GET ${d}/changes?status=stale`]: () => Response.json({ changes: [] }),
        [`GET ${d}/comments`]: () => Response.json({ comments: [] }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "اعمل المقايسة{enter}");
    const card = await screen.findByRole("article", { name: "جدول الكميات - عينة" });
    const open = within(card).getByRole("button", { name: new RegExp(texts.deliverableOpen.ar) });
    await user.click(open);
    expect(await screen.findByText("03/02")).toBeInTheDocument();
    expect(screen.getByRole("tablist", { name: texts.reviewPanels.ar })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.close.ar })).toHaveFocus();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("tablist")).toBeNull());
    await waitFor(() => expect(open).toHaveFocus());
  });

  it("“Deliverables” in the top bar opens the Project Index of the open project", async () => {
    setCurrentProject(P1);
    core({ routes: { "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }) } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.deliverablesButton.ar }));
    expect(await screen.findByRole("button", { name: "جدول الكميات - عينة" })).toBeInTheDocument();
  });

  it("the chat folds to a button and opens again; its width can be changed from the keyboard", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App />);
    const handle = await screen.findByRole("separator", { name: texts.chatWidth.ar });
    expect(handle).toHaveAttribute("aria-valuenow", "340");
    handle.focus();
    await user.keyboard("{ArrowRight}"); // in Arabic the chat is at the left: its edge moves right to widen it
    expect(handle).toHaveAttribute("aria-valuenow", "356");
    await user.click(screen.getByRole("button", { name: texts.closeChat.ar }));
    expect(screen.queryByRole("log")).toBeNull();
    await user.click(screen.getByRole("button", { name: texts.projectChat.ar }));
    expect(screen.getByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument();
  });

  it("one message box: at the open chat's foot, floating over the canvas only while the chat is folded", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    const { container } = render(<App />);
    const chat = await screen.findByRole("complementary", { name: texts.projectChat.ar });
    expect(container.querySelectorAll("[data-command-box]")).toHaveLength(1);
    expect(chat).toContainElement(await box()); // below the conversation, in the chat itself
    expect(chat).toHaveAttribute("data-canvas-cover"); // the canvas keeps its frames out from under it
    await user.click(screen.getByRole("button", { name: texts.closeChat.ar }));
    expect(container.querySelectorAll("[data-command-box]")).toHaveLength(1);
    const floating = screen.getByRole("region", { name: texts.commandBar.ar });
    expect(floating).toContainElement(await box());
    expect(floating).toHaveAttribute("data-canvas-cover");
    await user.click(screen.getByRole("button", { name: texts.projectChat.ar }));
    expect(screen.getByRole("complementary", { name: texts.projectChat.ar })).toContainElement(await box());
  });
});
