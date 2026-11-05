import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../i18n";
import { currentProject, type Project, setCurrentProject } from "../records/project";
import { CloseProject } from "./CloseProject";

type Handler = (body: Record<string, unknown> | undefined) => Response;

function mockCore(routes: Record<string, Handler>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const key = `${init.method ?? "GET"} ${String(input).replace(/^\/api/, "")}`;
    const body = typeof init.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined;
    return routes[key]?.(body) ?? new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const closing = (over: Record<string, unknown> = {}) => ({
  open_comments: 2,
  unsigned: [{ id: "d1", name: "جدول كميات مسعر - عينة" }],
  reports: [{ id: "d2", name: "خطاب العطاء - عينة", revision: 1 }],
  confidential: false,
  archived_at: null,
  lessons: [{ id: "l1", text: "راجع وحدات المقايسة قبل التسعير (عينة).", kind: "method", carried: false }],
  ...over,
});

let n = 0;
const project = (over: Partial<Project> = {}): Project => ({ id: `p${++n}`, name: "مدرسة - عينة", created_at: "x", ...over });

beforeEach(() => setLanguage("en"));

describe("Close project", () => {
  it("close project lists open comments but lets the engineer archive", async () => {
    const p = project();
    setCurrentProject(p);
    const opened: string[] = [];
    const fetch = mockCore({
      [`GET /projects/${p.id}/closing`]: () => Response.json(closing()),
      [`POST /projects/${p.id}/archive`]: () =>
        Response.json({ archived_at: "2026-11-05T10:00:00Z", backed_up: false, note: { en: "No backup was made.", ar: "مااتعملتش نسخة." } }),
    });
    const user = userEvent.setup();
    render(<CloseProject project={p} briefRunning={false} onOpenDeliverable={(id) => opened.push(id)} onClose={() => undefined} />);
    expect(await screen.findByText(fill(texts.closeProjectOpenComments.en, { n: 2 }))).toBeInTheDocument();
    expect(screen.getByText("جدول كميات مسعر - عينة")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /خطاب العطاء - عينة/ }));
    expect(opened).toEqual(["d2"]);
    // lessons are there already, so no Brief is started for them
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/lessons/propose"))).toBe(false);
    await user.click(screen.getByRole("button", { name: texts.archiveAnyway.en }));
    expect(await screen.findByText("No backup was made.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.openBackup.en })).toBeInTheDocument(); // where to back it up
    expect(currentProject()?.archived_at).toBe("2026-11-05T10:00:00Z");
  });

  it("carries a lesson, or keeps it in the project without writing anything", async () => {
    const p = project();
    let carried = false;
    const sent: unknown[] = [];
    mockCore({
      [`GET /projects/${p.id}/closing`]: () =>
        Response.json(
          closing({
            lessons: [
              { id: "l1", text: "درس أول (عينة)", kind: "method", carried },
              { id: "l2", text: "درس تاني (عينة)", kind: "correction", carried: false },
            ],
          }),
        ),
      [`POST /projects/${p.id}/lessons/l1`]: (body) => {
        sent.push(body);
        carried = true;
        return Response.json({ carried: true });
      },
      [`POST /projects/${p.id}/lessons/l2`]: (body) => {
        sent.push(body);
        return Response.json({ carried: false });
      },
    });
    const user = userEvent.setup();
    render(<CloseProject project={p} briefRunning={false} onOpenDeliverable={() => undefined} onClose={() => undefined} />);
    await screen.findByText("درس أول (عينة)");
    const [carry] = screen.getAllByRole("button", { name: texts.lessonCarry.en });
    await user.click(carry!);
    expect(await screen.findByText(texts.lessonCarried.en)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.lessonKeep.en }));
    await waitFor(() => expect(screen.queryByText("درس تاني (عينة)")).toBeNull());
    expect(sent).toEqual([{ carry: true }, { carry: false }]);
  });

  it("asks the Lead QS for lessons once, and reads them when its Brief ends", async () => {
    const p = project();
    let lessons: unknown[] = [];
    const fetch = mockCore({
      [`GET /projects/${p.id}/closing`]: () => Response.json(closing({ open_comments: 0, unsigned: [], lessons })),
      [`POST /projects/${p.id}/lessons/propose`]: () => Response.json({ brief_id: "b1" }, { status: 202 }),
    });
    const props = { project: p, onOpenDeliverable: () => undefined, onClose: () => undefined };
    const { rerender, unmount } = render(<CloseProject {...props} briefRunning={false} />);
    expect(await screen.findByText(texts.lessonsFinding.en)).toBeInTheDocument();
    rerender(<CloseProject {...props} briefRunning />);
    lessons = [{ id: "l1", text: "درس (عينة)", kind: "method", carried: false }];
    rerender(<CloseProject {...props} briefRunning={false} />);
    expect(await screen.findByText("درس (عينة)")).toBeInTheDocument();
    expect(screen.getByText(texts.closeProjectAllClear.en)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.archiveProject.en })).toBeInTheDocument();
    unmount();
    lessons = [];
    render(<CloseProject {...props} briefRunning={false} />);
    await screen.findByText(texts.lessonsNone.en);
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/lessons/propose"))).toHaveLength(1);
  });

  it("a Confidential project proposes no lessons", async () => {
    const p = project({ confidential: true });
    const fetch = mockCore({ [`GET /projects/${p.id}/closing`]: () => Response.json(closing({ confidential: true, lessons: [] })) });
    render(<CloseProject project={p} briefRunning={false} onOpenDeliverable={() => undefined} onClose={() => undefined} />);
    expect(await screen.findByText(texts.lessonsConfidential.en)).toBeInTheDocument();
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/lessons/propose"))).toBe(false);
  });

  it("an archived project says read-only and offers Unarchive", async () => {
    const p = project({ archived_at: "2026-11-05T10:00:00Z" });
    setCurrentProject(p);
    let archived: string | null = "2026-11-05T10:00:00Z";
    const fetch = mockCore({
      [`GET /projects/${p.id}/closing`]: () => Response.json(closing({ archived_at: archived, lessons: [] })),
      [`POST /projects/${p.id}/unarchive`]: () => {
        archived = null;
        return Response.json({ archived_at: null });
      },
    });
    const user = userEvent.setup();
    render(<CloseProject project={p} briefRunning={false} onOpenDeliverable={() => undefined} onClose={() => undefined} />);
    expect(await screen.findByText(texts.archivedReadOnly.en)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: texts.archiveAnyway.en })).toBeNull();
    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/lessons/propose"))).toBe(false); // refused while archived
    await user.click(screen.getByRole("button", { name: texts.unarchiveProject.en }));
    await waitFor(() => expect(currentProject()?.archived_at).toBeNull());
    expect(await screen.findByRole("button", { name: texts.archiveAnyway.en })).toBeInTheDocument();
  });
});
