import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../../i18n";
import { Cursors } from "./Cursors";
import { following, stopFollowing } from "./follow";
import { Following } from "../../project/live/TeamNow";
import { agent, paneSize, restorePane, showCanvas, viewport } from "./testing";

const role = "مهندس التسعير est - عينة";
// frames are 700 × 500 in a 1200 × 800 pane at zoom 1: centring one puts its corner at (250, 150) on screen
const centred = (x: number, y: number) => `translate(${600 - (x + 350)}px,${400 - (y + 250)}px) scale(1)`;

describe("following an agent", () => {
  beforeEach(() => {
    paneSize();
    setLanguage("ar");
    // reduced motion: the view moves at once, so the test needs no timers
    vi.stubGlobal("matchMedia", (query: string) => ({ matches: query.includes("reduce"), media: query, addEventListener() {}, removeEventListener() {} }));
  });
  afterEach(() => {
    restorePane();
    stopFollowing();
  });

  it("pans to the agent's frame and to its next one; a manual zoom stops it", async () => {
    const { fake, container } = showCanvas({ team: { desks: [], agents: [agent("est")] } }, <Cursors />, <Following />);
    const team = await screen.findByRole("group", { name: texts.projectTeam.ar });
    const button = await within(team).findByRole("button", { name: fill(texts.followRole.ar, { role }) });
    fireEvent.click(button);
    await waitFor(() => expect(viewport(container)).toBe(centred(0, 0)));
    expect(screen.getByText(fill(texts.following.ar, { role }))).toBeInTheDocument();

    act(() => fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "deliverable:quotes", anchor: null } }) }));
    await waitFor(() => expect(viewport(container)).toBe(centred(3000, 0)));

    await act(() => new Promise((r) => setTimeout(r, 150))); // past our own move
    fireEvent.click(screen.getByRole("button", { name: texts.zoomIn.ar }));
    await waitFor(() => expect(following()).toBeNull());
    expect(screen.queryByText(fill(texts.following.ar, { role }))).toBeNull();
    const after = viewport(container);
    act(() => fake.emit({ type: "agent", agent: agent("est", { focus: { frame: "deliverable:boq", anchor: null } }) }));
    await act(() => new Promise((r) => setTimeout(r, 50)));
    expect(viewport(container)).toBe(after);
  });

  it("the top bar's stop button ends it", async () => {
    showCanvas({ team: { desks: [], agents: [agent("est")] } }, <Cursors />, <Following />);
    const team = await screen.findByRole("group", { name: texts.projectTeam.ar });
    fireEvent.click(await within(team).findByRole("button", { name: fill(texts.followRole.ar, { role }) }));
    // the card's own button says the same; the top bar's comes after the canvas
    await waitFor(() => expect(screen.getAllByRole("button", { name: texts.stopFollowing.ar })).toHaveLength(2));
    fireEvent.click(screen.getAllByRole("button", { name: texts.stopFollowing.ar }).at(-1)!);
    await waitFor(() => expect(following()).toBeNull());
  });

  it("an agent that finishes is no longer followed", async () => {
    const { fake } = showCanvas({ team: { desks: [], agents: [agent("est")] } }, <Cursors />);
    const team = await screen.findByRole("group", { name: texts.projectTeam.ar });
    fireEvent.click(await within(team).findByRole("button", { name: fill(texts.followRole.ar, { role }) }));
    expect(following()).toBe("est");
    act(() => fake.emit({ type: "agent", agent: agent("est", { state: "done" }) }));
    await waitFor(() => expect(following()).toBeNull());
  });
});
