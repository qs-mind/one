import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Chat } from "../chat/Chat";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "./project";
import { RecordsPanel } from "./RecordsPanel";

const school = { id: "p1", name: "مدرسة - عينة", created_at: "2026-11-04T08:00:00.000000+00:00" };
const files = `/api/projects/${school.id}/files`;
const boqName = "جدول الكميات - عينة.xlsx";

// A file as the core describes it after an upload or in its list.
function fileInfo(name: string, more: object = {}) {
  return {
    id: `f-${name}`,
    name,
    kind: "xlsx",
    size: 1,
    sha256: "0".repeat(64),
    status: "read",
    note: null,
    pages: 1,
    chunks: 1,
    added_at: "2026-11-04T08:00:00.000000+00:00",
    replaces: null,
    valid_until: null,
    duplicate: false,
    ...more,
  };
}

type Route = (url: string, init: RequestInit) => Response | Promise<Response>;

// The core behind /api. Each route is matched by method and the path without its query.
function core(routes: Record<string, Route> = {}) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const route = routes[`${init.method ?? "GET"} ${url.split("?")[0]}`];
    if (route) return route(url, init);
    if (url === `${files}`) return Response.json({ files: [] });
    if (url === "/api/settings/ai-key") return Response.json({ set: true });
    if (url === "/api/settings/model") return Response.json({ id: "claude-opus-5-5" });
    if (url === "/api/settings/models") return Response.json([]);
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

// Uploads answer with the file's own name, read from the URL, as the core does.
const upload: Route = (url) => {
  const name = decodeURIComponent(url.split("?name=")[1]!);
  return Response.json(fileInfo(name), { status: 201 });
};

const posts = (fetch: ReturnType<typeof core>) =>
  fetch.mock.calls.filter(([url, init]) => String(url).startsWith(`${files}?`) && init?.method === "POST");

function panel() {
  return render(<RecordsPanel onClose={() => undefined} onPickProject={() => undefined} />);
}

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(school);
});

