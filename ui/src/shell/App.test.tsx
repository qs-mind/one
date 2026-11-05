// The shell around the workspace: the top bar and its panels, the project switcher and the General chat, the hand-off
// from the General chat, the palette, F6 between regions, the narrow layout and the sample label, and the open
// document: restored per project, saved as it changes, opened from a chat card, gone when its document goes.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fakeSources } from "../project/fake";
import { D, entry, sheet } from "../deliverables/fixtures";
import { count, fill, setLanguage, texts } from "../i18n";
import { currentProject, setCurrentProject } from "../records/project";
import { askForBackupFolder, stopAsking } from "../backup/ask";
import { workspaceApi } from "../workspace/api";
import { App } from "./App";
import { bodyOf, calls, core, P1, P2, reply, streamed } from "./testing";

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
const topBar = () => screen.getByRole("banner", { name: texts.topBar.ar });
const head = () => screen.findByRole("heading", { level: 1 });
const inTwoWeeks = "2026-11-19";

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

afterEach(() => {
  window.history.replaceState(null, "", "/");
  vi.unstubAllGlobals();
});

/** matchMedia that answers `narrow` for the 1000 px query. */
function screenWidth(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("999px") ? narrow : false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

const fileA = { id: "fa", name: "مواصفات مدرسة - عينة.pdf", status: "read" as const, note: null, replaces: null };
const fileB = { id: "fb", name: "مواصفات برج - عينة.pdf", status: "read" as const, note: null, replaces: null };

describe("the top bar", () => {
  it("shows the project name and only the status the core knows", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ status: { submission_date: inTwoWeeks, days_left: 14 } });
    render(<App sourcesFor={() => sources} />);
    const bar = topBar();
    expect(within(bar).getByRole("button", { name: new RegExp(P1.name) })).toBeInTheDocument();
    expect(await within(bar).findByText(/فاضل 14 يوم/)).toBeInTheDocument();
    expect(within(bar).queryByText(texts.boqSoFar.ar)).toBeNull();
    expect(within(bar).queryByText(texts.sampleData.ar)).toBeNull();
  });

  it("BOQ so far names its Deliverable and Revision", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({
      deliverables: [{ ...entry(), id: "boq1", title: "تسعير المقايسة - عينة" }],
      status: { boq_value: { value: "48200000.00", currency: "EGP", deliverable_id: "boq1", revision: 2, status: "checked", sample: true } },
    });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    const boq = await within(topBar()).findByRole("button", { name: new RegExp(texts.boqSoFar.ar) });
    expect(boq).toHaveTextContent(texts.sampleData.ar); // a sample number is labelled
    await user.click(boq);
    const popover = await screen.findByRole("dialog");
    expect(await within(popover).findByText(fill(texts.boqFrom.ar, { title: "تسعير المقايسة - عينة" }))).toBeInTheDocument();
    expect(within(popover).getByText(fill(texts.reviewRev.ar, { n: 2 }))).toBeInTheDocument();
    expect(within(popover).getByText(/48,200,000/)).toBeInTheDocument();
  });

  it("waiting opens the folded chat at the card", async () => {
    setCurrentProject(P1);
    const card = { type: "data-card", id: "c1", data: { kind: "outside", title: { en: "Send?", ar: "نبعت؟" }, detail: { en: "Lead QS: emailing.", ar: "بيبعت بالإيميل." }, options: ["yes", "no"], status: "pending" } };
    core({
      routes: {
        "GET /api/chat/p1/messages": () =>
          Response.json({ messages: [{ id: "a1", role: "assistant", parts: [{ type: "text", text: "-" }, card] }] }),
      },
    });
    const sources = fakeSources({ status: { waiting: 1 } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await screen.findByText("بيبعت بالإيميل.");
    await user.click(screen.getByRole("button", { name: texts.closeChat.ar }));
    await user.click(await within(topBar()).findByRole("button", { name: count("decisionsWaiting", 1) }));
    await waitFor(() => expect(screen.getByRole("button", { name: texts.allowOnce.ar })).toHaveFocus());
  });

  it("AI settings and Projects open from the top bar; Esc returns focus", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    for (const [button, heading, inMore] of [
      [texts.ai.ar, texts.aiTitle.ar, true], // AI settings are in More; focus goes back to More
      [P1.name, texts.projects.ar, false],
    ] as const) {
      const opener = within(topBar()).getByRole("button", { name: new RegExp(inMore ? texts.more.ar : button) });
      await user.click(opener);
      if (inMore) await user.click(await screen.findByRole("button", { name: new RegExp(button) }));
      const panel = await screen.findByRole("region", { name: heading });
      await waitFor(() => expect(panel.contains(document.activeElement) || document.activeElement?.contains(panel)).toBe(true));
      await user.keyboard("{Escape}");
      expect(screen.queryByRole("region", { name: heading })).toBeNull();
      expect(opener).toHaveFocus();
    }
  });
});

