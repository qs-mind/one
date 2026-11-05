import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { currentProject, setCurrentProject } from "../records/project";
import { importFolders, onBriefStarted, resetImports } from "./importer";
import { ImportReports } from "./ImportReport";
import { UnderstoodCard } from "./UnderstoodCard";

type Handler = (body: Record<string, unknown> | undefined, url: string) => Response | Promise<Response>;

/** The core behind /api, as the HTTP contract of Plan 8 has it: the routes a test gives, by "METHOD path". */
function mockCore(routes: Record<string, Handler>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input).replace(/^\/api/, "");
    const path = url.split("?")[0]!;
    const key = `${init.method ?? "GET"} ${path}`;
    const body = typeof init.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined;
    const route = routes[key];
    if (route) return route(body, url);
    if (key === "GET /projects") return Response.json({ projects: [{ id: "p1", name: "x" }] });
    if (key === "GET /backup") return Response.json({ folder: "/home/x/Backups" });
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const keys = (fetch: ReturnType<typeof mockCore>) =>
  fetch.mock.calls.map(([url, init]) => `${init?.method ?? "GET"} ${String(url).replace(/^\/api/, "").split("?")[0]}`);

const file = (name: string, path: string) => {
  const f = new File(["x"], name);
  Object.defineProperty(f, "webkitRelativePath", { value: path });
  return f;
};

const LETTER = "f-letter";
const facts = (approved = false, client = "هيئة - عينة", by: "lead_qs" | "engineer" = "lead_qs") => ({
  facts: {
    client: {
      value: client,
      source: by === "engineer" ? { kind: "engineer", date: "2026-11-05" } : { kind: "file", file_id: LETTER, file_name: "خطاب الدعوة - عينة.pdf", locator: { page: 3 } },
      by,
    },
    submission_date: {
      value: "2026-12-01",
      source: { kind: "file", file_id: "f-boq", file_name: "BOQ - عينة.xlsx", locator: { sheet: "BOQ", row: 2 } },
      by: "lead_qs",
    },
    items_count: { value: "118", source: { kind: "count", trace_id: "imp1" }, by: "lead_qs" },
  },
  missing: ["تقرير التربة - عينة"],
  files: [{ file_id: LETTER, name: "خطاب الدعوة - عينة.pdf", folder: "مناقصة", label: "خطاب الدعوة", why: "فيه العميل" }],
  approved,
});

beforeEach(() => {
  setLanguage("en");
  resetImports();
  setCurrentProject(undefined);
});
afterEach(() => resetImports());

