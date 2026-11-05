// Plan 4's chat, as the shell wraps it: the General chat and a project's chat, a column beside the document. Moved
// from Chat.test.tsx; every behaviour there still holds, with the command bar as the composer.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { D, entry, sheet } from "../deliverables/fixtures";
import { count, fill, setLanguage, texts } from "../i18n";
import { fakeSources } from "../project/fake";
import { setCurrentProject } from "../records/project";
import { App } from "./App";
import { bodyOf, calls, core, P1, reply, running, streamed } from "./testing";

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

  it("a project's chat has the project's id, and sits beside the document", async () => {
    setCurrentProject(P1);
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await waitFor(() => expect(calls(fetch, "GET", "/api/chat/p1/messages")).toHaveLength(1));
    expect(document.querySelector('[data-region="document"]')).not.toBeNull();
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

  it("Ctrl+Enter while a Brief runs steers it, and shows it as steering", async () => {
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
    await user.type(field, "استخدم أسعار الشهر ده{Control>}{enter}{/Control}"); // Enter alone queues it
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

  it("a long word with no spaces breaks inside its bubble, only where it must; a table scrolls in its own box", async () => {
    const word = "يسشبتشبتصبلقتسلبقسليسشبتشبتصبلق".repeat(4);
    const parts = [
      reply[0]!,
      { type: "text-start", id: "t1" },
      { type: "text-delta", id: "t1", delta: `${word}\n\n| البند | الكمية |\n|---|---|\n| ${word} | 12 |` },
      { type: "text-end", id: "t1" },
      { type: "finish" },
    ];
    core({ routes: { "POST /api/chat": (init) => streamed(parts, init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), `${word}{enter}`);
    await screen.findByRole("table");
    const log = screen.getByRole("log", { name: texts.generalChat.ar });
    // the whole chat (the engineer's bubble, replies, cards, file names) wraps a word that cannot fit, anywhere in it,
    // and never by letter where it would fit (no break-all: it would split Arabic words); it never scrolls sideways
    const chat = log.parentElement!;
    expect(chat).toHaveClass("[overflow-wrap:anywhere]");
    expect(log).toHaveClass("overflow-x-hidden");
    expect(chat.querySelector("[class*='break-all']")).toBeNull();
    expect(screen.getAllByText(word)[0]!.closest("[data-own]")).toBeInTheDocument();
    // a reply's table keeps its words whole and scrolls inside its own box
    const table = screen.getByRole("table");
    expect(table.parentElement).toHaveClass("overflow-x-auto");
    expect(chat).toHaveClass("[&_table]:[overflow-wrap:normal]");
  });

  it("a table pasted from Excel shows as a table in the engineer's bubble, and goes to the core as it was pasted", async () => {
    const fetch = core({ routes: { "POST /api/chat": (init) => streamed(reply, init) } });
    const user = userEvent.setup();
    render(<App />);
    const pasted = "راجع دول:\nالبند\tالكمية\tالفئة\n01-01\t51.3\t2500\n01-02\t59.8\t2500";
    await user.click(await box());
    await user.paste(pasted);
    await user.keyboard("{Enter}");
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(1));
    const sent = bodyOf(calls(fetch, "POST", "/api/chat")[0]![1]) as { messages: { parts: { text: string }[] }[] };
    expect(sent.messages[0]!.parts[0]!.text).toBe(pasted);
    const own = (await screen.findByText("راجع دول:")).closest("[data-own]") as HTMLElement;
    const table = within(own).getByRole("table");
    expect(within(table).getAllByRole("row")).toHaveLength(3);
    expect(within(table).getAllByRole("cell").map((c) => c.textContent)).toContain("59.8");
    expect(table.parentElement).toHaveClass("overflow-x-auto"); // a wide one scrolls in its own box
    expect(own.querySelectorAll("p")).toHaveLength(1); // the words before it, not 4 paragraphs
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
    expect(await screen.findByText("التكليف ده وقف عند: بيسعّر البنود")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls(fetch, "POST", "/api/briefs/b1/continue")).toHaveLength(0); // never by itself

    await user.click(screen.getByRole("button", { name: texts.continue.ar }));
    expect(await findReply(/مرحبا Hello/)).toBeInTheDocument(); // its stream joined
    expect(calls(fetch, "POST", "/api/briefs/b1/continue")).toHaveLength(1);
  });

  it("a refused key in the chat: the core's words, and Open AI settings, which opens them", async () => {
    // as the core sends it (core/qsone/copy.py KEY_REFUSED, with its fix)
    const refused = {
      en: "Anthropic refused this Claude key. Check that you copied all of it, or make a new key at console.anthropic.com.",
      ar: "Anthropic رفض مفتاح Claude ده. اتأكد إنك نسخته كله، أو اعمل مفتاح جديد من console.anthropic.com.",
      fix: "ai",
    };
    core({ routes: { "POST /api/chat": (init) => streamed([{ type: "error", errorText: JSON.stringify(refused) }], init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "hello{enter}");
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(refused.ar);
    expect(alert).not.toHaveTextContent(/فوق|at the top/);
    expect(screen.queryByRole("heading", { name: texts.aiTitle.ar })).toBeNull();

    await user.click(within(alert).getByRole("button", { name: texts.openAiSettings.ar }));
    expect(await screen.findByRole("heading", { name: texts.aiTitle.ar })).toBeInTheDocument();
  });

  it("an error the chat cannot fix from here shows no action", async () => {
    const failed = { en: "The work stopped because of a problem with Claude.", ar: "الشغل وقف بسبب مشكلة في Claude." };
    core({ routes: { "POST /api/chat": (init) => streamed([...reply.slice(0, 2), { type: "error", errorText: JSON.stringify(failed) }], init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "hello{enter}");
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveTextContent(failed.ar));
    expect(within(alert).queryByRole("button")).toBeNull();
  });

  it("shows a plain line when the reply fails, and the core's {en, ar} line in the engineer's language", async () => {
    const refused = {
      en: "Anthropic refused this Claude key. Check that you copied all of it, or make a new key at console.anthropic.com.",
      ar: "Anthropic رفض مفتاح Claude ده. اتأكد إنك نسخته كله، أو اعمل مفتاح جديد من console.anthropic.com.",
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
    await user.click(screen.getByRole("button", { name: texts.more.ar }));
    await user.click(await screen.findByRole("button", { name: texts.otherLanguage.ar }));
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

  it("pasting the first key stores it in the core and checks it, without showing it, and opens the chat", async () => {
    const key = "sk-ant-sample-not-a-real-key-0000000000000"; // not a real key
    const fetch = core({ keySet: false, routes: { "POST /api/settings/ai/check": () => Response.json({ ok: true }) } });
    const user = userEvent.setup();
    render(<App />);
    const field = await screen.findByLabelText(texts.aiKeyLabel.ar);
    expect(field).toHaveAttribute("type", "password");
    await user.click(field);
    await user.paste(key);

    expect(await box()).toBeInTheDocument(); // the chat is open now
    expect(screen.queryByDisplayValue(key)).not.toBeInTheDocument();
    const [, init] = calls(fetch, "PUT", "/api/settings/ai-key")[0]!;
    expect(bodyOf(init)).toEqual({ provider: "anthropic", value: key });
    expect(calls(fetch, "POST", "/api/settings/ai/check")).toHaveLength(1);
  });

  it("“AI” opens its one settings panel while the chat stays, and closes again", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    await user.click(await screen.findByRole("button", { name: texts.more.ar }));
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
    await user.click(await screen.findByRole("button", { name: texts.more.ar })); // the other language is in More
    await user.click(await screen.findByRole("button", { name: texts.otherLanguage.ar }));
    expect(document.documentElement.dir).toBe("ltr");
    expect(await screen.findByRole("button", { name: texts.send.en })).toBeInTheDocument();
  });

  it("a Deliverable card's Open shows it as the document, with its review in the viewer", async () => {
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
    render(<App sourcesFor={() => fakeSources({ deliverables: [entry()] })} />);
    await user.type(await box(), "اعمل المقايسة{enter}");
    const card = await screen.findByRole("article", { name: "جدول الكميات - عينة" });
    await user.click(within(card).getByRole("button", { name: new RegExp(texts.deliverableOpen.ar) }));
    const sheetBox = await screen.findByText("03/02");
    expect(sheetBox.closest('[data-region="document"]')).not.toBeNull();
    expect(screen.getByRole("tablist", { name: texts.reviewPanels.ar })).toBeInTheDocument();
    expect(screen.getByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument(); // the chat stays beside it
  });

  it("the chat is a column beside the document, 320 px to start, 280 to 480 from the keyboard", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    const chat = await screen.findByRole("complementary", { name: texts.projectChat.ar });
    expect(chat.parentElement).toBe(document.querySelector('[data-region="document"]')!.parentElement); // a flex sibling
    expect(chat).not.toHaveClass("absolute");
    const handle = screen.getByRole("separator", { name: texts.chatWidth.ar });
    expect(handle).toHaveAttribute("aria-valuenow", "320");
    expect(handle).toHaveAttribute("aria-valuemin", "280");
    expect(handle).toHaveAttribute("aria-valuemax", "480");
    handle.focus();
    await user.keyboard("{ArrowRight}"); // in Arabic the chat is at the left: its edge moves right to widen it
    expect(handle).toHaveAttribute("aria-valuenow", "336");
    for (let i = 0; i < 12; i++) await user.keyboard("{ArrowRight}");
    expect(handle).toHaveAttribute("aria-valuenow", "480");
    for (let i = 0; i < 14; i++) await user.keyboard("{ArrowLeft}");
    expect(handle).toHaveAttribute("aria-valuenow", "280");
    expect(handle).toHaveClass("focus-visible:outline-2", "focus-visible:outline-ink");
  });

  it("folding leaves the edge with the dot; the edge opens it again", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    const { container } = render(<App sourcesFor={() => fakeSources({ status: { waiting: 1 } })} />);
    await box();
    await user.click(screen.getByRole("button", { name: texts.closeChat.ar }));
    expect(screen.queryByRole("log")).toBeNull();
    expect(container.querySelectorAll("[data-command-box]")).toHaveLength(0); // the composer is only in the chat
    const edge = screen.getByRole("button", { name: texts.openChat.ar });
    expect(edge).toHaveClass("w-3"); // 12 px
    await waitFor(() => expect(edge.querySelector("[data-waiting-dot]")).not.toBeNull());
    await user.click(edge);
    expect(screen.getByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument();
    expect(screen.getByRole("complementary", { name: texts.projectChat.ar })).toContainElement(await box());
    expect(container.querySelectorAll("[data-command-box]")).toHaveLength(1);
  });

  it("below 1000 px the chat opens over the document from the top bar's chat button and closes on Esc", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query.includes("999px"),
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({ status: { waiting: 1 } })} />);
    await screen.findByRole("heading", { level: 1 });
    expect(screen.queryByRole("complementary", { name: texts.projectChat.ar })).toBeNull();
    const button = within(screen.getByRole("banner")).getByRole("button", { name: texts.projectChat.ar });
    await waitFor(() => expect(button.querySelector("[data-waiting-dot]")).not.toBeNull()); // the dot rides on it
    await user.click(button);
    const chat = screen.getByRole("complementary", { name: texts.projectChat.ar });
    expect(chat).toHaveClass("fixed");
    await user.click(await box());
    await user.keyboard("{Escape}"); // Esc unwinds one step at a time: the open message box folds first
    expect(chat).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("complementary", { name: texts.projectChat.ar })).toBeNull());
    expect(button).toHaveFocus();
    vi.unstubAllGlobals();
  });

  it("its head names the role it talks to and who is working now; pressing that lists the team, Desks folded", async () => {
    setCurrentProject(P1);
    core();
    const est = {
      id: "est", kind: "specialist" as const, role: { en: "Estimator - sample", ar: "مهندس التسعير - عينة" }, desk_id: "pd",
      model: "claude-sonnet-5", state: "working" as const, line: null, brief_id: "b1",
      focus: { frame: "deliverable:dA" as const, anchor: null }, at: "",
    };
    const sources = fakeSources({
      deliverables: [entry({ id: "dA", title: "تسعير - عينة" })],
      team: { desks: [{ id: "pd", name: { en: "Pricing Desk", ar: "قسم التسعير - عينة" }, stage: "temporary" }], agents: [est] },
    });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    const chat = await screen.findByRole("complementary", { name: texts.projectChat.ar });
    expect(within(chat).getByRole("heading", { level: 2 })).toHaveTextContent(texts.roleLead.ar);
    const now = await within(chat).findByRole("button", { name: fill(texts.workingNow.ar, { role: "مهندس التسعير - عينة" }) });
    await user.click(now);
    const team = await screen.findByRole("dialog");
    const desk = within(team).getByRole("button", { name: count("deskSummary", 1, { desk: "قسم التسعير - عينة" }) });
    expect(desk).toHaveAttribute("aria-expanded", "false");
    expect(team.querySelector('[data-agent="est"]')).toBeNull();
    expect(team).toHaveTextContent(texts.roleLead.ar); // the project team: the Lead QS and the Checking QS
    await user.click(desk);
    expect(team.querySelector('[data-agent="est"]')).not.toBeNull();
  });
});
