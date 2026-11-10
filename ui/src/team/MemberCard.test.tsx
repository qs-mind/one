import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { client } from "@/api/client";
import { listening, P1, P2, publish, startFakeCore } from "@/api/fakeCore";
import { paths } from "@/app/paths";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { formatNumber } from "@/texts/format";
import { team } from "@/texts/team";
import { plural, text } from "@/texts/useText";
import { MemberCard } from "./MemberCard";

startFakeCore();
beforeEach(stubBrowser);
afterEach(resetPage);

const plain = (value: string | null | undefined) => (value ?? "").replace(/[⁦⁨⁩]/g, "");
const id = (end: string) => "5a" + end.padStart(30, "0");

function open(dir: "rtl" | "ltr", projectId: string, memberId: string) {
  const router = createMemoryRouter([{ path: "*", element: <MemberCard projectId={projectId} memberId={memberId} /> }], {
    initialEntries: [paths.member(projectId, memberId)],
  });
  renderIn(dir, <RouterProvider router={router} />);
  return router;
}

describe.each(DIRS)("MemberCard (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const say = (pair: { en: string; ar: string }, vars?: Record<string, string | number>) => plain(text(pair, lang, vars));
  const page = () => plain(document.querySelector('[data-place="member"]')?.textContent);

  it("shows the Lead's whole identity and the real record of its work", async () => {
    open(dir, P2, "lead-qs");
    expect(await screen.findByRole("heading", { level: 1, name: "Lead QS" })).toBeInTheDocument();
    expect(document.querySelector('[data-place="member"]')).toHaveAttribute("data-member", "lead-qs");
    const lead = (await client.GET("/projects/{project_id}/members", { params: { path: { project_id: P2 } } })).data!.members[0]!;
    for (const pair of [lead.title, lead.speciality, lead.style, ...lead.tools.map((tool) => tool.title)]) expect(page()).toContain(text(pair, lang));
    expect(page()).toContain(text(team.fixed, lang));
    expect(page()).toContain(say(team.modelBy, { name: "Claude (sample)", provider: "Anthropic" }));
    expect(page()).toContain(text(team.offDevice, lang));
    expect(page()).toContain(plain(plural(team.workedWith, 5, lang)));
    expect(page()).toContain(say(team.checks, { passed: 4, total: 5 }));
    const cost = formatNumber(6.85, lang, { style: "currency", currency: "USD" });
    expect(page()).toContain(say(team.cost, { cost }));
    expect(page()).toContain(text(lead.doing!, lang)); // waiting for the engineer's decision
  });

  it("a temporary member reads first tender with you, with no experience it has not had", async () => {
    open(dir, P2, id("c2"));
    await screen.findByRole("heading", { level: 1 });
    expect(page()).toContain(text(team.temporary, lang));
    expect(page()).toContain(text(team.firstTender, lang));
    expect(page()).not.toContain(plain(plural(team.workedWith, 1, lang)));
  });

  it("the Checking QS is independent; nothing of its own is checked", async () => {
    open(dir, P2, "checking-qs");
    await screen.findByRole("heading", { level: 1, name: "Checking QS" });
    expect(page()).toContain(text(team.independent, lang));
    expect(page()).toContain(text(team.checksNone, lang));
  });

  it("a member proposed with the plan says so", async () => {
    open(dir, P1, id("c3"));
    await screen.findByRole("heading", { level: 1 });
    expect(page()).toContain(text(team.proposed, lang));
    expect(page()).toContain(text(team.firstTender, lang));
  });

  it("an id this tender does not hold says so, with the way back to the room", async () => {
    const router = open(dir, P2, id("99"));
    expect(await screen.findByText(text(team.notInTender, lang))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("link", { name: text(team.backToRoom, lang) }));
    expect(router.state.location.pathname).toBe(paths.room(P2));
  });

  it("moves with the member event: its line, and a model that can no longer be used", async () => {
    open(dir, P2, "lead-qs");
    await screen.findByRole("heading", { level: 1 });
    await waitFor(() => expect(listening(P2)).toBe(1));
    const lead = (await client.GET("/projects/{project_id}/members", { params: { path: { project_id: P2 } } })).data!.members[0]!;
    const doing = { en: "Reading 02 الشروط الخاصة.pdf (sample)", ar: "بيقرا 02 الشروط الخاصة.pdf - عينة" };
    act(() => publish(P2, { type: "member", member: { ...lead, state: "working", doing, model: null } }));
    await waitFor(() => expect(page()).toContain(text(doing, lang)));
    expect(page()).toContain(text(team.noModel, lang));
  });
});