describe("projects and the General chat", () => {
  it("the switcher lists General chat, the projects and New project, and opens one", async () => {
    const fetch = core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await user.click(within(topBar()).getByRole("button", { name: new RegExp(texts.generalChat.ar) }));
    const panel = await screen.findByRole("region", { name: texts.projects.ar });
    expect(await within(panel).findByRole("button", { name: P2.name })).toBeInTheDocument();
    const buttons = within(panel).getAllByRole("button").map((b) => b.textContent ?? "");
    const first = buttons.findIndex((text) => text.includes(texts.generalChat.ar));
    expect(first).toBeGreaterThan(-1);
    expect(first).toBeLessThan(buttons.findIndex((text) => text.includes(P2.name))); // newest first, under it
    expect(within(panel).getByText(texts.newProject.ar)).toBeInTheDocument();
    await user.click(within(panel).getByRole("button", { name: P1.name }));
    await waitFor(() => expect(currentProject()?.id).toBe("p1"));
    expect(await head()).toHaveTextContent(texts.projectFiles.ar); // an empty project opens on Project files
    expect(calls(fetch, "POST", "/api/projects/p1/open")).toHaveLength(1);
  });

  it("General chat shows the chat without a document or status", async () => {
    core();
    render(<App />);
    await box();
    expect(document.querySelector('[data-region="document"]')).toBeNull();
    expect(within(topBar()).getByText(texts.generalChat.ar)).toBeInTheDocument();
    expect(screen.getByRole("log", { name: texts.generalChat.ar })).toBeInTheDocument();
  });

  it("going to the General chat from a project closes the project", async () => {
    setCurrentProject(P1);
    const fetch = core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await user.click(within(topBar()).getByRole("button", { name: new RegExp(P1.name) }));
    await user.click(await screen.findByRole("button", { name: texts.generalChat.ar }));
    expect(currentProject()).toBeUndefined();
    await waitFor(() => expect(calls(fetch, "POST", "/api/projects/p1/close")).toHaveLength(1));
    expect(await screen.findByRole("log", { name: texts.generalChat.ar })).toBeInTheDocument();
  });

  it("each project has its own chat, loaded from the core", async () => {
    setCurrentProject(P1);
    const fetch = core({
      routes: {
        "GET /api/chat/p1/messages": () =>
          Response.json({ messages: [{ id: "u1", role: "user", parts: [{ type: "text", text: "رسالة مدرسة - عينة" }] }] }),
      },
    });
    render(<App sourcesFor={() => fakeSources({})} />);
    expect(await screen.findByText("رسالة مدرسة - عينة")).toBeInTheDocument();
    act(() => setCurrentProject(P2));
    await waitFor(() => expect(calls(fetch, "GET", "/api/chat/p2/messages")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByText("رسالة مدرسة - عينة")).toBeNull());
  });

  it("hand-off continues in the project only after the click", async () => {
    const handOff = { type: "data-hand-off", id: "h1", data: { kind: "project", project_id: "p2", name: P2.name, request: "سعّر بند 3/02 - عينة" } };
    const fetch = core({
      routes: {
        "POST /api/chat": (init) =>
          bodyOf(init).id === "general" ? streamed([reply[0]!, handOff, ...reply.slice(1)], init) : streamed(reply, init),
      },
    });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await user.type(await box(), "سعّر بند في البرج{enter}");
    expect(await screen.findByText(fill(texts.handOffAbout.ar, { name: P2.name }))).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(calls(fetch, "POST", "/api/projects/p2/open")).toHaveLength(0); // never by itself

    await user.click(screen.getByRole("button", { name: fill(texts.continueInProject.ar, { name: P2.name }) }));
    await waitFor(() => expect(currentProject()?.id).toBe("p2"));
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(2));
    const body = bodyOf(calls(fetch, "POST", "/api/chat")[1]![1]) as { id: string; messages: { parts: { text: string }[] }[] };
    expect(body.id).toBe("p2");
    expect(body.messages[0]!.parts[0]!.text).toBe("سعّر بند 3/02 - عينة");
  });

  it("no project for it yet: Create makes the project, then sends the request there", async () => {
    const offer = [{ type: "data-hand-off", id: "h2", data: { kind: "new_project", name: "فيلا - عينة", request: "اعمل حصر - عينة" } }];
    const fetch = core({
      routes: {
        "POST /api/chat": (init) =>
          bodyOf(init).id === "general" ? streamed([reply[0]!, ...reply.slice(1, 6), ...offer, ...reply.slice(6)], init) : streamed(reply, init),
        "POST /api/projects": () => Response.json({ id: "p3", name: "فيلا - عينة", created_at: "2026-11-05T09:00:00+00:00" }),
      },
    });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await user.type(await box(), "عندي فيلا جديدة{enter}");
    await user.click(await screen.findByRole("button", { name: fill(texts.createProjectNamed.ar, { name: "فيلا - عينة" }) }));
    await waitFor(() => expect(currentProject()?.id).toBe("p3"));
    expect(bodyOf(calls(fetch, "POST", "/api/projects")[0]![1])).toEqual({ name: "فيلا - عينة" });
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(2));
    expect(bodyOf(calls(fetch, "POST", "/api/chat")[1]![1]).id).toBe("p3");
  });
});

