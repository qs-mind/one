// Activity in other chats (chatActivity.ts): the top bar's mark, the projects' rows, the quiet notice at the chat's
// foot, the seen mark clearing, reduced motion; and the compact projects list. A mocked core; sample projects only.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../i18n";
import { currentProject, setCurrentProject } from "../records/project";
import { App } from "./App";
import { ACTIVITY_POLL, type ChatActivity } from "./chatActivity";
import { calls, core, P1, P2, type Route } from "./testing";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }));

const topBar = () => screen.getByRole("banner", { name: texts.topBar.ar });
const picker = () => screen.getByRole("region", { name: texts.projects.ar });
const words = { working: texts.activityWorking, waiting: texts.activityWaiting, failed: texts.activityFailed, done: texts.activityDone };
const elsewhereLabel = (state: keyof typeof words) => fill(texts.activityElsewhere.ar, { state: words[state].ar });
const chat = (chat_id: string, state: ChatActivity["state"], brief_id = "b1"): ChatActivity => ({
  chat_id,
  brief_id,
  state,
  name: chat_id === "general" ? null : chat_id === "p1" ? P1.name : P2.name,
});

/** The core's answers to GET /briefs/activity, one per poll; the last one stays. */
function answers(...seq: ChatActivity[][]): Route {
  let n = 0;
  return () => Response.json({ chats: seq[Math.min(n++, seq.length - 1)] });
}

function reducedMotion(on: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("reduce") ? on : false,
    media: query,
    addEventListener() {},
    removeEventListener() {},
  }));
}

const poll = ACTIVITY_POLL.ms;
beforeEach(() => {
  ACTIVITY_POLL.ms = 20;
  setLanguage("ar");
  setCurrentProject(undefined);
});
afterEach(() => {
  ACTIVITY_POLL.ms = poll;
  vi.unstubAllGlobals();
});

describe("the top bar's mark", () => {
  it.each(["working", "waiting", "failed", "done"] as const)("shows %s in another chat on the project button", async (state) => {
    core({ routes: { "GET /api/briefs/activity": answers([chat("p2", state)]) } });
    render(<App />);
    const button = within(topBar()).getByRole("button", { name: new RegExp(texts.generalChat.ar) });
    const mark = await within(button).findByRole("img", { name: elsewhereLabel(state) });
    expect(mark).toHaveAttribute("data-activity", state);
    if (state === "working") expect(mark.querySelector("[data-dots]")).not.toBeNull(); // the three dots fade in turn
    else expect(mark.querySelector("[data-dots]")).toBeNull(); // the others stand still
  });

  it("shows what most needs the engineer, and nothing for the chat on the screen", async () => {
    setCurrentProject(P1);
    core({
      routes: {
        "GET /api/projects/p1/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": answers([chat("p1", "waiting"), chat("general", "working"), chat("p2", "failed", "b2")]),
      },
    });
    render(<App />);
    expect(await within(topBar()).findByRole("img", { name: elsewhereLabel("failed") })).toBeInTheDocument();
    expect(within(topBar()).queryByRole("img", { name: elsewhereLabel("waiting") })).toBeNull(); // p1's own: on screen
  });

  it("stands still with reduced motion", async () => {
    reducedMotion(true);
    core({ routes: { "GET /api/briefs/activity": answers([chat("p2", "working")]) } });
    render(<App />);
    const mark = await within(topBar()).findByRole("img", { name: elsewhereLabel("working") });
    expect(mark.querySelector("[data-dots]")).toBeNull();
    expect(mark.querySelector("[data-still]")).not.toBeNull();
  });

  it("opening the chat clears its done mark, here and in the core", async () => {
    let seen = false;
    const fetch = core({
      routes: {
        "GET /api/projects/p2/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": () => Response.json({ chats: seen ? [] : [chat("p2", "done")] }),
        "POST /api/chat/p2/seen": () => {
          seen = true;
          return new Response(null, { status: 204 });
        },
      },
    });
    const user = userEvent.setup();
    render(<App />);
    expect(await within(topBar()).findByRole("img", { name: elsewhereLabel("done") })).toBeInTheDocument();
    await user.click(within(topBar()).getByRole("button", { name: new RegExp(texts.generalChat.ar) }));
    await user.click(await within(picker()).findByRole("button", { name: new RegExp(P2.name) }));
    await waitFor(() => expect(currentProject()?.id).toBe("p2"));
    await waitFor(() => expect(calls(fetch, "POST", "/api/chat/p2/seen").length).toBeGreaterThan(0));
    expect(within(topBar()).queryByRole("img")).toBeNull();
  });
});

