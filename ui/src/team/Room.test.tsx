import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactElement } from "react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { client, type Schemas } from "@/api/client";
import { listening, P1, P2, publish, server, startFakeCore } from "@/api/fakeCore";
import { paths } from "@/app/paths";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { team } from "@/texts/team";
import { text } from "@/texts/useText";
import { Room } from "./Room";

startFakeCore();
beforeEach(stubBrowser);
afterEach(resetPage);

// The words as the screen writes them, without the marks that keep an inserted value in one piece.
const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");
const id = (end: string | number) => "5a" + String(end).padStart(30, "0");

function open(dir: "rtl" | "ltr", ui: ReactElement) {
  const router = createMemoryRouter([{ path: "*", element: ui }], { initialEntries: [paths.room(P2)] });
  renderIn(dir, <RouterProvider router={router} />);
  return router;
}

const room = () => screen.findByRole("log");
const ids = (log: HTMLElement) => [...log.querySelectorAll("[data-message]")].map((el) => el.getAttribute("data-message")!.slice(-4));

describe.each(DIRS)("Room (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string | number>) => plain(text(pair, lang, vars));
  const pricing = lang === "ar" ? "مهندس التسعير - عينة" : "Pricing QS (sample)";

  it("draws the messages in the order written, the newest last, under the tender's name and the sample label", async () => {
    renderRoom();
    const log = await room();
    await waitFor(() => expect(ids(log)).toEqual(["7001", "7002", "7003", "7004", "7005", "7006"]));
    expect(document.querySelector('[data-place="room"]')).not.toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(text(team.roomTitle, lang));
    expect(await screen.findByText("برج إداري - عينة (sample)")).toBeInTheDocument();
    expect(screen.getByText(text(common.sample, lang))).toBeInTheDocument();
  });

  it("says who wrote to whom, and shows each source as a link that opens it", async () => {
    const router = renderRoom();
    const log = await room();
    const first = await waitFor(() => {
      const el = log.querySelector<HTMLElement>(`[data-message="${id(7001)}"]`);
      expect(el).not.toBeNull();
      expect(plain(el!.textContent)).toContain(pricing); // the member's name, once the team is in
      return el!;
    });
    expect(plain(first.textContent)).toContain(say(team.fromTo, { from: "Lead QS", to: pricing }));
    const engineer = log.querySelector<HTMLElement>(`[data-message="${id(7005)}"]`)!;
    expect(plain(engineer.textContent)).toContain(say(team.fromTo, { from: text(team.you, lang), to: text(team.everyone, lang) }));
    const words = within(first).getByText("ابدأ بتسعير القسم 3 (الخرسانة) من جدول الكميات - عينة (sample)");
    expect(words).toHaveAttribute("dir", "rtl");
    const link = within(first).getByRole("button", { name: /3\/02/ });
    await userEvent.click(link);
    expect(router.state.location.pathname).toBe(paths.doc(P2, id("f3")));
  });

  it("marks what the Lead raised to the engineer: waiting with the way to answer, or answered", async () => {
    const router = renderRoom();
    const log = await room();
    const raised = await waitFor(() => {
      const el = log.querySelector<HTMLElement>('[data-raised="waiting"]');
      expect(el).not.toBeNull();
      return el!;
    });
    expect(raised.getAttribute("data-message")).toBe(id(7006));
    expect(plain(raised.textContent)).toContain(say(team.raised, { name: "Lead QS" }));
    expect(log.querySelector('[data-raised="answered"]')!.getAttribute("data-message")).toBe(id(7004));
    expect(plain(log.textContent)).toContain(say(team.answered, { name: "Lead QS" }));
    await userEvent.click(within(raised).getByRole("link", { name: text(team.answer, lang) }));
    expect(router.state.location.pathname).toBe(paths.tender(P2));
  });

  it("the engineer's message posts to the room and appears at once", async () => {
    renderRoom();
    const log = await room();
    await waitFor(() => expect(ids(log)).toHaveLength(6));
    const box = screen.getByRole("textbox", { name: text(team.messageLabel, lang) });
    await userEvent.type(box, "راجعوا البند 9 تاني{Enter}");
    await waitFor(() => expect(ids(log)).toHaveLength(7));
    expect(log.querySelectorAll("[data-message]")[6]).toHaveTextContent("راجعوا البند 9 تاني");
    expect(box).toHaveValue("");
    const stored = (await client.GET("/projects/{project_id}/room", { params: { path: { project_id: P2 } } })).data!;
    expect(stored.messages[0]).toMatchObject({ from_id: "engineer", to_id: "team", text: "راجعوا البند 9 تاني" });
  });

  it("a refused message says why and keeps the words", async () => {
    const refusal = { en: "The Lead QS cannot work now.", ar: "الـ Lead QS مش قادر يشتغل دلوقتي." };
    server.use(http.post("*/api/projects/:id/room", () => HttpResponse.json({ error: refusal }, { status: 409 })));
    renderRoom();
    await room();
    const box = await screen.findByRole("textbox", { name: text(team.messageLabel, lang) });
    await userEvent.type(box, "ابدأوا");
    await userEvent.click(screen.getByRole("button", { name: text(common.send, lang) }));
    expect(await screen.findByText(text(refusal, lang))).toBeInTheDocument();
    expect(box).toHaveValue("ابدأوا");
  });

  it("moves with the room event: a new message comes in, a raised one turns answered", async () => {
    renderRoom();
    const log = await room();
    await waitFor(() => expect(ids(log)).toHaveLength(6));
    await waitFor(() => expect(listening(P2)).toBe(1));
    const fresh: Schemas["RoomMessage"] = {
      id: id(7100),
      from_id: "checking-qs",
      to_id: "lead-qs",
      text: "راجعت تحليل سعر البند 3/02 - عينة (sample)",
      sources: [],
      at: "2026-11-09T08:30:00.000000+00:00",
      raised: null,
    };
    act(() => publish(P2, { type: "room", message: fresh }));
    await waitFor(() => expect(ids(log).at(-1)).toBe("7100"));
    const old = { ...fresh, id: id(7099), at: "2026-11-09T07:00:00.000000+00:00" };
    act(() => publish(P2, { type: "room", message: old })); // older than the newest held: left to its page
    const answered = (await client.GET("/projects/{project_id}/room", { params: { path: { project_id: P2 } } })).data!.messages[0]!;
    act(() => publish(P2, { type: "room", message: { ...answered, raised: { id: answered.raised!.id, answered: true } } }));
    await waitFor(() => expect(log.querySelector('[data-raised="waiting"]')).toBeNull());
    expect(ids(log)).toEqual(["7001", "7002", "7003", "7004", "7005", "7006", "7100"]);
  });

  it("loads the older page when asked, above the ones it holds", async () => {
    const all = (await client.GET("/projects/{project_id}/room", { params: { path: { project_id: P2 } } })).data!.messages;
    server.use(
      http.get("*/api/projects/:id/room", ({ request }) => {
        const cursor = new URL(request.url).searchParams.get("cursor");
        return HttpResponse.json(cursor === "page-2" ? { messages: all.slice(3), next_cursor: null } : { messages: all.slice(0, 3), next_cursor: "page-2" });
      }),
    );
    renderRoom();
    const log = await room();
    await waitFor(() => expect(ids(log)).toEqual(["7004", "7005", "7006"]));
    await userEvent.click(screen.getByRole("button", { name: text(team.older, lang) }));
    await waitFor(() => expect(ids(log)).toEqual(["7001", "7002", "7003", "7004", "7005", "7006"]));
    expect(screen.queryByRole("button", { name: text(team.older, lang) })).toBeNull(); // the start of the room
  });

  it("an empty room says so and still takes a message", async () => {
    const router = createMemoryRouter([{ path: "*", element: <Room projectId={P1} /> }], { initialEntries: [paths.room(P1)] });
    renderIn(dir, <RouterProvider router={router} />);
    expect(await screen.findByText(text(team.roomEmpty, lang))).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: text(team.messageLabel, lang) })).toBeInTheDocument();
  });

  it("lists the team beside the room; pressing a member opens its identity and the way to its card", async () => {
    const router = renderRoom();
    const aside = await screen.findByRole("complementary", { name: text(team.teamTitle, lang) });
    const row = await within(aside).findByRole("button", { name: new RegExp(pricing.replace(/[()]/g, "\\$&")) });
    expect(plain(row.textContent)).toContain(text(team.temporary, lang));
    expect(plain(row.textContent)).toContain(text(team.firstTender, lang));
    await userEvent.click(row);
    expect(row).toHaveAttribute("aria-expanded", "true");
    const style = lang === "ar" ? "بيبني كل سعر من أجزاء ليها مصدر وبيوضّح المجموع. - عينة" : "Builds every rate from sourced parts and shows the sum. (sample)";
    expect(plain(aside.textContent)).toContain(say(team.styleLine, { value: style }));
    await userEvent.click(within(aside).getByRole("link", { name: text(team.openCard, lang) }));
    expect(router.state.location.pathname).toBe(paths.member(P2, id("c2")));
  });

  function renderRoom() {
    return open(dir, <Room projectId={P2} />);
  }
});
