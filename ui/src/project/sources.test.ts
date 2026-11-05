import { describe, expect, it, vi } from "vitest";
import { texts } from "../i18n";
import { httpSources, PAGE_IMAGES_KEPT, SourceError } from "./sources";

type Route = (url: string, init?: RequestInit) => Response;

function core(route: Route) {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init });
      return route(url, init);
    }),
  );
  return calls;
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const missing = () => json({ detail: "Not Found" }, 404);

describe("the project's sources over /api", () => {
  it("routes of later plans answer empty while they are missing", async () => {
    core((url) => (url.endsWith("/files") ? json({ files: [] }) : missing()));
    const s = httpSources("p1");
    expect(await s.deliverables()).toEqual([]);
    expect(await s.team()).toEqual({ desks: [], agents: [] });
    expect(await s.status()).toEqual({});
    expect(await s.pages("f1")).toBe(0);
    expect(await s.fileText("f1", 2)).toEqual([]);
  });

  it("the workspace route is there: a 404 is an error like any other", async () => {
    core(missing);
    const s = httpSources("p1");
    await expect(s.workspace()).rejects.toBeInstanceOf(SourceError);
    await expect(s.saveWorkspace({ key: "files:all", anchor: null })).rejects.toBeInstanceOf(SourceError);
  });

  it("a refused call is an error with the core's line, so the screen never saves over a document it did not read", async () => {
    const line = { en: "Open the project first.", ar: "افتح المشروع الأول." };
    core(() => json({ error: line }, 409));
    const s = httpSources("p1");
    await expect(s.workspace()).rejects.toEqual(new SourceError(line));
    await expect(s.saveWorkspace({ key: "files:all", anchor: null })).rejects.toBeInstanceOf(SourceError);
    core(() => new Response("", { status: 500 }));
    await expect(httpSources("p1").files()).rejects.toMatchObject({ line: texts.documentFailed });
  });

  it("saves the open document to the project with keepalive when asked", async () => {
    const calls = core(() => json({ ok: true }));
    const s = httpSources("p 1");
    await s.saveWorkspace({ key: "files:all", anchor: null }, true);
    expect(calls[0]).toMatchObject({ url: "/api/projects/p%201/workspace", init: { method: "PUT", keepalive: true } });
    expect(JSON.parse(calls[0]!.init!.body as string)).toEqual({ open: "files:all", anchor: null });
  });

  it("asks for page images by width and keeps at most 64 object URLs", async () => {
    const calls = core(() => new Response(new Blob(["png"]), { status: 200 }));
    let made = 0;
    vi.spyOn(URL, "createObjectURL").mockImplementation(() => `blob:${++made}`);
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
    const s = httpSources("p1");
    expect(await s.pageImage("f1", 3, 600)).toBe("blob:1");
    expect(calls[0]!.url).toBe("/api/projects/p1/files/f1/pages/3?width=600");
    expect(await s.pageImage("f1", 3, 600)).toBe("blob:1"); // kept, not asked again
    expect(calls).toHaveLength(1);
    for (let page = 1; page <= PAGE_IMAGES_KEPT; page++) await s.pageImage("f2", page, 600);
    await vi.waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:1"));
    expect(revoke).toHaveBeenCalledTimes(1);
  });

  it("a page count of 0 for a file that is not a PDF", async () => {
    core((url) => (url.endsWith("/f1/pages") ? json({ pages: 18 }) : json({ error: { en: "x", ar: "x" } }, 409)));
    const s = httpSources("p1");
    expect(await s.pages("f1")).toBe(18);
    expect(await s.pages("f2")).toBe(0);
  });
});