describe("the projects' rows", () => {
  it("each row, General chat too, shows its mark and word; the open chat says Open", async () => {
    setCurrentProject(P1);
    core({
      routes: {
        "GET /api/projects/p1/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": answers([chat("general", "working"), chat("p2", "waiting"), chat("p1", "working")]),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await within(topBar()).findByRole("img", { name: elsewhereLabel("waiting") });
    await user.click(within(topBar()).getByRole("button", { name: new RegExp(P1.name) }));
    const general = await within(picker()).findByRole("button", { name: `${texts.generalChat.ar} ${texts.activityWorking.ar}` });
    expect(general.querySelector('[data-activity="working"]')).not.toBeNull();
    const tower = within(picker()).getByRole("button", { name: `${P2.name} ${texts.activityWaiting.ar}` });
    expect(tower.querySelector('[data-activity="waiting"]')).not.toBeNull();
    // the open project's row says Open, and what its Briefs do too (tender day: it had no mark)
    const school = within(picker()).getByRole("button", { name: `${P1.name} ${texts.open.ar} · ${texts.activityWorking.ar}` });
    expect(school.querySelector('[data-activity="working"]')).not.toBeNull();
  });

  it.each([
    ["failed", texts.activityFailed],
    ["done", texts.activityDone],
  ] as const)("says %s in words, in English too", async (state, word) => {
    setLanguage("en");
    core({ routes: { "GET /api/briefs/activity": answers([chat("p2", state)]) } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(within(screen.getByRole("banner")).getByRole("button", { name: new RegExp(texts.generalChat.en) }));
    const region = screen.getByRole("region", { name: texts.projects.en });
    expect(await within(region).findByRole("button", { name: `${P2.name} ${word.en}` })).toBeInTheDocument();
  });
});

describe("the notice from another chat", () => {
  it("says the work finished, and Open goes to that chat", async () => {
    const fetch = core({
      routes: {
        "GET /api/projects/p2/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": answers([chat("p2", "working")], [chat("p2", "working")], [chat("p2", "done")]),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    const line = fill(texts.activityNoticeDone.ar, { name: "⁨" + P2.name + "⁩" });
    const notice = await screen.findByRole("region", { name: line }, { timeout: 3000 });
    expect(notice).toHaveAttribute("data-activity-notice");
    expect(notice.closest("[data-notices]")).not.toBeNull(); // with the other cards at the chat's foot
    expect(screen.getAllByRole("region", { name: line })).toHaveLength(1); // one, and only once
    await user.click(within(notice).getByRole("button", { name: texts.activityOpen.ar }));
    await waitFor(() => expect(currentProject()?.id).toBe("p2"));
    expect(calls(fetch, "POST", "/api/projects/p2/open")).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole("region", { name: line })).toBeNull());
  });

  it("says another chat waits for you, and goes when it no longer waits", async () => {
    setCurrentProject(P2);
    core({
      routes: {
        "GET /api/projects/p2/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": answers([chat("general", "working")], [chat("general", "waiting")], [chat("general", "working")]),
      },
    });
    render(<App />);
    const line = fill(texts.activityNoticeWaiting.ar, { name: "⁨" + texts.generalChat.ar + "⁩" });
    expect(await screen.findByRole("region", { name: line })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("region", { name: line })).toBeNull());
  });

  it("never says «‹name› مستنيك» inside that same project's chat", async () => {
    setCurrentProject(P1);
    core({
      routes: {
        "GET /api/projects/p1/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": answers([chat("p1", "working")], [chat("p1", "waiting")]),
      },
    });
    render(<App />);
    await within(topBar()).findByRole("button", { name: new RegExp(P1.name) });
    await new Promise((r) => setTimeout(r, ACTIVITY_POLL.ms * 4));
    expect(screen.queryByRole("region", { name: fill(texts.activityNoticeWaiting.ar, { name: "⁨" + P1.name + "⁩" }) })).toBeNull();
  });

  it("the top bar's Waiting for you counts every project that waits, and goes to one", async () => {
    setCurrentProject(P1);
    core({
      routes: {
        "GET /api/projects/p1/files": () => Response.json({ files: [] }),
        "GET /api/projects/p2/files": () => Response.json({ files: [] }),
        "GET /api/briefs/activity": answers([chat("p2", "waiting")]),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    const waiting = await within(topBar()).findByRole("button", { name: fill(texts.waitingForYou.ar, { n: 1 }) });
    await user.click(waiting);
    await waitFor(() => expect(currentProject()?.id).toBe("p2"));
  });

  it("says a chat failed; Close takes it away; nothing ended before the screen looked makes one", async () => {
    core({
      routes: { "GET /api/briefs/activity": answers([chat("p1", "done")], [chat("p1", "done"), chat("p2", "failed")]) },
    });
    const user = userEvent.setup();
    render(<App />);
    const line = fill(texts.activityNoticeFailed.ar, { name: "⁨" + P2.name + "⁩" });
    const notice = await screen.findByRole("region", { name: line });
    expect(document.querySelectorAll("[data-activity-notice]")).toHaveLength(1); // p1's was old news: a mark only
    await user.click(within(notice).getByRole("button", { name: texts.close.ar }));
    expect(screen.queryByRole("region", { name: line })).toBeNull();
  });
});

describe("the compact projects list", () => {
  const open = async (user: ReturnType<typeof userEvent.setup>) => {
    await user.click(within(topBar()).getByRole("button", { name: new RegExp(texts.generalChat.ar) }));
    return within(picker()).findByRole("button", { name: P2.name });
  };

  it("New project turns into a field: Enter creates, Escape cancels", async () => {
    const fetch = core({
      routes: {
        "POST /api/projects": () => Response.json({ ...P1, open: true }, { status: 201 }),
        "GET /api/projects/p1/files": () => Response.json({ files: [] }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await open(user);
    expect(within(picker()).queryByRole("button", { name: texts.close.ar })).toBeNull(); // Escape or a click outside
    const row = within(picker()).getByRole("button", { name: texts.newProject.ar });
    await user.click(row);
    const field = within(picker()).getByRole("textbox", { name: texts.projectName.ar });
    expect(field).toHaveFocus();
    await user.type(field, "عينة");
    await user.keyboard("{Escape}");
    expect(picker()).toBeInTheDocument(); // only the field closed
    expect(within(picker()).queryByRole("textbox", { name: texts.projectName.ar })).toBeNull();
    expect(within(picker()).getByRole("button", { name: texts.newProject.ar })).toHaveFocus();

    await user.keyboard("{Enter}");
    await user.type(within(picker()).getByRole("textbox", { name: texts.projectName.ar }), "  مدرسة - عينة {Enter}");
    await waitFor(() => expect(currentProject()?.id).toBe("p1"));
    const [, init] = calls(fetch, "POST", "/api/projects")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({ name: "مدرسة - عينة" });
    expect(screen.queryByRole("region", { name: texts.projects.ar })).toBeNull();
  });

  it("the arrow keys move between the rows, one tab stop", async () => {
    core();
    const user = userEvent.setup();
    render(<App />);
    const first = await open(user);
    await waitFor(() => expect(first).toHaveFocus()); // the first project, one key press away
    await user.keyboard("{ArrowDown}");
    expect(within(picker()).getByRole("button", { name: P1.name })).toHaveFocus();
    await user.keyboard("{ArrowUp}{ArrowUp}");
    expect(within(picker()).getByRole("button", { name: new RegExp(texts.generalChat.ar) })).toHaveFocus();
    await user.keyboard("{End}");
    expect(within(picker()).getByRole("button", { name: texts.newProject.ar })).toHaveFocus();
    const stops = within(picker()).getAllByRole("button").filter((b) => b.tabIndex === 0);
    expect(stops).toHaveLength(1);
    expect(picker().querySelector("[data-glide]")).not.toBeNull(); // the gliding highlight
  });

  it("finds a project once there are more than six", async () => {
    const many = Array.from({ length: 7 }, (_, i) => ({ id: `p${i + 1}`, name: `مشروع ${i + 1} - عينة`, created_at: P1.created_at, open: false }));
    core({ routes: { "GET /api/projects": () => Response.json({ projects: many }) } });
    const user = userEvent.setup();
    render(<App />);
    await user.click(within(topBar()).getByRole("button", { name: new RegExp(texts.generalChat.ar) }));
    const search = await within(picker()).findByRole("searchbox", { name: texts.findProject.ar });
    await waitFor(() => expect(search).toHaveFocus());
    await user.type(search, "7");
    expect(within(picker()).getByRole("button", { name: many[6]!.name })).toBeInTheDocument();
    expect(within(picker()).queryByRole("button", { name: many[0]!.name })).toBeNull();
    await user.type(search, "9");
    expect(within(picker()).getByText(texts.noProjectMatch.ar)).toBeInTheDocument();
    await user.keyboard("{Escape}"); // clears the search first
    expect(search).toHaveValue("");
    expect(picker()).toBeInTheDocument();
  });
});
