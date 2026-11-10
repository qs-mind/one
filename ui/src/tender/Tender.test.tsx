import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { P1, P2, P3, publish, server, startFakeCore } from "@/api/fakeCore";
import { client } from "@/api/client";
import { paths } from "@/app/paths";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Tender } from "./Tender";

startFakeCore();

// Today's routes the place reads beside the contract's: the stored conversation and the tender's documents.
let requested: string[];
beforeEach(() => {
  stubBrowser();
  requested = [];
  server.use(
    http.get("*/api/chat/:id/messages", () => HttpResponse.json({ messages: [] })),
    http.get("*/api/chat/:id/stream", () => new HttpResponse(null, { status: 204 })),
    http.get("*/api/projects/:id/deliverables", () => HttpResponse.json({ deliverables: [] })),
    http.get("*/api/projects/:id/files", () => HttpResponse.json({ files: [] })),
    http.post("*/api/projects/:id/plan/request", ({ request }) => {
      requested.push(new URL(request.url).pathname);
      return HttpResponse.json({ brief_id: "5a" + "b".repeat(30) }, { status: 202 });
    }),
  );
});
afterEach(resetPage);

const ROUTES = ["/tender/:id", "/tender/:id/doc/:docId", "/tender/:id/room", "/tender/:id/member/:memberId"];

function open(path: string, dir: "rtl" | "ltr" = "ltr") {
  const router = createMemoryRouter(
    ROUTES.map((p) => ({ path: p, element: <Tender /> })),
    { initialEntries: [path] },
  );
  renderIn(dir, <RouterProvider router={router} />);
  return router;
}

const side = () => screen.findByRole("complementary");

describe.each(DIRS)("the tender place (%s)", (dir) => {
  it("shows the header, what waits, the stages and the team beside the thread", async () => {
    open(paths.tender(P1), dir);
    const aside = await side();
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent("مجمع مدارس");
    await waitFor(() => expect(aside.querySelectorAll("[data-stage]")).toHaveLength(7));
    expect(aside.querySelector('[data-waiting="plan"] button')).not.toBeNull();
    const team = within(aside).getAllByRole("link");
    expect(team.map((a) => a.getAttribute("href"))).toEqual(
      expect.arrayContaining([paths.member(P1, "lead-qs"), paths.room(P1)]),
    );
    expect(screen.getByRole("log")).toBeTruthy();
  });

  it("asks the Lead for a plan when the tender has none", async () => {
    open(paths.tender(P3), dir);
    const ask = await screen.findByRole("button", { name: dir === "rtl" ? /اطلب من الـ Lead QS/ : /Ask the Lead QS/ });
    await userEvent.click(ask);
    expect(await screen.findByText(dir === "rtl" ? "الـ Lead QS بيكتب الخطة" : "The Lead QS is writing the plan")).toBeTruthy();
    expect(requested).toEqual([`/api/projects/${P3}/plan/request`]);
    expect(screen.queryByRole("button", { name: /Ask the Lead QS|اطلب من/ })).toBeNull();
  });
});

describe("a document beside a narrow thread", () => {
  it("replaces the side column, and Close goes back to the conversation", async () => {
    const router = open(paths.doc(P2, "view:project-map"));
    expect(await screen.findByRole("region", { name: "Open document" })).toBeTruthy();
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(screen.getByRole("log")).toBeTruthy(); // the narrow thread stays
    expect(screen.getByRole("separator", { name: /Width of the conversation/ })).toBeTruthy();
    await userEvent.click(screen.getByRole("link", { name: "Close the document" }));
    expect(router.state.location.pathname).toBe(paths.tender(P2));
    expect(await side()).toBeTruthy();
  });

  it("goes full screen by its route and back", async () => {
    const router = open(paths.doc(P2, "view:project-map"));
    const full = await screen.findByRole("button", { name: "Full screen" });
    await userEvent.click(full);
    expect(router.state.location.search).toBe("?full");
    await waitFor(() => expect(screen.queryByRole("log")).toBeNull());
    await userEvent.click(screen.getByRole("button", { name: "Full screen", pressed: true }));
    expect(router.state.location.search).toBe("");
    expect(await screen.findByRole("log")).toBeTruthy();
  });

  it("opens the team room and a member's card in the document's place", async () => {
    open(paths.room(P2));
    await screen.findByRole("region", { name: "Open document" });
    expect(document.querySelector('[data-place="room"]')).not.toBeNull();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Team room");
    resetPage();
    document.body.innerHTML = "";
    open(paths.member(P2, "lead-qs"));
    expect(await screen.findByRole("heading", { level: 1, name: "Lead QS" })).toBeTruthy();
    expect(document.querySelector('[data-place="member"]')).not.toBeNull();
  });

  it("says when the route names no document it can open", async () => {
    open(paths.doc(P2, "d1"));
    expect(await screen.findByRole("alert")).toHaveTextContent("cannot be opened here");
  });
});

describe("live", () => {
  it("follows the plan's events", async () => {
    open(paths.tender(P3));
    await screen.findByRole("button", { name: /Ask the Lead QS/ });
    await waitFor(() => expect(document.querySelector("[data-noplan]")).not.toBeNull());
    const { data } = await client.GET("/projects/{project_id}/plan", { params: { path: { project_id: P1 } } });
    publish(P3, { type: "plan", plan: data!.plan });
    await waitFor(() => expect(document.querySelector("[data-noplan]")).toBeNull());
    expect((await side()).querySelectorAll("[data-stage]")).toHaveLength(7);
  });
});
