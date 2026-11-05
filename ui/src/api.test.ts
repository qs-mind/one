import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import type { Channel } from "@tauri-apps/api/core";
import { clearMocks, mockIPC } from "@tauri-apps/api/mocks";
import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  clearMocks();
});

describe("api()", () => {
  it("reaches the core through /api in development", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    await api("/health");
    expect(fetch).toHaveBeenCalledWith("/api/health", undefined);
  });

  it("passes the request on as it is", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}"));
    const init = { method: "POST", body: "{}" };
    await api("/projects/p1/files?name=%D8%B9", init);
    expect(fetch).toHaveBeenCalledWith("/api/projects/p1/files?name=%D8%B9", init);
  });
});

// The installed app: a release build in the Tauri window, every call carried by the shell (desktop/src/shim.rs).
describe("api() in the installed app", () => {
  type Sent = { event: string; [key: string]: unknown } | ArrayBuffer;
  const encode = (text: string) => new TextEncoder().encode(text).buffer;
  const installed = (shell: (cmd: string, args: Record<string, unknown>) => unknown) => {
    vi.stubEnv("PROD", true);
    mockIPC((cmd, args) => shell(cmd, args as Record<string, unknown>));
    return vi.spyOn(globalThis, "fetch");
  };
  const channel = (args: Record<string, unknown>) => args.onEvent as Channel<Sent>;

  it("in the installed app, streams the answer through the shim", async () => {
    const fetch = installed((cmd, args) => {
      if (cmd !== "core_fetch") return;
      const ch = channel(args);
      ch.onmessage({ event: "head", status: 200, headers: [["content-type", "text/event-stream"]] });
      ch.onmessage(encode("data: مر"));
      ch.onmessage(encode("حبا\n\n"));
      ch.onmessage({ event: "end" });
    });
    const r = await api("/chat", { method: "POST", body: "{}" });
    expect(r.status).toBe(200);
    expect(r.headers.get("content-type")).toBe("text/event-stream");
    expect(await r.text()).toBe("data: مرحبا\n\n");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("sends the method, path, headers and body as they are", async () => {
    const seen: Record<string, unknown>[] = [];
    installed((cmd, args) => {
      if (cmd !== "core_fetch") return;
      seen.push(args);
      channel(args).onmessage({ event: "head", status: 204, headers: [] });
      channel(args).onmessage({ event: "end" });
    });
    const r = await api("/projects/p1?x=%D8%B9", {
      method: "put",
      headers: { "Content-Type": "application/json" },
      body: '{"a":1}',
    });
    expect(r.status).toBe(204);
    expect(seen[0]).toMatchObject({
      method: "PUT",
      path: "/projects/p1?x=%D8%B9",
      headers: [["content-type", "application/json"]],
      body: '{"a":1}',
    });
  });

  it("an answer that stops early fails the read, as a dropped connection does", async () => {
    installed((cmd, args) => {
      if (cmd !== "core_fetch") return;
      channel(args).onmessage({ event: "head", status: 200, headers: [] });
      channel(args).onmessage(encode("half"));
      channel(args).onmessage({ event: "error", code: "cut_short" });
    });
    const r = await api("/projects");
    await expect(r.text()).rejects.toThrow();
  });

  it("a core that is down or a path the shell refuses fails the call, as fetch does offline", async () => {
    installed((cmd, args) => {
      if (cmd === "core_fetch") channel(args).onmessage({ event: "error", code: "core_down" });
    });
    await expect(api("/health")).rejects.toThrow(TypeError);
  });

  it("stop aborts the call and tells Rust to drop it", async () => {
    const calls: [string, Record<string, unknown>][] = [];
    installed((cmd, args) => {
      calls.push([cmd, args]);
      if (cmd === "core_fetch") channel(args).onmessage({ event: "head", status: 200, headers: [] });
    });
    const stop = new AbortController();
    const r = await api("/projects/p1/activity", { signal: stop.signal });
    const read = r.text();
    stop.abort();
    await expect(read).rejects.toThrow();
    const id = calls.find(([cmd]) => cmd === "core_fetch")![1].id;
    expect(calls).toContainEqual(["core_cancel", { id }]);

    const before = new AbortController();
    before.abort();
    await expect(api("/chat", { signal: before.signal })).rejects.toThrow();
  });

  it("a file goes through core_upload with its path in a header", async () => {
    installed(() => undefined);
    const shell = vi.fn(async (_cmd: string, _payload: unknown, _options?: { headers?: Record<string, string> }) => ({
      status: 200,
      headers: [["content-type", "application/json"]],
      body: '{"id":"f1"}',
    }));
    (window as unknown as { __TAURI_INTERNALS__: { invoke: typeof shell } }).__TAURI_INTERNALS__.invoke = shell;
    const file = new File(["%PDF"], "عقد.pdf", { type: "application/pdf" });
    const r = await api(`/projects/p1/files?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file });
    expect(await r.json()).toEqual({ id: "f1" });
    const [cmd, payload, options] = shell.mock.calls[0]!;
    expect(cmd).toBe("core_upload");
    expect(new TextDecoder().decode(payload as Uint8Array)).toBe("%PDF");
    expect(options?.headers).toEqual({
      "content-type": "application/pdf",
      "x-qsone-path": "/projects/p1/files?name=%D8%B9%D9%82%D8%AF.pdf",
      "x-qsone-method": "POST",
      "content-length": "4",
    });
  });

  it("the secret is never in the page", () => {
    const source = readFileSync(join(__dirname, "api.ts"), "utf8");
    expect(source).not.toMatch(/authorization|bearer/i);
    // The shell answers the page with a phase and a log path only (core.rs: status_json), never the secret.
    const status = readFileSync(join(__dirname, "../../desktop/src/core.rs"), "utf8").match(/fn status_json[\s\S]*?\n}/)![0];
    expect(status).not.toMatch(/secret|bearer|target/);
  });
});

// Every screen calls api(), never fetch, so the installed app can carry every call (Plan 8 Task 2).
describe("no screen calls fetch itself", () => {
  const root = join(__dirname);
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? files(path) : [path];
    });

  it("only api.ts calls fetch", () => {
    const callers = files(root)
      .filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path))
      .map((path) => relative(root, path).replaceAll("\\", "/"))
      .filter((path) => !["api.ts", "test-setup.ts", "shell/testing.tsx"].includes(path) && !path.endsWith("fixtures.ts"))
      .filter((path) => /\bfetch\(|["'`]\/api[/"'`?]/.test(readFileSync(join(root, path), "utf8")));
    expect(callers).toEqual([]);
  });
});
