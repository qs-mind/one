// @vitest-environment node
import { mkdtempSync, readFileSync } from "node:fs";
import type { AddressInfo } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createServer, type ViteDevServer } from "vite";
import { afterEach, describe, expect, it } from "vitest";
import { coreDev } from "./core-dev.ts";

const fakeCore = fileURLToPath(new URL("./fixtures/fake-core.mjs", import.meta.url));
const servers: ViteDevServer[] = [];

async function start(extra: string[] = []) {
  const dir = mkdtempSync(path.join(tmpdir(), "qsone-core-dev-"));
  const logFile = path.join(dir, "core.log");
  const server = await createServer({
    configFile: false,
    root: dir,
    logLevel: "silent",
    server: { port: 0, host: "127.0.0.1" },
    plugins: [coreDev({ command: [process.execPath, fakeCore, ...extra], logFile, readyTimeoutMs: 10000 })],
  });
  servers.push(server);
  await server.listen();
  const { port } = server.httpServer!.address() as AddressInfo;
  return { server, logFile, base: `http://127.0.0.1:${port}` };
}

function alive(pid: number) {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function until(check: () => boolean, ms = 5000) {
  const end = Date.now() + ms;
  while (!check() && Date.now() < end) await new Promise((r) => setTimeout(r, 50));
  return check();
}

afterEach(async () => {
  await Promise.all(servers.splice(0).map((s) => s.close()));
});

describe("coreDev", () => {
  it("forwards /api to the core with the secret, so the page sends none", async () => {
    const { base } = await start();
    const r = await fetch(`${base}/api/health`); // no Authorization header, as from the page
    expect(r.status).toBe(200);
    expect(await r.json()).toEqual({ ok: true, path: "/health" });
    expect(process.env.QSONE_SECRET).toBeUndefined(); // the secret goes to the core only
  });

  it("writes the core's output to core.log, without the secret", async () => {
    const { logFile } = await start();
    const log = readFileSync(logFile, "utf8");
    expect(log).toMatch(/pids \d+ \d+/);
    expect(log).not.toMatch(/[0-9a-f]{64}/);
  });

  it("stopping the dev server stops the core and its children", async () => {
    const { server, logFile } = await start();
    const [, core, child] = readFileSync(logFile, "utf8").match(/pids (\d+) (\d+)/)!.map(Number);
    expect(alive(core!) && alive(child!)).toBe(true);
    await server.close();
    expect(await until(() => !alive(core!) && !alive(child!))).toBe(true);
  });

  it("a core that fails to start leaves the dev server up and /api/health failing", async () => {
    const { base, logFile } = await start(["--fail"]);
    const r = await fetch(`${base}/api/health`);
    expect(r.ok).toBe(false);
    expect(readFileSync(logFile, "utf8")).toContain("failing on purpose");
  });
});
