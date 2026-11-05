import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { entry } from "../../deliverables/fixtures";
import { fill, setLanguage, texts } from "../../i18n";
import { workspaceApi } from "../../workspace/api";
import { DocumentsContext, type Documents } from "../../workspace/documents";
import { fakeSources, type FakeSources } from "../fake";
import type { AgentInfo, Team } from "../types";
import { startActivity } from "./activity";
import { TeamList } from "./TeamNow";

function agent(id: string, fields: Partial<AgentInfo> = {}): AgentInfo {
  return {
    id, kind: "specialist", role: { en: `Estimator ${id} (sample)`, ar: `مهندس التسعير ${id} - عينة` }, desk_id: null,
    model: "claude-sonnet-5", state: "working", line: null, brief_id: "b1", focus: null, at: "2026-11-05T09:00:00+00:00",
    ...fields,
  };
}

const documents: Documents = {
  deliverables: [entry({ id: "boq", title: "تسعير boq - عينة" })],
  clientBoqs: [],
  files: [],
  desks: [],
};

let stop: AbortController;

/** The team list in the chat's head, with the live team of fake sources. */
function showTeam(team: Team = { desks: [], agents: [] }): { fake: FakeSources } {
  const fake = fakeSources({ team });
  stop = new AbortController();
  startActivity(fake, stop.signal, team);
  render(
    <DocumentsContext.Provider value={{ ...documents, desks: team.desks }}>
      <TeamList />
    </DocumentsContext.Provider>,
  );
  return { fake };
}

const card = async (id: string) => {
  const list = screen.getByRole("list", { name: texts.projectTeam.ar });
  await waitFor(() => expect(list.querySelector(`[data-agent="${id}"]`)).not.toBeNull());
  return list.querySelector<HTMLElement>(`[data-agent="${id}"]`)!;
};

