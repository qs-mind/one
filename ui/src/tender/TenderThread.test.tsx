// The tender's conversation column on the fake core: a stage signed off from its block, a waiting item that brings
// its place into view, a message the core refused, files dropped on the box, the box while the Lead cannot work, the
// Lead's name before the team is read, and a plan request that got no answer.
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { client } from "@/api/client";
import { P1, P3, scenario, server, stageEnds, startFakeCore } from "@/api/fakeCore";
import { paths } from "@/app/paths";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { setCurrentProject } from "@/records/project";
import { cards } from "@/texts/cards";
import { tender as texts } from "@/texts/tender";
import { plural, text } from "@/texts/useText";
import { Tender } from "./Tender";
import { refusalOf } from "./useThread";

startFakeCore();

let calls: string[];
let unhandled: string[];
server.events.on("request:unhandled", ({ request }) => unhandled.push(`${request.method} ${new URL(request.url).pathname}`));
const stored = (messages: unknown[]) => http.get("*/api/chat/:id/messages", () => HttpResponse.json({ messages }));
beforeEach(() => {
  stubBrowser();
  calls = [];
  unhandled = [];
  Element.prototype.scrollIntoView = vi.fn();
  const note = (request: Request) => calls.push(`${request.method} ${new URL(request.url).pathname}`);
  server.use(
    http.post("*/api/projects/:id/open", ({ params }) => HttpResponse.json({ id: params.id, name: "sample", created_at: "2026-11-01T09:00:00Z", open: true })),
    stored([]),
    http.get("*/api/chat/:id/stream", () => new HttpResponse(null, { status: 204 })),
    http.get("*/api/projects/:id/deliverables", () => HttpResponse.json({ deliverables: [] })),
    http.get("*/api/projects/:id/files", () => HttpResponse.json({ files: [] })),
    http.post("*/api/projects/:id/files", ({ request }) => {
      note(request);
      return HttpResponse.json({ id: "f1" });
    }),
    http.post("*/api/projects/:id/files/report", ({ request }) => {
      note(request);
      return HttpResponse.json({});
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  resetPage();
  setCurrentProject(undefined);
  expect(unhandled).toEqual([]);
});

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

function open(id: string, dir: "rtl" | "ltr" = "ltr") {
  const router = createMemoryRouter([{ path: "/tender/:id", element: <Tender /> }], { initialEntries: [paths.tender(id)] });
  renderIn(dir, <RouterProvider router={router} />);
}
const box = () => screen.findByRole("textbox");

describe("the tender's conversation", () => {
  it("signs off a stage from its block, and the waiting item brings that block into view", async () => {
    const { data } = await client.GET("/projects/{project_id}/plan", { params: { path: { project_id: P1 } } });
    await client.POST("/projects/{project_id}/plan/approve", { params: { path: { project_id: P1 } }, body: { version: data!.plan!.version } });
    stageEnds(P1);
    const stage = (await client.GET("/projects/{project_id}/plan", { params: { path: { project_id: P1 } } })).data!.plan!.stages[0]!;
    open(P1);
    const sign = await screen.findByRole("button", { name: text(cards.signOff, "en") });
    const item = document.querySelector('[data-waiting="stage"] button') as HTMLElement;
    await userEvent.click(item);
    const place = document.querySelector(`[data-part="${stage.id}"]`) as HTMLElement;
    expect(place.scrollIntoView).toHaveBeenCalled();
    fireEvent.click(sign);
    fireEvent.click(sign); // a hold, the way a screen reader holds
    // drawn from the route alone, it leaves once signed off; the plan holds the stage as approved
    await waitFor(() => expect(document.querySelector("[data-signoff]")).toBeNull());
    const after = await client.GET("/projects/{project_id}/plan", { params: { path: { project_id: P1 } } });
    expect(after.data!.plan!.stages[0]!.status).toBe("approved");
  });

  it("says the core's words when it refuses a message", async () => {
    const words = { en: "No AI is connected (sample).", ar: "مفيش ذكاء اصطناعي متوصل - عينة" };
    server.use(
      http.post("*/api/chat", () =>
        new HttpResponse(`data: ${JSON.stringify({ type: "error", errorText: JSON.stringify(words) })}\n\n`, {
          headers: { "content-type": "text/event-stream" },
        }),
      ),
    );
    open(P1);
    await userEvent.type(await box(), "Price the concrete{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(words.en);
  });

  it("steers a message that found other work running to that work, and joins it", async () => {
    let steered: unknown = null;
    server.use(
      http.post("*/api/chat", () => HttpResponse.json({ brief_id: "b7" }, { status: 409 })),
      http.post("*/api/briefs/:id/steer", async ({ params, request }) => {
        steered = { id: params.id, body: await request.json() };
        return new HttpResponse(null, { status: 202 });
      }),
    );
    open(P1);
    await userEvent.type(await box(), "Start with the concrete{Enter}");
    await waitFor(() => expect(steered).toEqual({ id: "b7", body: { text: "Start with the concrete" } }));
    // not a message of its own: it comes back as the work's steer
    await waitFor(() => expect(screen.queryByText("Start with the concrete")).toBeNull());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("says the words were not sent when the work running refused them too", async () => {
    server.use(
      http.post("*/api/chat", () => HttpResponse.json({ brief_id: "b7" }, { status: 409 })),
      http.post("*/api/briefs/:id/steer", () => HttpResponse.json({ error: { en: "x", ar: "س" } }, { status: 409 })),
    );
    open(P1);
    await userEvent.type(await box(), "Start with the concrete{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(text(cards.messageNotSent, "en"));
    expect(screen.getByText("Start with the concrete")).toBeInTheDocument();
  });

  it("puts files dropped on the box into the tender, then sends the words", async () => {
    server.use(
      http.post("*/api/chat", ({ request }) => {
        calls.push(`POST ${new URL(request.url).pathname}`);
        return new HttpResponse(null, { status: 204 });
      }),
    );
    open(P1);
    const field = await box();
    const file = new File(["%PDF"], "addendum.pdf", { type: "application/pdf" });
    fireEvent.drop(field.closest("form")!, { dataTransfer: { files: [file], items: [], types: ["Files"] } });
    await userEvent.type(field, "please read this{Enter}");
    await waitFor(() =>
      expect(calls).toEqual([`POST /api/projects/${P1}/files`, `POST /api/projects/${P1}/files/report`, "POST /api/chat"]),
    );
    expect(await screen.findByText(plural(cards.filesIn, 1, "en"))).toBeInTheDocument();
  });

  it("turns the box off while the Lead cannot work", async () => {
    scenario(`tender:${P3}:blocked` as never);
    open(P3);
    await waitFor(async () => expect(await box()).toBeDisabled());
  });

  it("names the Lead in Arabic before the team is read", async () => {
    server.use(
      http.get("*/api/projects/:id/members", () => HttpResponse.json({ error: { en: "x", ar: "س" } }, { status: 500 })),
      stored([{ id: "b1-reply", role: "assistant", parts: [{ type: "text", text: "تمام" }] }]),
    );
    open(P1, "rtl");
    expect(await screen.findByText(text(cards.leadName, "ar"))).toBeInTheDocument();
  });

  it("keeps the plan button when the request got no answer", async () => {
    server.use(http.post("*/api/projects/:id/plan/request", () => HttpResponse.error()));
    open(P3);
    await userEvent.click(await screen.findByRole("button", { name: /Ask the Lead QS/ }));
    expect(await screen.findByText(text(texts.failed, "en"))).toBeInTheDocument();
    expect(screen.queryByText(text(texts.planAsked, "en"))).toBeNull();
    expect(screen.getByRole("button", { name: /Ask the Lead QS/ })).toBeEnabled();
  });
});

describe("refusalOf", () => {
  it("reads the core's words, and a message that found other work running", () => {
    expect(refusalOf(new Error(JSON.stringify({ en: "e", ar: "ع", fix: "ai" })))).toEqual({ words: { en: "e", ar: "ع" }, busy: null });
    expect(refusalOf(new Error(JSON.stringify({ brief_id: "b1" })))).toEqual({ words: null, busy: "b1" });
    expect(refusalOf(new Error("Failed to fetch"))).toEqual({ words: null, busy: null });
    expect(refusalOf(undefined)).toBeNull();
  });
});