describe("the open document", () => {
  it("the screen is the open document", async () => {
    setCurrentProject(P1);
    core();
    render(<App sourcesFor={() => fakeSources({ files: [fileA] })} />);
    await head();
    expect(document.querySelector('[data-region="document"]')).not.toBeNull();
  });

  it("switching project restores that project's open document", async () => {
    setCurrentProject(P1);
    core();
    const byProject = {
      p1: fakeSources({ files: [fileA], workspace: { key: "file:fa", anchor: { page: 1 } } }),
      p2: fakeSources({ files: [fileB], workspace: { key: "file:fb", anchor: null } }),
    };
    render(<App sourcesFor={(id) => byProject[id as "p1" | "p2"]} />);
    await waitFor(async () => expect(await head()).toHaveTextContent(fileA.name));
    act(() => setCurrentProject(P2));
    await waitFor(async () => expect(await head()).toHaveTextContent(fileB.name));
    act(() => setCurrentProject(P1));
    await waitFor(async () => expect(await head()).toHaveTextContent(fileA.name));
    expect(workspaceApi.current()).toEqual({ key: "file:fa", anchor: { page: 1 } });
  });

  it("a document opened is saved in its project; a switch sends it at once, pagehide with keepalive", async () => {
    setCurrentProject(P1);
    core();
    const p1 = fakeSources({ files: [fileA] });
    const p2 = fakeSources({});
    render(<App sourcesFor={(id) => (id === "p1" ? p1 : p2)} />);
    await head();
    act(() => workspaceApi.open("file:fa", { page: 2 }));
    window.dispatchEvent(new Event("pagehide"));
    expect(p1.saved.workspace.at(-1)).toEqual({ opened: { key: "file:fa", anchor: { page: 2 } }, keepalive: true });
    act(() => workspaceApi.open("files:all"));
    act(() => setCurrentProject(P2));
    expect(p1.saved.workspace.at(-1)).toEqual({ opened: { key: "files:all", anchor: null }, keepalive: false });
    await waitFor(() => expect(currentProject()?.id).toBe("p2"));
    expect(p2.saved.workspace).toEqual([]); // restoring is not a change
  });

  it("a Deliverable card in the chat opens it as the document", async () => {
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
    expect(workspaceApi.current()?.key).toBe(`deliverable:${D}`);
    expect(await head()).toHaveTextContent("جدول الكميات - عينة");
    expect(await screen.findByText("03/02")).toBeInTheDocument();
    expect(document.querySelector("[data-deliverable-panel]")).toBeNull(); // no board over the screen any more
  });

  it("a removed document closes: its file replaced on the live stream, or gone from a reload", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ files: [fileA], deliverables: [entry({ id: "dX" })], workspace: { key: "file:fa", anchor: null } });
    render(<App sourcesFor={() => sources} />);
    await waitFor(async () => expect(await head()).toHaveTextContent(fileA.name));
    act(() => sources.emit({ type: "file", file: { ...fileB, replaces: "fa" } }));
    await waitFor(() => expect(workspaceApi.current()?.key).toBe("files:all"));

    act(() => workspaceApi.open("deliverable:dX"));
    const reload = vi.spyOn(sources, "deliverables").mockResolvedValue([]);
    act(() => sources.reconnect());
    await waitFor(() => expect(workspaceApi.current()?.key).toBe("files:all"));
    expect(reload).toHaveBeenCalled();
  });
});