describe("RecordsPanel", () => {
  it("lists the project's files with their status", async () => {
    const scanned = { en: "Some pages are scanned.", ar: "بعض الصفحات ممسوحة ضوئيًا." };
    core({
      [`GET ${files}`]: () =>
        Response.json({
          files: [fileInfo(boqName), fileInfo("مواصفات - عينة.pdf", { status: "partly_read", note: scanned })],
        }),
    });
    panel();
    const name = await screen.findByText(boqName);
    expect(name).toHaveAttribute("dir", "auto");
    expect(screen.getByText(texts.fileRead.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.filePartlyRead.ar)).toBeInTheDocument();
    expect(screen.getByText(scanned.ar)).toBeInTheDocument();
  });

  it("adds a file with its Arabic name in the URL and shows its status", async () => {
    const fetch = core({ [`POST ${files}`]: upload });
    const user = userEvent.setup();
    const { container } = panel();
    const file = new File(["x"], boqName);
    await user.upload(container.querySelector<HTMLInputElement>('input[type="file"]')!, file);

    expect(await screen.findByText(boqName)).toBeInTheDocument();
    expect(screen.getByText(texts.fileRead.ar)).toBeInTheDocument();
    const [url, init] = posts(fetch)[0]!;
    expect(url).toBe(`${files}?name=${encodeURIComponent(boqName)}`);
    expect(init?.body).toBe(file);
  });

  it("the Add files button opens the file chooser", async () => {
    core();
    const user = userEvent.setup();
    const { container } = panel();
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    expect(input).toHaveAttribute("multiple");
    const chooser = vi.spyOn(input, "click");
    await user.click(screen.getByRole("button", { name: texts.addFiles.ar }));
    expect(chooser).toHaveBeenCalled();
  });

  it("shows the core's plain note for a scanned PDF, in the page language", async () => {
    const scanned = { en: "Some pages have no text layer.", ar: "بعض الصفحات بلا طبقة نص." };
    core({
      [`POST ${files}`]: () =>
        Response.json(fileInfo("مواصفات - عينة.pdf", { kind: "pdf", status: "partly_read", note: scanned }), {
          status: 201,
        }),
    });
    const user = userEvent.setup();
    const { container } = panel();
    await user.upload(
      container.querySelector<HTMLInputElement>('input[type="file"]')!,
      new File(["x"], "مواصفات - عينة.pdf"),
    );

    expect(await screen.findByText(scanned.ar)).toBeInTheDocument();
    setLanguage("en");
    expect(await screen.findByText(scanned.en)).toBeInTheDocument();
    expect(screen.getByText(texts.filePartlyRead.en)).toBeInTheDocument();
  });

  it("dropping files on the panel adds them, one at a time", async () => {
    let inFlight = 0;
    let most = 0;
    const fetch = core({
      [`POST ${files}`]: async (url, init) => {
        most = Math.max(most, ++inFlight);
        await new Promise((resolve) => setTimeout(resolve, 5));
        inFlight--;
        return upload(url, init);
      },
    });
    panel();
    await screen.findByText(texts.noFiles.ar);
    const area = screen.getByText(texts.dropHere.ar);
    expect(fireEvent.dragOver(area)).toBe(false); // the default is prevented, so the window does not open the file
    fireEvent.drop(area, {
      dataTransfer: { files: [new File(["a"], "أ - عينة.csv"), new File(["b"], "ب - عينة.csv")] },
    });

    expect(await screen.findByText("ب - عينة.csv")).toBeInTheDocument();
    expect(screen.getByText("أ - عينة.csv")).toBeInTheDocument();
    expect(posts(fetch).map(([url]) => decodeURIComponent(String(url).split("?name=")[1]!))).toEqual([
      "أ - عينة.csv",
      "ب - عينة.csv",
    ]);
    expect(most).toBe(1);
  });

  it("a file the core refuses says which and why", async () => {
    const tooBig = { en: "Larger than 256 MB, not added.", ar: "أكبر من 256 ميجابايت، لم يُضف." };
    core({ [`POST ${files}`]: () => Response.json({ error: tooBig }, { status: 413 }) });
    const user = userEvent.setup();
    const { container } = panel();
    await user.upload(
      container.querySelector<HTMLInputElement>('input[type="file"]')!,
      new File(["x"], "كبير - عينة.pdf"),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("كبير - عينة.pdf");
    expect(alert).toHaveTextContent(tooBig.ar);
  });

  it("the same file again says it is already there", async () => {
    core({ [`POST ${files}`]: () => Response.json(fileInfo(boqName, { duplicate: true }), { status: 200 }) });
    const user = userEvent.setup();
    const { container } = panel();
    await user.upload(container.querySelector<HTMLInputElement>('input[type="file"]')!, new File(["x"], boqName));
    expect(await screen.findByText(texts.fileDuplicate.ar)).toBeInTheDocument();
  });

  it("search shows file name and page or sheet row", async () => {
    const fetch = core({
      [`GET /api/projects/${school.id}/search`]: () =>
        Response.json({
          mode: "exact",
          note: null,
          results: [
            { file_id: "f1", file_name: "مواصفات - عينة.pdf", locator: { page: 3 }, text: "Sub-Clause 14.2", score: 1 },
            {
              file_id: "f2",
              file_name: boqName,
              locator: { sheet: "BOQ", row: 23 },
              text: "03/02 | خرسانة",
              score: 0.5,
            },
          ],
        }),
    });
    const user = userEvent.setup();
    panel();
    await user.type(screen.getByRole("searchbox", { name: texts.search.ar }), "03/02{enter}");

    expect(await screen.findByText("صفحة 3")).toBeInTheDocument();
    expect(screen.getByText("ورقة BOQ، صف 23")).toBeInTheDocument();
    expect(screen.getByText("03/02 | خرسانة")).toHaveAttribute("dir", "auto");
    expect(screen.getByText("مواصفات - عينة.pdf")).toHaveAttribute("dir", "auto");
    const search = fetch.mock.calls.find(([url]) => String(url).includes("/search"))!;
    expect(search[0]).toBe(`/api/projects/${school.id}/search?q=${encodeURIComponent("03/02")}`);

    setLanguage("en");
    expect(await screen.findByText("Page 3")).toBeInTheDocument();
    expect(screen.getByText("Sheet BOQ, row 23")).toBeInTheDocument();
  });

  it("says search is by words only when the core says so", async () => {
    const wordsOnly = { en: "Searching by words only for now.", ar: "البحث بالكلمات فقط حاليًا." };
    core({
      [`GET /api/projects/${school.id}/search`]: () => Response.json({ mode: "words", note: wordsOnly, results: [] }),
    });
    const user = userEvent.setup();
    panel();
    await user.type(screen.getByRole("searchbox", { name: texts.search.ar }), "الخرسانة المسلحة");
    await user.click(screen.getByRole("button", { name: texts.search.ar }));

    expect(await screen.findByText(wordsOnly.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.noResults.ar)).toBeInTheDocument();
  });

  it("asks to pick or create a project first when none is open", async () => {
    setCurrentProject(undefined);
    core({ "GET /api/projects": () => Response.json({ projects: [] }) });
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.records.ar }));

    const records = screen.getByRole("region", { name: texts.records.ar });
    expect(within(records).getByText(texts.pickProjectFirst.ar)).toBeInTheDocument();
    expect(within(records).queryByRole("searchbox")).not.toBeInTheDocument();
    await user.click(within(records).getByRole("button", { name: texts.projects.ar }));
    expect(screen.getByRole("region", { name: texts.projects.ar })).toBeInTheDocument();
  });

  it("opens from the header and closes again", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.records.ar }));
    const records = screen.getByRole("region", { name: texts.records.ar });
    await user.click(within(records).getByRole("button", { name: texts.close.ar }));
    await waitFor(() => expect(screen.queryByRole("region", { name: texts.records.ar })).not.toBeInTheDocument());
  });

  it("opens in its own column beside the chat; the message box stays, and Tab reaches the panel first", async () => {
    core();
    const user = userEvent.setup();
    render(<Chat />);
    await user.click(screen.getByRole("button", { name: texts.records.ar }));
    const records = screen.getByRole("region", { name: texts.records.ar });
    const box = screen.getByRole("textbox", { name: texts.message.ar });
    expect(within(records.parentElement!).queryByRole("textbox", { name: texts.message.ar })).toBeNull();
    expect(records.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("every new label exists in both languages", async () => {
    core();
    panel();
    await screen.findByText(texts.noFiles.ar);
    expect(screen.getByRole("heading", { name: texts.records.ar })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.addFiles.ar })).toBeInTheDocument();
    expect(screen.getByText(texts.dropHere.ar)).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: texts.search.ar })).toBeInTheDocument();

    setLanguage("en");
    expect(await screen.findByRole("heading", { name: texts.records.en })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.addFiles.en })).toBeInTheDocument();
    expect(screen.getByText(texts.dropHere.en)).toBeInTheDocument();
    expect(screen.getByText(texts.noFiles.en)).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: texts.search.en })).toBeInTheDocument();
    for (const key of [
      "projects",
      "newProject",
      "projectName",
      "create",
      "open",
      "records",
      "addFiles",
      "dropHere",
      "fileRead",
      "filePartlyRead",
      "fileStored",
      "fileUnreadable",
      "search",
      "noResults",
      "page",
      "sheetRow",
      "pickProjectFirst",
    ] as const) {
      expect(texts[key].en).not.toBe(texts[key].ar);
    }
  });
});
