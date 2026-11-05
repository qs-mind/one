import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../../i18n";
import { currentSelection, select } from "../selection";
import { agent, paneSize, restorePane, showCanvas } from "./testing";

const team = () => screen.findByRole("group", { name: texts.projectTeam.ar });
const card = async (id: string) => {
  const frame = await team();
  await waitFor(() => expect(frame.querySelector(`[data-agent="${id}"]`)).not.toBeNull());
  return frame.querySelector<HTMLElement>(`[data-agent="${id}"]`)!;
};

describe("the agent card", () => {
  beforeEach(() => {
    paneSize();
    setLanguage("ar");
  });
  afterEach(() => {
    restorePane();
    select([]);
  });

  it("shows role, model, state in words and the Progress Line, never a raw id", async () => {
    const est = agent("est", {
      line: { en: "Pricing item 3/02 (sample)", ar: "بيسعّر البند 3/02 - عينة" },
      focus: { frame: "deliverable:boq", anchor: { row: "3/02", column: "rate" } },
    });
    showCanvas({ team: { desks: [], agents: [est] } });
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
    await waitFor(() => expect(currentSelection()).toEqual([{ kind: "deliverable", id: "boq", title: "تسعير boq - عينة" }]));
  });

  it("its line is in its Brief's language, not the page's", async () => {
    setLanguage("en");
    const est = agent("est", { line: { en: "Look at the BOQ columns", ar: "يبص على أعمدة المقايسة" }, lang: "ar" });
    showCanvas({ team: { desks: [], agents: [est] } });
    const frame = await screen.findByRole("group", { name: texts.projectTeam.en });
    await waitFor(() => expect(frame.querySelector('[data-agent="est"]')).toHaveTextContent("يبص على أعمدة المقايسة"));
  });

  it("Stop calls the core for the agent's Brief", async () => {
    const fetch = vi.fn(async (url: string) =>
      url.startsWith("/api/briefs/") ? Response.json({ state: "stopped" }) : new Response(null, { status: 404 }),
    );
    vi.stubGlobal("fetch", fetch);
    showCanvas({ team: { desks: [], agents: [agent("est")] } });
    const el = await card("est");
    fireEvent.click(within(el).getByRole("button", { name: fill(texts.stopRole.ar, { role: "مهندس التسعير est - عينة" }) }));
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/briefs/b1/stop", { method: "POST" }));
  });

  it("a Stop the core refuses says so", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(null, { status: url.startsWith("/api/briefs/") ? 500 : 404 })));
    showCanvas({ team: { desks: [], agents: [agent("est")] } });
    const el = await card("est");
    fireEvent.click(within(el).getByRole("button", { name: fill(texts.stopRole.ar, { role: "مهندس التسعير est - عينة" }) }));
    expect(await within(el).findByRole("alert")).toHaveTextContent(texts.stopFailed.ar);
  });

  it("no Brief, no Stop; nothing to point at, no Follow", async () => {
    showCanvas({ team: { desks: [], agents: [agent("est", { brief_id: null, focus: null })] } });
    const el = await card("est");
    expect(within(el).queryByRole("button")).toBeNull();
  });

  it("a silent agent's card says no news; a waiting one says it needs you in copper", async () => {
    const { fake } = showCanvas({ team: { desks: [], agents: [agent("est")] } });
    const el = await card("est");
    act(() => fake.emit({ type: "agent", agent: agent("est", { state: "waiting" }) }));
    await waitFor(() => expect(el).toHaveTextContent(texts.stateWaiting.ar));
    expect(within(el).getByText(texts.stateWaiting.ar)).toHaveClass("text-copper");
  });

  it("the Lead QS shows thinking while the chat streams, before Plan 4", async () => {
    const { leadFromChat } = await import("./activity");
    showCanvas();
    const frame = await team();
    expect(frame).toHaveTextContent(texts.roleLead.ar);
    act(() => leadFromChat(true));
    await waitFor(() => expect(frame).toHaveTextContent(texts.stateThinking.ar));
    act(() => leadFromChat(false));
    await waitFor(() => expect(frame).not.toHaveTextContent(texts.stateThinking.ar));
  });
});
