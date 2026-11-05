// The shell around the canvas: the top bar and its panels, the project switcher and the General chat, the hand-off
// from the General chat, the palette, F6 between regions, the narrow layout and the sample label.
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { canvasApi } from "../canvas/api";
import { fakeSources } from "../canvas/fake";
import { entry } from "../deliverables/fixtures";
import { fill, setLanguage, texts } from "../i18n";
import { currentProject, setCurrentProject } from "../records/project";
import { askForBackupFolder, stopAsking } from "../backup/ask";
import { App } from "./App";
import { bodyOf, calls, core, P1, P2, reply, shown, streamed } from "./testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }));

const box = () => screen.findByRole("textbox", { name: texts.message.ar });
const topBar = () => screen.getByRole("banner", { name: texts.topBar.ar });
const inTwoWeeks = "2026-11-19";

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

afterEach(() => {
  window.history.replaceState(null, "", "/");
});

/** matchMedia that answers `narrow` for the 900 px query. */
function screenWidth(narrow: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("899px") ? narrow : false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

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

  it("waiting for you opens the chat at the first waiting card", async () => {
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
    await user.click(await within(topBar()).findByRole("button", { name: fill(texts.waitingForYou.ar, { n: 1 }) }));
    await waitFor(() => expect(screen.getByRole("button", { name: texts.allowOnce.ar })).toHaveFocus());
  });

  it("AI settings, Projects, Deliverables and Project Records open from the top bar; Esc returns focus", async () => {
    setCurrentProject(P1);
    core({ routes: { "GET /api/projects/p1/files": () => Response.json({ files: [] }) } });
    const user = userEvent.setup();
    render(<App />);
    await box();
    for (const [button, heading, inMore] of [
      [texts.ai.ar, texts.aiTitle.ar, true], // AI settings are in More; focus goes back to More
      [P1.name, texts.projects.ar, false],
      [texts.records.ar, texts.records.ar, false],
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
    render(<App />);
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
    expect(await screen.findByRole("region", { name: "canvas stand-in" })).toBeInTheDocument();
    expect(calls(fetch, "POST", "/api/projects/p1/open")).toHaveLength(1);
  });

  it("General chat shows the chat without a canvas, status or Records", async () => {
    core();
    render(<App />);
    await box();
    expect(screen.queryByRole("region", { name: "canvas stand-in" })).toBeNull();
    expect(within(topBar()).getByText(texts.generalChat.ar)).toBeInTheDocument();
    expect(within(topBar()).queryByRole("button", { name: texts.records.ar })).toBeNull();
    expect(screen.getByRole("log", { name: texts.generalChat.ar })).toBeInTheDocument();
  });

  it("going to the General chat from a project closes the project", async () => {
    setCurrentProject(P1);
    const fetch = core();
    const user = userEvent.setup();
    render(<App />);
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
    render(<App />);
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
    render(<App />);
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
    render(<App />);
    await user.type(await box(), "عندي فيلا جديدة{enter}");
    await user.click(await screen.findByRole("button", { name: fill(texts.createProjectNamed.ar, { name: "فيلا - عينة" }) }));
    await waitFor(() => expect(currentProject()?.id).toBe("p3"));
    expect(bodyOf(calls(fetch, "POST", "/api/projects")[0]![1])).toEqual({ name: "فيلا - عينة" });
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat")).toHaveLength(2));
    expect(bodyOf(calls(fetch, "POST", "/api/chat")[1]![1]).id).toBe("p3");
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

  it("finds a frame by title and focuses it", async () => {
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ deliverables: [{ ...entry(), id: "boq1", title: "تسعير المقايسة - عينة" }] });
    vi.spyOn(canvasApi, "frames").mockReturnValue([
      { key: "deliverable:boq1", x: 0, y: 0, w: 960, h: 640, z: 0, collapsed: false },
      { key: "files:all", x: -500, y: 0, w: 360, h: 520, z: 0, collapsed: false },
    ]);
    const focus = vi.spyOn(canvasApi, "focusFrame").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await box();
    await user.click(within(topBar()).getByRole("button", { name: fill(texts.searchKeys.ar, { keys: "Ctrl K" }) }));
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.type(within(dialog).getByRole("combobox"), "المقايسة");
    await user.click(await within(dialog).findByRole("option", { name: /تسعير المقايسة - عينة/ }));
    expect(focus).toHaveBeenCalledWith("deliverable:boq1");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("finds text in Project Records and opens the file at its page", async () => {
    setCurrentProject(P1);
    const hit = { chunk_id: 1, file_id: "f1", file_name: "مواصفات - عينة.pdf", locator: { page: 3 }, text: "خرسانة مسلحة للأعمدة - عينة" };
    const fetch = core({
      routes: { "GET /api/projects/p1/search?q=%D8%A3%D8%B9%D9%85%D8%AF%D8%A9&k=10": () => Response.json({ note: null, results: [hit] }) },
    });
    const open = vi.spyOn(canvasApi, "openFile").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", key: "ن", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.type(within(dialog).getByRole("combobox"), "أعمدة");
    await user.click(await within(dialog).findByRole("option", { name: /خرسانة مسلحة للأعمدة - عينة/ }));
    expect(open).toHaveBeenCalledWith("f1", 3);
    expect(fetch.mock.calls.filter(([url]) => String(url).includes("/search?"))).toHaveLength(1); // debounced
  });

  it("commands run from the palette: show everything", async () => {
    setCurrentProject(P1);
    core();
    const fit = vi.spyOn(canvasApi, "fitAll").mockImplementation(() => {});
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    const dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.click(within(dialog).getByRole("option", { name: texts.fitAll.ar }));
    expect(fit).toHaveBeenCalled();
  });

  it("each command says what it does, none reads like another; the panels and Usage Stats are there too", async () => {
    setCurrentProject(P1);
    core();
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    let dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    const names = within(dialog).getAllByRole("option").map((o) => o.textContent ?? "");
    for (const key of ["fitAll", "arrangeByStageCommand", "tidy", "records", "deliverablesButton", "ai", "backupTitle", "usageTitle"] as const)
      expect(names, key).toContain(texts[key].ar);
    expect(new Set(names).size).toBe(names.length);
    expect(texts.tidy.ar).not.toMatch(/^(نظّم|رتّب)/); // never «نظّم» next to «رتّب»: one says rows, one columns by stage
    await user.click(within(dialog).getByRole("option", { name: texts.backupTitle.ar }));
    expect(await screen.findByRole("heading", { name: texts.backupTitle.ar })).toBeInTheDocument();
    fireEvent.keyDown(document, { code: "KeyK", ctrlKey: true });
    dialog = await screen.findByRole("dialog", { name: texts.palette.ar });
    await user.click(within(dialog).getByRole("option", { name: texts.records.ar }));
    expect(await screen.findByRole("heading", { name: texts.records.ar })).toBeInTheDocument();
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
  });
});

describe("keyboard and layout", () => {
  it("F6 moves between top bar, canvas, chat and command bar", async () => {
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
    expect(order).toEqual(["topbar", "canvas", "chat", "command", "topbar"]);
    fireEvent.keyDown(document.activeElement!, { code: "F6", key: "F6", shiftKey: true });
    expect(where()).toBe("command");
  });

  it("below 900 px the chat is a sheet and the status folds into one button", async () => {
    screenWidth(true);
    setCurrentProject(P1);
    core();
    const sources = fakeSources({ status: { submission_date: inTwoWeeks, days_left: 14 } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => sources} />);
    await box();
    expect(screen.queryByRole("log")).toBeNull();
    expect(within(topBar()).queryByText(/فاضل 14 يوم/)).toBeNull();
    await user.click(within(topBar()).getByRole("button", { name: texts.deliverableStatus.ar }));
    expect(await screen.findByText(/فاضل 14 يوم/)).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await user.click(within(topBar()).getByRole("button", { name: texts.projectChat.ar }));
    expect(screen.getByRole("log", { name: texts.projectChat.ar })).toBeInTheDocument();
    await user.click(within(topBar()).getByRole("button", { name: texts.more.ar }));
    expect(await screen.findByRole("button", { name: texts.records.ar })).toBeInTheDocument();
  });

  it("sample mode shows the sample label in both languages", async () => {
    window.history.replaceState(null, "", "/?sample=1");
    setCurrentProject(P1);
    core();
    render(<App />);
    expect(await within(topBar()).findByText(texts.sampleData.ar)).toBeInTheDocument();
    expect(shown.props?.sources.saveFrames).toBeDefined();
    expect((await shown.props!.sources.files())[0]!.name).toMatch(/عينة/);
    act(() => setLanguage("en"));
    expect(within(screen.getByRole("banner", { name: texts.topBar.en })).getByText(texts.sampleData.en)).toBeInTheDocument();
  });

  it("Open full screen on a frame shows the Deliverable over the canvas; Close comes back", async () => {
    setCurrentProject(P1);
    core({ routes: { "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }) } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    act(() => shown.props!.onOpenFull("d1"));
    const close = await screen.findByRole("button", { name: texts.close.ar });
    expect(close).toHaveFocus();
    expect(screen.getByRole("region", { name: "canvas stand-in" }).closest("[inert]")).not.toBeNull();
    await user.click(close);
    expect(screen.getByRole("region", { name: "canvas stand-in" }).closest("[inert]")).toBeNull();
  });
});

describe("the Project Index", () => {
  it("opening a Deliverable from it closes the index, so nothing sits over the board; Close goes back to Deliverables", async () => {
    setCurrentProject(P1);
    core({ routes: { "GET /api/projects/p1/deliverables": () => Response.json({ deliverables: [entry()] }) } });
    const user = userEvent.setup();
    render(<App sourcesFor={() => fakeSources({})} />);
    await box();
    const opener = within(topBar()).getByRole("button", { name: texts.deliverablesButton.ar });
    await user.click(opener);
    const index = await screen.findByRole("region", { name: texts.deliverables.ar });
    await user.click(await within(index).findByRole("button", { name: entry().title }));
    await waitFor(() => expect(document.querySelector("[data-deliverable-panel]")).not.toBeNull());
    expect(screen.queryByRole("region", { name: texts.deliverables.ar })).toBeNull();
    await user.click(within(document.querySelector<HTMLElement>("[data-deliverable-panel]")!).getAllByRole("button", { name: texts.close.ar })[0]!);
    await waitFor(() => expect(document.querySelector("[data-deliverable-panel]")).toBeNull());
    expect(opener).toHaveFocus();
  });
});

describe("the import reports and the backup question", () => {
  afterEach(() => stopAsking());

  it("are cards at the chat's foot, never over the canvas, and a new one opens a folded chat", async () => {
    setCurrentProject(P1);
    core({
      routes: {
        "GET /api/projects": () => Response.json({ projects: [{ ...P1, open: true }] }),
        "GET /api/backup": () => Response.json({ folder: null }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
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