describe("the agent card", () => {
  beforeEach(() => {
    setLanguage("ar");
    workspaceApi.reset(null, () => true);
  });
  afterEach(() => {
    stop.abort();
    vi.unstubAllGlobals();
  });

  it("shows role, model, state in words and the Progress Line, never a raw id; what it is on opens that document", async () => {
    const est = agent("est", {
      line: { en: "Pricing item 3/02 (sample)", ar: "بيسعّر البند 3/02 - عينة" },
      focus: { frame: "deliverable:boq", anchor: { row: "3/02", column: "rate" } },
    });
    showTeam({ desks: [], agents: [est] });
    const el = await card("est");
    expect(el).toHaveTextContent("مهندس التسعير est - عينة");
    expect(within(el).getByText("claude-sonnet-5")).toHaveAttribute("dir", "ltr");
    expect(within(el).getByText("claude-sonnet-5").tagName).toBe("BDI");
    expect(el).toHaveTextContent(texts.stateWorking.ar);
    expect(el.querySelector("svg[aria-hidden]")).not.toBeNull(); // an icon beside the words, never colour alone
    expect(within(el).getByText("بيسعّر البند 3/02 - عينة")).toHaveAttribute("dir", "auto");
    const on = within(el).getByRole("button", {
      name: fill(texts.agentOnAt.ar, { title: "تسعير boq - عينة", place: fill(texts.anchorRow.ar, { row: "3/02" }) }),
    });
    expect(el.textContent).not.toMatch(/deliverable:|\brate\b|\bb1\b|\best\b(?! - )/);
    fireEvent.click(on);
    expect(workspaceApi.current()).toEqual({ key: "deliverable:boq", anchor: { row: "3/02", column: "rate" } });
  });

  it("fits its list: its words wrap, a long document name keeps to one line, nothing pushes it sideways", async () => {
    const est = agent("est", {
      line: { en: "Importing the BOQ (sample)", ar: "يستورد المقايسة من جدول كميات - عينة اختبار (sample BOQ).xlsx، شيت BOQ" },
      focus: { frame: "deliverable:boq", anchor: null },
    });
    showTeam({ desks: [], agents: [est] });
    const el = await card("est");
    expect(el).toHaveClass("min-w-0", "[overflow-wrap:anywhere]");
    const on = within(el).getByRole("button", { name: fill(texts.agentOn.ar, { title: "تسعير boq - عينة" }) });
    expect(on).toHaveClass("min-w-0", "max-w-full");
    expect(on.querySelector("[data-file-name]")).toHaveTextContent("تسعير boq - عينة"); // cut with «…», never the card
    expect(within(el).getByText("claude-sonnet-5")).toHaveClass("min-w-0", "truncate");
  });

  it("on something that is not a document (a Desk, the team), it names no place and has nothing to open", async () => {
    showTeam({ desks: [], agents: [agent("est", { focus: { frame: "team:core", anchor: null } })] });
    const el = await card("est");
    expect(within(el).queryByRole("button", { name: /على/ })).toBeNull();
  });

  it("its model has its company's logo; one not on the sheet has the neutral mark", async () => {
    showTeam({ desks: [], agents: [agent("est", { provider: "anthropic" }), agent("qs", { provider: null })] });
    const model = (id: string) => card(id).then((el) => within(el).getByText("claude-sonnet-5").closest("span")!);
    expect((await model("est")).querySelector("svg")).toHaveAttribute("data-logo", "claude");
    expect((await model("qs")).querySelector("svg")).toHaveAttribute("data-logo", "unknown");
  });

  it("its model by the name the sheet gives it, never the raw id (tender day: «models/gemini-3.1-flash-lite»)", async () => {
    showTeam({ desks: [], agents: [agent("est", { model: "models/gemini-3.1-flash-lite", model_name: "Gemini 3.1 Flash Lite" })] });
    const el = await card("est");
    expect(el).toHaveTextContent("Gemini 3.1 Flash Lite");
    expect(el).not.toHaveTextContent("models/");
  });

  it("its line is in its Brief's language, not the page's", async () => {
    setLanguage("en");
    showTeam({ desks: [], agents: [agent("est", { line: { en: "Look at the BOQ columns", ar: "يبص على أعمدة المقايسة" }, lang: "ar" })] });
    const list = screen.getByRole("list", { name: texts.projectTeam.en });
    await waitFor(() => expect(list.querySelector('[data-agent="est"]')).toHaveTextContent("يبص على أعمدة المقايسة"));
  });

  it("Stop calls the core for the agent's Brief", async () => {
    const fetch = vi.fn(async (url: string) =>
      url.startsWith("/api/briefs/") ? Response.json({ state: "stopped" }) : new Response(null, { status: 404 }),
    );
    vi.stubGlobal("fetch", fetch);
    showTeam({ desks: [], agents: [agent("est")] });
    const el = await card("est");
    fireEvent.click(within(el).getByRole("button", { name: fill(texts.stopRole.ar, { role: "مهندس التسعير est - عينة" }) }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/briefs/b1/stop", { method: "POST" }));
  });

  it("a Stop the core refuses says so", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(null, { status: url.startsWith("/api/briefs/") ? 500 : 404 })));
    showTeam({ desks: [], agents: [agent("est")] });
    const el = await card("est");
    fireEvent.click(within(el).getByRole("button", { name: fill(texts.stopRole.ar, { role: "مهندس التسعير est - عينة" }) }));
    expect(await within(el).findByRole("alert")).toHaveTextContent(texts.stopFailed.ar);
  });

  it("no Brief, no Stop; nothing to point at, nothing to open; never a Follow", async () => {
    showTeam({ desks: [], agents: [agent("est", { brief_id: null, focus: null })] });
    const el = await card("est");
    expect(within(el).queryByRole("button")).toBeNull();
    showTeam({ desks: [], agents: [agent("on", { focus: { frame: "deliverable:boq", anchor: null } })] });
    expect(screen.queryByRole("button", { name: texts.follow.ar })).toBeNull();
  });

  it("a silent agent's card says no news; a waiting one says it needs you in copper", async () => {
    const { fake } = showTeam({ desks: [], agents: [agent("est")] });
    const el = await card("est");
    act(() => fake.emit({ type: "agent", agent: agent("est", { state: "waiting" }) }));
    await waitFor(() => expect(el).toHaveTextContent(texts.stateWaiting.ar));
    expect(within(el).getByText(texts.stateWaiting.ar)).toHaveClass("text-copper");
  });

  it("the Lead QS shows thinking while the chat streams, before Plan 4", async () => {
    const { leadFromChat } = await import("./activity");
    showTeam();
    const list = screen.getByRole("list", { name: texts.projectTeam.ar });
    expect(list).toHaveTextContent(texts.roleLead.ar);
    act(() => leadFromChat(true));
    await waitFor(() => expect(list).toHaveTextContent(texts.stateThinking.ar));
    act(() => leadFromChat(false));
    await waitFor(() => expect(list).not.toHaveTextContent(texts.stateThinking.ar));
  });
});