describe("the I understood this card", () => {
  it("the card shows each fact with its source and saves a correction on Enter", async () => {
    const puts: unknown[] = [];
    mockCore({
      "GET /projects/p1/facts": () => Response.json(facts()),
      "PUT /projects/p1/facts": (body) => {
        puts.push(body);
        return Response.json(facts(false, "هيئة المجتمعات - عينة", "engineer"));
      },
    });
    const user = userEvent.setup();
    render(<UnderstoodCard projectId="p1" />);
    expect(await screen.findByText("هيئة - عينة")).toBeInTheDocument();
    // each file's name isolated on one line, its extension whole, then the place in it
    const source = (name: string) => screen.getAllByTitle(name)[0]!.parentElement!;
    expect(source("خطاب الدعوة - عينة.pdf")).toHaveTextContent(/^خطاب الدعوة - عينة\.pdf, page 3$/);
    expect(source("BOQ - عينة.xlsx")).toHaveTextContent(/^BOQ - عينة\.xlsx, BOQ, row 2$/);
    expect(screen.getAllByTitle("BOQ - عينة.xlsx")[0]!.querySelector('bdi[dir="ltr"]')).toHaveTextContent(".xlsx");
    expect(screen.getByText(texts.factSourceCount.en)).toBeInTheDocument();
    expect(screen.getByText(texts.understoodNotFound.en)).toBeInTheDocument(); // the contract type: no file states it
    expect(screen.getByText("تقرير التربة - عينة")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: `${texts.understoodChange.en}: ${texts.understoodClient.en}` }));
    const box = screen.getByLabelText(texts.understoodClient.en);
    await user.clear(box);
    await user.type(box, "هيئة المجتمعات - عينة");
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull(); // no Save button
    await user.keyboard("{Enter}");
    expect(await screen.findByText("هيئة المجتمعات - عينة")).toBeInTheDocument();
    expect(puts).toEqual([{ facts: { client: { value: "هيئة المجتمعات - عينة" } }, approve: false }]);
    expect(screen.getByText("You, 5 Nov 2026")).toBeInTheDocument();
    expect(await screen.findByText(texts.saved.en)).toBeInTheDocument();
  });

  it("leaving a changed fact saves it; Escape keeps it as it was; a refused one stays to be fixed", async () => {
    const refused = { en: "Not saved (sample).", ar: "ماتحفظش (عينة)." };
    const puts: unknown[] = [];
    let ok = true;
    mockCore({
      "GET /projects/p1/facts": () => Response.json(facts()),
      "PUT /projects/p1/facts": (body) => {
        puts.push(body);
        return ok ? Response.json(facts(false, "عميل - عينة", "engineer")) : Response.json({ error: refused }, { status: 409 });
      },
    });
    const user = userEvent.setup();
    render(<UnderstoodCard projectId="p1" />);
    const change = () => screen.getByRole("button", { name: `${texts.understoodChange.en}: ${texts.understoodClient.en}` });

    await screen.findByText("هيئة - عينة");
    await user.click(change());
    await user.type(screen.getByLabelText(texts.understoodClient.en), " - تعديل");
    await user.keyboard("{Escape}");
    expect(screen.getByText("هيئة - عينة")).toBeInTheDocument();
    expect(puts).toHaveLength(0);

    ok = false;
    await user.click(change());
    const box = screen.getByLabelText(texts.understoodClient.en);
    await user.clear(box);
    await user.type(box, "عميل - عينة");
    await user.tab(); // leaving the field
    expect(await screen.findByRole("alert")).toHaveTextContent(refused.en);
    expect(screen.getByLabelText(texts.understoodClient.en)).toHaveValue("عميل - عينة");

    ok = true;
    await user.click(screen.getByLabelText(texts.understoodClient.en));
    await user.tab();
    expect(await screen.findByText("عميل - عينة")).toBeInTheDocument();
    expect(puts).toHaveLength(2);
  });

  it("Approve right after a change saves the change first", async () => {
    const puts: { approve: boolean }[] = [];
    mockCore({
      "GET /projects/p1/facts": () => Response.json(facts()),
      "PUT /projects/p1/facts": (body) => {
        puts.push(body as { approve: boolean });
        return Response.json(facts((body as { approve: boolean }).approve, "عميل - عينة", "engineer"));
      },
    });
    const user = userEvent.setup();
    render(<UnderstoodCard projectId="p1" />);
    await user.click(await screen.findByRole("button", { name: `${texts.understoodChange.en}: ${texts.understoodClient.en}` }));
    const box = screen.getByLabelText(texts.understoodClient.en);
    await user.clear(box);
    await user.type(box, "عميل - عينة");
    await user.click(screen.getByRole("button", { name: texts.understoodApprove.en }));
    expect(await screen.findByText(texts.understoodApproved.en)).toBeInTheDocument();
    expect(puts.map((put) => put.approve)).toEqual([false, true]);
  });

  it("approve is the only way forward", async () => {
    const puts: unknown[] = [];
    mockCore({
      "GET /projects/p1/facts": () => Response.json(facts()),
      "PUT /projects/p1/facts": (body) => {
        puts.push(body);
        return Response.json(facts(true));
      },
    });
    const user = userEvent.setup();
    const { container } = render(<UnderstoodCard projectId="p1" />);
    await screen.findByText("هيئة - عينة");
    // one main action: Approve; the rest only change a fact
    const actions = screen.getAllByRole("button").map((b) => b.textContent);
    expect(actions.filter((name) => !name?.startsWith(texts.understoodChange.en))).toEqual([texts.understoodApprove.en]);
    await user.click(screen.getByRole("button", { name: texts.understoodApprove.en }));
    expect(puts).toEqual([{ facts: {}, approve: true }]);
    expect(await screen.findByText(texts.understoodApproved.en)).toBeInTheDocument();
    expect(container.querySelector("[data-approved]")).not.toBeNull();
    expect(screen.queryByRole("button", { name: texts.understoodApprove.en })).toBeNull();
    expect(screen.queryByRole("button", { name: new RegExp(`^${texts.understoodChange.en}`) })).toBeNull();
  });
});