describe("the palette", () => {
  it("Ctrl+K opens the palette with the Arabic layout too", async () => {
    core();
    render(<App />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", key: "ن", ctrlKey: true });
    expect(await screen.findByRole("dialog", { name: texts.palette.ar })).toBeInTheDocument();
  });

  it("typing a Deliverable's title and Enter opens it", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ deliverables: [{ ...entry(), id: "boq1", title: "تسعير المقايسة - عينة" }] });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await box();
    await head();
    await user.click(within(topBar()).getByRole("button", { name: fill(texts.searchKeys.ar, { keys: "Ctrl K" }) }));
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.type(within(dialog).getByRole("combobox"), "تسعير المقايسة");
    await within(dialog).findByRole("option", { name: /تسعير المقايسة - عينة/ });
    await user.keyboard("{Enter}");
    expect(workspaceApi.current()?.key).toBe("deliverable:boq1");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("finds text in Project Records and opens the file at its page", async () => {
    setCurrentProject(P1);
    const hit = { chunk_id: 1, file_id: "f1", file_name: "مواصفات - عينة.pdf", locator: { page: 3 }, text: "خرسانة مسلحة للأعمدة - عينة" };
    const fetch = core({
      routes: { "GET /api/projects/p1/search?q=%D8%A3%D8%B9%D9%85%D8%AF%D8%A9&k=10": () => Response.json({ note: null, results: [hit] }) },
    });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", key: "ن", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.type(within(dialog).getByRole("combobox"), "أعمدة");
    await user.click(await within(dialog).findByRole("option", { name: /خرسانة مسلحة للأعمدة - عينة/ }));
    expect(workspaceApi.current()).toEqual({ key: "file:f1", anchor: { page: 3 } });
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/search?"))).toHaveLength(1); // debounced
  });

  it("each command says what it does, none reads like another; no canvas commands; the panels and Usage Stats are there", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    let dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    const names = within(dialog).getAllByRole("option").map((o) => o.textContent ?? "");
    for (const key of ["records", "deliverablesButton", "ai", "backupTitle", "usageTitle"] as const) expect(names, key).toContain(texts[key].ar);
    expect(new Set(names).size).toBe(names.length);
    await user.click(within(dialog).getByRole("option", { name: texts.backupTitle.ar }));
    expect(await screen.findByRole("heading", { name: texts.backupTitle.ar })).toBeInTheDocument();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.click(within(dialog).getByRole("option", { name: texts.records.ar }));
    expect(await screen.findByRole("heading", { name: texts.records.ar })).toBeInTheDocument();
  });

  it("the Project Index opens from the palette; a Deliverable picked there opens as the document", async () => {
    setCurrentProject(P1);
    core({ routes: { "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }) } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({ deliverables: [entry()] })} />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.click(within(dialog).getByRole("option", { name: texts.deliverablesButton.ar }));
    const index = await screen.findByRole("region", { name: texts.deliverables.ar });
    await user.click(await within(index).findByRole("button", { name: entry().title }));
    expect(workspaceApi.current()?.key).toBe(`deliverable:${D}`);
    expect(screen.queryByRole("region", { name: texts.deliverables.ar })).toBeNull();
  });

  it("in the General chat the palette's field never mentions frames", async () => {
    core();
    render(<App />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    expect(within(dialog).getByRole("combobox")).toHaveAttribute("placeholder", texts.paletteSearchGeneral.ar);
    expect(texts.paletteSearchGeneral.ar).not.toContain("الإطارات");
    expect(texts.paletteSearchGeneral.en).not.toMatch(/frame/i);
    expect(texts.paletteSearch.en).not.toMatch(/frame/i);
  });
});

describe("keyboard and layout", () => {
  it("F6 moves between top bar, document, chat and command bar", async () => {
    setCurrentProject(P1);
    core();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    const where = () => document.activeElement?.closest("[data-region]")?.getAttribute("data-region") ?? undefined;
    const order: (string | undefined)[] = [];
    for (let i = 0; i < 5; i++) {
      fireEvent.keyDown(document.activeElement ?? document.body, { code: "F6", key: "F6" });
      order.push(where());
    }
    expect(order).toEqual(["topbar", "document", "chat", "command", "topbar"]);
    fireEvent.keyDown(document.activeElement!, { code: "F6", key: "F6", shiftKey: true });
    expect(where()).toBe("command");
  });

  it("below 1280 px the status folds into More, a section at its top; no Status button", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: query === "(max-width: 1279px)",
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ status: { submission_date: inTwoWeeks, days_left: 14 } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await head();
    expect(within(topBar()).queryByText(/فاضل 14 يوم/)).toBeNull();
    expect(within(topBar()).queryByRole("button", { name: texts.deliverableStatus.ar })).toBeNull();
    // search still has room here: it folds only below 1000 px
    expect(within(topBar()).getByRole("button", { name: `${texts.searchField.ar} Ctrl K` })).toBeInTheDocument();
    await user.click(within(topBar()).getByRole("button", { name: texts.more.ar }));
    const status = await screen.findByText(/فاضل 14 يوم/);
    const section = status.closest("[data-more-status]")!;
    expect(section).not.toBeNull();
    expect(section.parentElement!.firstElementChild).toBe(section); // the top of More
    vi.unstubAllGlobals();
  });

  it("below 1000 px the status is in More and the chat opens from the top bar", async () => {
    screenWidth(true);
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ status: { submission_date: inTwoWeeks, days_left: 14 } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await head();
    expect(screen.queryByRole("log")).toBeNull();
    expect(within(topBar()).queryByText(/فاضل 14 يوم/)).toBeNull();
    await user.click(within(topBar()).getByRole("button", { name: texts.more.ar }));
    expect((await screen.findByText(/فاضل 14 يوم/)).closest("[data-more-status]")).not.toBeNull();
    await user.keyboard("{Escape}");
    await user.click(within(topBar()).getByRole("button", { name: texts.projectChat.ar }));
    expect(screen.getByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument();
  });

  it("below 640 px the document loses its side gutters", async () => {
    vi.stubGlobal("matchMedia", (query: string) => ({
      matches: /639px|999px|1279px/.test(query),
      media: query,
      addEventListener() {},
      removeEventListener() {},
    }));
    setCurrentProject(P1);
    core();
    render(<App sourcesFor={() => fakeSources({})} />);
    await head();
    const main = screen.getByRole("main");
    expect(main).toHaveClass("px-0");
    expect(main).not.toHaveClass("px-3");
    vi.unstubAllGlobals();
  });

  it("wider, the document keeps its 12 px gutters", async () => {
    setCurrentProject(P1);
    core();
    render(<App sourcesFor={() => fakeSources({})} />);
    await head();
    expect(screen.getByRole("main")).toHaveClass("px-3");
  });

  it("Full screen, from More or Ctrl+Shift+F by the key's place, folds the chat; the second press brings it back", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    const chat = () => screen.queryByRole("complementary", { name: texts.projectChat.ar });
    await user.click(within(topBar()).getByRole("button", { name: texts.more.ar }));
    await user.click(await screen.findByRole("button", { name: texts.fullScreen.ar }));
    await waitFor(() => expect(chat()).toBeNull());
    await user.click(within(topBar()).getByRole("button", { name: texts.more.ar }));
    const leave = await screen.findByRole("button", { name: texts.leaveFullScreen.ar });
    expect(leave).toHaveAttribute("aria-pressed", "true");
    await user.click(leave);
    await waitFor(() => expect(chat()).not.toBeNull());
    // the shortcut, read by its code: an Arabic layout's «ب» on the F key works too
    fireEvent.keyDown(document, { key: "ب", code: "KeyF", ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(chat()).toBeNull());
    fireEvent.keyDown(document, { key: "ب", code: "KeyF", ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(chat()).not.toBeNull());
    // never while writing: the message box keeps the keys
    fireEvent.keyDown(screen.getByRole("textbox", { name: texts.message.ar }), { key: "ب", code: "KeyF", ctrlKey: true, shiftKey: true });
    expect(chat()).not.toBeNull();
  });

  it("sample mode says sample once: an open sample Deliverable's facts, else the top bar's plain words", async () => {
    window.history.replaceState(null, "", "/?sample=1");
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App />);
    // Project files: no document facts, so the bar says it, in Copper with no border
    const words = await within(topBar()).findByText(texts.sampleData.ar);
    expect(words).toHaveClass("text-copper");
    expect(words.className).not.toMatch(/\bborder\b/);
    await user.click(await screen.findByRole("button", { name: new RegExp(texts.projectFiles.ar) }));
    await user.click(await screen.findByRole("menuitem", { name: /تسعير المقايسة - عينة/ }));
    // a sample Deliverable: its facts say it, and the bar says nothing more
    expect(await within(topBar()).findByText(new RegExp(texts.sampleNumbers.ar))).toBeInTheDocument();
    expect(within(topBar()).queryByText(texts.sampleData.ar)).toBeNull();
    act(() => setLanguage("en"));
    const bar = screen.getByRole("banner", { name: texts.topBar.en });
    expect(within(bar).getByText(new RegExp(texts.sampleNumbers.en))).toBeInTheDocument();
    expect(within(bar).queryByText(texts.sampleData.en)).toBeNull();
  });

  it("sample mode in the General chat, where no document says it: plain Copper words in the top bar, no border", async () => {
    window.history.replaceState(null, "", "/?sample=1");
    core();
    render(<App />);
    const label = await within(topBar()).findByText(texts.sampleData.ar);
    expect(label).toHaveClass("text-copper");
    expect(label.className).not.toMatch(/\bborder\b/);
  });
});

describe("the import reports and the backup question", () => {
  afterEach(() => stopAsking());

  it("are cards at the chat's foot, never over the document, and a new one opens a folded chat", async () => {
    setCurrentProject(P1);
    core({
      routes: {
        "GET /api/projects": () => Response.json({ projects: [{ ...P1, open: true }] }),
        "GET /api/backup": () => Response.json({ folder: null }),
      },
    });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    await user.click(screen.getByRole("button", { name: texts.closeChat.ar }));
    expect(screen.queryByRole("complementary", { name: texts.projectChat.ar })).toBeNull();
    await act(() => askForBackupFolder()); // after the first project
    const chat = await screen.findByRole("complementary", { name: texts.projectChat.ar });
    const question = within(chat).getByRole("region", { name: texts.backupTitle.ar });
    expect(question.closest("[data-notices]")).not.toBeNull();
    // one compact line: the question, its action and a dismiss; the path field opens only when asked for
    expect(within(question).getAllByRole("button").map((b) => b.textContent)).toEqual([texts.backupPickFolder.ar, texts.backupLater.ar]);
    expect(within(question).queryByRole("textbox")).toBeNull();
    expect(question).not.toHaveTextContent(texts.backupNoFolder.ar);
    await user.click(within(question).getByRole("button", { name: texts.backupPickFolder.ar }));
    expect(within(question).getByRole("textbox", { name: texts.backupFolderPath.ar })).toBeInTheDocument();
    await user.click(within(question).getByRole("button", { name: texts.backupLater.ar }));
    expect(within(chat).queryByRole("region", { name: texts.backupTitle.ar })).toBeNull();
  });
});
