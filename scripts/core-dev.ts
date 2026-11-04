// Vite plugin for development: start the Python core on a free local port with a fresh secret, and forward /api to it
// with that secret, so the page never holds it. The core's output goes to core.log in the OS temp folder.
import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { randomBytes } from "node:crypto";
import { appendFileSync, closeSync, mkdirSync, openSync, writeSync } from "node:fs";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import path from "node:path";
import type { Plugin } from "vite";
import { corePython, root } from "./python.mjs";

export const defaultCoreLog = path.join(tmpdir(), "qs-mind-one", "core.log");

export interface CoreDevOptions {
  /** The program and arguments that start the core; `--port <p> --exit-with-stdin` is added. */
  command?: string[];
  logFile?: string;
  /** How long the dev server waits for the core's /health before it starts anyway. */
  readyTimeoutMs?: number;
}

export function coreDev(options: CoreDevOptions = {}): Plugin {
  const secret = randomBytes(32).toString("hex");
  const logFile = options.logFile ?? defaultCoreLog;
  let port = 0;

  return {
    name: "qsone-core-dev",
    apply: "serve",
    async config() {
      port = await freePort();
      return {
        define: { "import.meta.env.VITE_CORE_LOG": JSON.stringify(logFile) },
        server: {
          proxy: {
            "/api": {
              target: `http://127.0.0.1:${port}`,
              rewrite: (url: string) => url.replace(/^\/api/, ""),
              headers: { Authorization: `Bearer ${secret}` },
            },
          },
        },
      };
    },
    async configureServer(server) {
      const logger = server.config.logger;
      const note = (line: string) => appendFileSync(logFile, `${line}\n`);
      mkdirSync(path.dirname(logFile), { recursive: true });
      const log = openSync(logFile, "w");
      writeSync(log, `QS Mind One core, started ${new Date().toISOString()} on port ${port}\n`);

      let child: ChildProcess | undefined;
      let stopping = false;
      try {
        const [program, ...args] = options.command ?? [corePython(), "-m", "qsone"];
        child = spawn(program!, [...args, "--port", String(port), "--exit-with-stdin"], {
          cwd: root,
          env: { ...process.env, QSONE_SECRET: secret },
          stdio: ["pipe", log, log], // the core exits when this stdin closes, even if this process is killed
          detached: process.platform !== "win32", // its own process group, so stop() can end its children too
          windowsHide: true,
        });
      } catch (error) {
        writeSync(log, `${error instanceof Error ? error.message : String(error)}\n`);
      } finally {
        closeSync(log);
      }

      const failed = (why: string) => {
        if (stopping) return;
        note(why);
        logger.error(`QS Mind One core: ${why} Log: ${logFile}`);
      };
      if (!child) failed("could not start.");
      child?.on("error", (error) => failed(`could not start: ${error.message}`));
      child?.on("exit", (code, signal) => failed(`stopped (${signal ?? `code ${code}`}).`));

      // On Windows the venv's python.exe is a launcher that starts the real interpreter as its own child,
      // so killing only the launcher would leave the core running. Stop the whole tree on every system.
      const stop = () => {
        if (!child?.pid || stopping) return;
        stopping = true;
        if (process.platform === "win32") {
          spawnSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true });
        } else {
          try {
            process.kill(-child.pid, "SIGTERM");
          } catch {
            // the group has already gone
          }
        }
      };
      const onSignal = () => {
        stop();
        process.exit(0);
      };
      const signals = ["SIGINT", "SIGTERM", "SIGHUP"] as const;
      process.on("exit", stop);
      for (const signal of signals) process.once(signal, onSignal);
      server.httpServer?.once("close", () => {
        stop();
        process.off("exit", stop);
        for (const signal of signals) process.off(signal, onSignal);
      });

      if (child && (await ready(child, port, secret, options.readyTimeoutMs ?? 30000))) {
        logger.info("QS Mind One core is ready.");
      } else if (child?.exitCode === null) {
        failed("did not answer /health in time.");
      }
    },
  };
}

async function ready(child: ChildProcess, port: number, secret: string, timeoutMs: number) {
  const end = Date.now() + timeoutMs;
  while (Date.now() < end && child.exitCode === null && child.signalCode === null) {
    try {
      const r = await fetch(`http://127.0.0.1:${port}/health`, { headers: { Authorization: `Bearer ${secret}` } });
      if (r.ok) return true;
    } catch {
      // not listening yet
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return false;
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address();
      probe.close(() => (typeof address === "object" && address ? resolve(address.port) : reject(new Error("no port"))));
    });
  });
}
