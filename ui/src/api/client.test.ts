import type { Channel } from "@tauri-apps/api/core";
import { clearMocks, mockIPC } from "@tauri-apps/api/mocks";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "../api";
import { client, type Schemas, type Source } from "./client";
import { P2, startFakeCore } from "./fakeCore";

// The real api(), watched: the client must reach the core through it and through nothing else.
vi.mock("../api", async (original) => {
  const real = await original<typeof import("../api")>();
  return { ...real, api: vi.fn(real.api) };
});

startFakeCore();
beforeEach(() => {
  vi.mocked(api).mockClear();
});
afterEach(() => {
  vi.unstubAllEnvs();
  clearMocks();
});

/** The one call api() got: its path and what went with it. */
function sent() {
  expect(api).toHaveBeenCalledTimes(1);
  const [path, init] = vi.mocked(api).mock.calls[0]!;
  return { path, init: init!, headers: new Headers(init!.headers) };
}

describe("the typed client", () => {
  it("a GET leaves through api() with the core's own path and query", async () => {
    const { data, error, response } = await client.GET("/projects/{project_id}/room", { params: { path: { project_id: P2 }, query: { limit: 2 } } });

    const { path, init } = sent();
    expect(path).toBe(`/projects/${P2}/room?limit=2`);
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
    expect(response.status).toBe(200);
    expect(error).toBeUndefined();
    expect(data?.messages).toHaveLength(2);
  });

  it("a POST sends its JSON body as text", async () => {
    const text = "راجعوا بند 3/05 - عينة (sample)";
    const { data, response } = await client.POST("/projects/{project_id}/room", { params: { path: { project_id: P2 } }, body: { text } });

    const { path, init, headers } = sent();
    expect(path).toBe(`/projects/${P2}/room`);
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ text })); // text, never a stream: the installed app's shell carries no stream
    expect(headers.get("content-type")).toBe("application/json");
    expect(response.status).toBe(201);
    expect(data).toMatchObject({ from_id: "engineer", to_id: "team", text });
  });

  it("a refusal comes back as `error` with the core's words, and is not thrown", async () => {
    const { data, error, response } = await client.POST("/projects/{project_id}/room", { params: { path: { project_id: P2 } }, body: { text: " " } });

    expect(sent().path).toBe(`/projects/${P2}/room`);
    expect(response.status).toBe(422);
    expect(data).toBeUndefined();
    expect(error).toEqual({ error: { en: "Write a message first.", ar: "اكتب رسالة الأول." }, field: "text" });
  });

  it("a call the core cannot be reached for throws, as api() does", async () => {
    vi.mocked(api).mockRejectedValueOnce(new TypeError("ONE could not reach its core (core_down)."));
    await expect(client.GET("/home")).rejects.toThrow("ONE could not reach its core (core_down).");
  });

  it("nothing but api() reaches out", async () => {
    const fetched = vi.spyOn(globalThis, "fetch");
    await client.GET("/home");
    await client.PATCH("/settings/{key}", { params: { path: { key: "look.theme" } }, body: { value: "dark" } });
    expect(fetched.mock.calls.map(([address]) => address)).toEqual(["/api/home", "/api/settings/look.theme"]);
  });

  it("a source from any answer is a source the kept viewers take", async () => {
    const { data } = await client.GET("/projects/{project_id}/tender", { params: { path: { project_id: P2 } } });
    const sent: Schemas["Source"] = data!.tender.submission_source!;
    const kept: Source = sent; // the typecheck is the test: a place in a file may say true or false
    expect(kept.locator).toEqual({ page: 1, ocr_low_confidence: true });
  });

  // The installed app: a release build in the Tauri window, where api() hands every call to the shell.
  it("in the installed app the shell carries the call", async () => {
    const text = "راجعوا بند 3/05 - عينة (sample)";
    const stored: Schemas["RoomMessage"] = { id: "5a".padEnd(32, "0"), from_id: "engineer", to_id: "team", text, sources: [], at: "2026-11-09T09:00:00.000000+00:00", raised: null };
    const seen: Record<string, unknown>[] = [];
    vi.stubEnv("PROD", true);
    mockIPC((cmd, args) => {
      if (cmd !== "core_fetch") return;
      const call = args as Record<string, unknown> & { onEvent: Channel<unknown> };
      seen.push(call);
      call.onEvent.onmessage({ event: "head", status: 201, headers: [["content-type", "application/json"]] });
      call.onEvent.onmessage(new TextEncoder().encode(JSON.stringify(stored)).buffer);
      call.onEvent.onmessage({ event: "end" });
    });
    const fetched = vi.spyOn(globalThis, "fetch");

    const { data, response } = await client.POST("/projects/{project_id}/room", { params: { path: { project_id: P2 } }, body: { text } });

    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ method: "POST", path: `/projects/${P2}/room`, body: JSON.stringify({ text }) });
    expect(new Headers(seen[0]!.headers as [string, string][]).get("content-type")).toBe("application/json");
    expect(response.status).toBe(201);
    expect(data).toEqual(stored);
    expect(fetched).not.toHaveBeenCalled();
  });
});
