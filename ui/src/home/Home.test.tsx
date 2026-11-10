import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Schemas } from "@/api/client";
import { P1, P2, P3, P4, P5, scenario, server, startFakeCore } from "@/api/fakeCore";
import { paths } from "@/app/paths";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { home } from "@/texts/home";
import { plural, text } from "@/texts/useText";
import { Home } from "./Home";

startFakeCore();

const NEW = "5a" + "e1".padStart(30, "0");
type Call = { path: string; query: URLSearchParams; body: unknown };
let calls: Call[];

beforeEach(() => {
  stubBrowser();
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 10, 9, 9, 0)); // the sample day, in the morning
  calls = [];
  const note = async (request: Request) => {
    const url = new URL(request.url);
    const raw = await request.text().catch(() => "");
    let body: unknown = raw;
    try {
      body = JSON.parse(raw);
    } catch {
      // a file's bytes
    }
    calls.push({ path: url.pathname.replace(/^\/api/, ""), query: url.searchParams, body });
  };
  server.use(
    http.get("*/api/chat/general/messages", () => HttpResponse.json({ messages: [] })),
    http.post("*/api/projects", async ({ request }) => (await note(request), HttpResponse.json({ id: NEW }, { status: 201 }))),
    http.post("*/api/projects/:id/files", async ({ request }) => {
      await note(request);
      return HttpResponse.json({ id: "5a" + String(calls.length).padStart(30, "f"), status: "read" }, { status: 201 });
    }),
    http.post("*/api/projects/:id/files/report", async ({ request }) => (await note(request), new HttpResponse(null, { status: 201 }))),
    http.post("*/api/projects/:id/understand", async ({ request }) => (await note(request), HttpResponse.json({ brief_id: NEW }, { status: 202 }))),
    http.post("*/api/projects/:id/open", async ({ request }) => (await note(request), HttpResponse.json({ id: P1 }))),
  );
});
afterEach(() => {
  vi.useRealTimers();
  resetPage();
});

function open(dir: "rtl" | "ltr") {
  // Home, and where it leads (the places themselves are other jobs').
  const routes = [
    { path: paths.home, element: <Home /> },
    { path: "/tender/:id", element: <main data-place="tender" /> },
    { path: "/settings/:section", element: <main data-place="settings" /> },
  ];
  const router = createMemoryRouter(routes, { initialEntries: [paths.home] });
  renderIn(dir, <RouterProvider router={router} />);
  return router;
}

const ready = () => waitFor(() => expect(document.querySelector('[data-place="home"]:not([aria-busy])')).not.toBeNull());
const section = (name: string) => screen.getByRole("region", { name });

/** A drop as the browser hands it: a folder with two files (one in a sub-folder), or loose files. */
function folderDrop(name: string) {
  const file = (n: string) => ({ isFile: true, isDirectory: false, name: n, file: (ok: (f: File) => void) => ok(new File(["x"], n)) });
  const dir = (n: string, children: object[]) => {
    let given = false;
    return {
      isFile: false,
      isDirectory: true,
      name: n,
      createReader: () => ({ readEntries: (ok: (e: object[]) => void) => ok(given ? [] : ((given = true), children)) }),
    };
  };
  const root = dir(name, [file("01 BOQ.xlsx"), dir("Drawings", [file("A-101.pdf")])]);
  return { types: ["Files"], files: [], items: [{ kind: "file", getAsFile: () => null, webkitGetAsEntry: () => root }] };
}