describe("importing a folder", () => {
  it("a tender folder becomes a project named after it, then the Lead QS reads it", async () => {
    const uploads: string[] = [];
    const fetch = mockCore({
      "POST /projects": (body) => Response.json({ id: "p1", name: body!.name, created_at: "2026-11-05T08:00:00Z", open: true }, { status: 201 }),
      "POST /projects/p1/files": (_, url) => {
        uploads.push(decodeURIComponent(url.split("?")[1]!));
        return Response.json({ status: "read" }, { status: 201 });
      },
      "POST /projects/p1/understand": () => Response.json({ brief_id: "b1" }, { status: 202 }),
    });
    const started: string[] = [];
    onBriefStarted((id) => started.push(id));
    render(<ImportReports />);
    await act(() => importFolders([file("عقد.pdf", "مناقصة/عقد.pdf"), file("BOQ.xlsx", "مناقصة/02 جداول/BOQ.xlsx")], { old: false }));
    expect(currentProject()?.name).toBe("مناقصة");
    expect(uploads).toEqual(["name=عقد.pdf&folder=مناقصة", "name=BOQ.xlsx&folder=مناقصة/02 جداول"]);
    expect(keys(fetch)).toContain("POST /projects/p1/understand");
    expect(started).toEqual(["p1"]);
    expect(await screen.findByText("Added: 2")).toBeInTheDocument();
    expect(screen.getByText(texts.importUnderstanding.en)).toBeInTheDocument();
  });

  it("old work is archived without the AI step and offers to understand it", async () => {
    let n = 0;
    const fetch = mockCore({
      "POST /projects": (body) => Response.json({ id: `p${++n}`, name: body!.name, created_at: "2026-11-05T08:00:00Z" }, { status: 201 }),
      "POST /projects/p1/files": () => Response.json({ status: "read" }, { status: 201 }),
      "POST /projects/p2/files": () => Response.json({ status: "read" }, { status: 201 }),
      "POST /projects/p1/archive": () => Response.json({ archived_at: "2026-11-05T09:00:00Z", backed_up: false, note: null }),
      "POST /projects/p2/archive": () => Response.json({ archived_at: "2026-11-05T09:00:00Z", backed_up: false, note: null }),
      "POST /projects/p1/close": () => Response.json({ open: false }),
      "POST /projects/p2/close": () => Response.json({ open: false }),
      "POST /projects/p1/open": () => Response.json({ id: "p1", name: "برج", created_at: "x", archived_at: "2026-11-05T09:00:00Z" }),
      "POST /projects/p1/unarchive": () => Response.json({ archived_at: null }),
      "POST /projects/p1/understand": () => Response.json({ brief_id: "b1" }, { status: 202 }),
    });
    const user = userEvent.setup();
    render(<ImportReports />);
    await act(() => importFolders([file("a.pdf", "برج/a.pdf"), file("b.pdf", "مدرسة/b.pdf")], { old: true }));
    expect(keys(fetch)).not.toContain("POST /projects/p1/understand");
    expect(keys(fetch)).toEqual(expect.arrayContaining(["POST /projects/p1/archive", "POST /projects/p2/archive"]));
    expect(currentProject()).toBeUndefined(); // old work does not take the engineer away
    expect(screen.getAllByText(texts.importOldArchived.en)).toHaveLength(2);

    const report = screen.getByRole("region", { name: "برج" });
    await user.click(within(report).getByRole("button", { name: texts.importUnderstandIt.en }));
    await waitFor(() => expect(keys(fetch)).toContain("POST /projects/p1/understand"));
    const order = keys(fetch);
    expect(order.indexOf("POST /projects/p1/unarchive")).toBeLessThan(order.indexOf("POST /projects/p1/understand"));
    expect(currentProject()).toMatchObject({ id: "p1", archived_at: null });
  });

  it("a tender folder chosen with a project open goes into that project, never a new one", async () => {
    const uploads: string[] = [];
    const fetch = mockCore({
      "POST /projects/p7/files": (_, url) => {
        uploads.push(decodeURIComponent(url.split("?")[1]!));
        return Response.json({ status: "read" }, { status: 201 });
      },
    });
    setCurrentProject({ id: "p7", name: "مناقصة - عينة", created_at: "x" });
    render(<ImportReports />);
    await act(() => importFolders([file("عقد.pdf", "مناقصة - عينة/عقد.pdf")], { old: false }));
    expect(keys(fetch)).not.toContain("POST /projects");
    expect(uploads).toEqual(["name=عقد.pdf&folder=مناقصة - عينة"]);
    expect(currentProject()?.id).toBe("p7");
  });

  it("a tender whose name is taken goes into the project of that name", async () => {
    const there = { id: "p3", name: "مناقصة - عينة", created_at: "x" };
    const fetch = mockCore({
      "POST /projects": () => Response.json({ error: { en: "Taken.", ar: "متاخد." }, field: "name", project: there }, { status: 409 }),
      "POST /projects/p3/open": () => Response.json({ ...there, open: true }),
      "POST /projects/p3/files": () => Response.json({ status: "read" }, { status: 201 }),
    });
    render(<ImportReports />);
    await act(() => importFolders([file("عقد.pdf", "مناقصة - عينة/عقد.pdf")], { old: false }));
    expect(keys(fetch).filter((k) => k === "POST /projects")).toHaveLength(1);
    expect(keys(fetch)).toContain("POST /projects/p3/files");
    expect(currentProject()?.id).toBe("p3");
  });

  it("old work whose name is taken gets (2) after it", async () => {
    const names: unknown[] = [];
    mockCore({
      "POST /projects": (body) => {
        names.push(body!.name);
        if (names.length === 1) return Response.json({ error: { en: "Taken.", ar: "متاخد." }, project: { id: "p0", name: "برج", created_at: "x" } }, { status: 409 });
        return Response.json({ id: "p1", name: body!.name, created_at: "x" }, { status: 201 });
      },
      "POST /projects/p1/files": () => Response.json({ status: "read" }, { status: 201 }),
      "POST /projects/p1/archive": () => Response.json({ archived_at: "2026-11-05T09:00:00Z", backed_up: false, note: null }),
      "POST /projects/p1/close": () => Response.json({ open: false }),
    });
    render(<ImportReports />);
    await act(() => importFolders([file("a.pdf", "برج/a.pdf")], { old: true }));
    expect(names).toEqual(["برج", "برج (2)"]);
  });

  it("says why the Lead QS could not start", async () => {
    mockCore({
      "POST /projects": (body) => Response.json({ id: "p1", name: body!.name, created_at: "x" }, { status: 201 }),
      "POST /projects/p1/files": () => Response.json({ status: "read" }, { status: 201 }),
      "POST /projects/p1/understand": () => Response.json({ error: { en: "Connect AI first.", ar: "وصّل الذكاء الاصطناعي الأول." } }, { status: 409 }),
    });
    render(<ImportReports />);
    await act(() => importFolders([file("a.pdf", "مناقصة/a.pdf")], { old: false }));
    expect(await screen.findByText("Connect AI first.")).toBeInTheDocument();
  });
});