describe.each(DIRS)("Home (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: Schemas["Text"], vars?: Record<string, string | number>) => text(pair, lang, vars);
  const box = () => screen.getByRole("textbox");

  it("greets by first name, shows the Lead's summary, what waits and the tenders in the core's order", async () => {
    open(dir);
    await ready();
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("مهندس - عينة (sample)"));
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain(t(home.morningNoName));
    expect(screen.getByText(/3 حاجات مستنية ردّك/)).toBeInTheDocument();
    expect(screen.getByText(plural(home.leftOut, 1, lang))).toBeInTheDocument(); // P3 is Confidential

    const waiting = within(section(t(home.waiting)));
    const items = waiting.getAllByRole("link");
    expect(items.map((a) => a.getAttribute("href"))).toEqual([P2, P1, P2, P3].map(paths.tender));
    expect(items[1]).toHaveTextContent(t({ en: "Approve the tender plan", ar: "اعتمد خطة العطاء" }));
    expect(items[3]).toHaveTextContent("إمتى آخر موعد لتقديم العطاء؟");
    expect(items[1]).toHaveTextContent(t(home.workStopped));
    expect(items[0]).not.toHaveTextContent(t(home.workStopped)); // a Suggested change does not stop the work

    const rows = within(section(t(common.tenders))).getAllByRole("link");
    expect(rows.map((a) => a.getAttribute("href"))).toEqual([P2, P1, P5, P3, P4].map(paths.tender));
    expect(rows[0]).toHaveTextContent(plural(common.daysLeft, 7, lang));
    expect(rows[0]!.querySelector(".font-bold")).not.toBeNull(); // the nearest deadline
    expect(rows[1]).toHaveTextContent(plural(common.daysLeft, 12, lang));
    expect(rows[2]).toHaveTextContent(t({ en: "Project 2026-11-09", ar: "مشروع 2026-11-09" }));
    expect(rows[3]).toHaveTextContent(t(home.confidential));
    expect(rows[4]).toHaveTextContent(t(home.finished));
    expect(within(rows[0]!).getByRole("img")).toHaveAccessibleName(
      t(home.stageOf, { n: 4, total: 6, stage: t({ en: "Pricing the BOQ (sample)", ar: "تسعير جدول الكميات - عينة" }) }),
    );
    expect(screen.getByText(t(home.cannotOpen))).toBeInTheDocument(); // P6
    expect(screen.getByText(t(common.sample))).toBeInTheDocument(); // every tender is a sample: one label at the top
  });

  it("opens a tender from its row", async () => {
    const router = open(dir);
    await ready();
    const rows = within(section(t(common.tenders))).getAllByRole("link");
    await userEvent.click(rows[1]!);
    await waitFor(() => expect(router.state.location.pathname).toBe(paths.tender(P1)));
  });

  it("shows nothing in place of a summary that is being written, and moves with the home event", async () => {
    scenario("home:cut_off");
    open(dir);
    await ready();
    expect(screen.queryByText(/3 حاجات مستنية ردّك/)).toBeNull();
    expect(within(section(t(home.waiting))).getByRole("button")).toHaveTextContent(t(home.homeConversation));
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("مهندس"));
    scenario("home:empty"); // says `home` on the general stream
    await waitFor(() => expect(screen.getByText(t(home.empty))).toBeInTheDocument());
    expect(screen.queryByRole("region", { name: t(home.waiting) })).toBeNull();
    expect(screen.queryByRole("region", { name: t(common.tenders) })).toBeNull();
    expect(box()).toHaveAttribute("placeholder", t(home.placeholder));
  });

  it("says why the Lead cannot work, with the way to fix it", async () => {
    scenario("home:no_ai");
    open(dir);
    await ready();
    expect(screen.getByText(/No AI is connected yet|لسه مفيش ذكاء اصطناعي/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t(home.openAi) })).toHaveAttribute("href", paths.settings("ai"));
    expect(box()).toBeDisabled();
  });

  it("a dropped folder makes a tender, opens it, and sends its files with their folders", async () => {
    const router = open(dir);
    await ready();
    fireEvent.drop(box().closest("form")!, { dataTransfer: folderDrop("Tender A") });
    await waitFor(() => expect(router.state.location.pathname).toBe(paths.tender(NEW)));
    await waitFor(() => expect(calls.at(-1)?.path).toBe(`/projects/${NEW}/understand`));
    expect(calls[0]).toMatchObject({ path: "/projects", body: { folder: "Tender A" } });
    const files = calls.filter((c) => c.path === `/projects/${NEW}/files`);
    expect(files.map((c) => [c.query.get("name"), c.query.get("folder")])).toEqual([
      ["01 BOQ.xlsx", "Tender A"],
      ["A-101.pdf", "Tender A/Drawings"],
    ]);
    expect(calls.find((c) => c.path.endsWith("/files/report"))?.body).toEqual({ file_ids: expect.arrayContaining([expect.any(String)]) });
  });

  it("a folder of a tender already here goes into it, with no second reading", async () => {
    server.use(
      http.post("*/api/projects", () =>
        HttpResponse.json({ error: { en: "Taken", ar: "موجود" }, project: { id: P1 } }, { status: 409 }),
      ),
    );
    const router = open(dir);
    await ready();
    fireEvent.drop(box().closest("form")!, { dataTransfer: folderDrop("مجمع مدارس") });
    await waitFor(() => expect(router.state.location.pathname).toBe(paths.tender(P1)));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/files/report"))).toBe(true));
    expect(calls.map((c) => c.path)).not.toContain(`/projects/${P1}/understand`);
    expect(calls[0]?.path).toBe(`/projects/${P1}/open`);
  });

  it("loose files are not a tender: it asks for the folder", async () => {
    open(dir);
    await ready();
    const file = new File(["x"], "BOQ.xlsx");
    const items = [{ kind: "file", getAsFile: () => file, webkitGetAsEntry: () => ({ isFile: true, isDirectory: false, name: file.name }) }];
    fireEvent.drop(box().closest("form")!, { dataTransfer: { types: ["Files"], files: [file], items } });
    expect(await screen.findByText(t(home.folderOnly))).toBeInTheDocument();
    expect(screen.queryByText("BOQ.xlsx")).toBeNull();
    expect(calls).toEqual([]);
  });

  it("sends a message in the Home conversation", async () => {
    let sent: { id?: string; messages?: { parts: { text?: string }[] }[] } | undefined;
    server.use(
      http.post("*/api/chat", async ({ request }) => {
        sent = (await request.json()) as typeof sent;
        return new HttpResponse(null, { status: 503 });
      }),
    );
    open(dir);
    await ready();
    await userEvent.type(box(), "ما الأقرب؟{Enter}");
    await waitFor(() => expect(sent?.id).toBe("general"));
    expect(sent?.messages).toHaveLength(1);
    expect(sent?.messages?.[0]?.parts[0]?.text).toBe("ما الأقرب؟");
  });
});
