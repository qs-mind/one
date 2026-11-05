// A screen crash, sent to Usage Stats as the core takes it (POST /usage/crash): the error's class and the deepest
// place in One's own code, as "Chat.tsx:120". Never the message, a path, a URL or a library's file. The core sends
// nothing unless the engineer said yes to Usage Stats; the screen reports each crash once per session.
import { api } from "../api";

const KIND = /^[A-Za-z0-9_.:-]{1,80}$/;
const WHERE = /^[A-Za-z0-9_-]+(\.[A-Za-z0-9_-]+)*\.(tsx|ts|js):\d+$/;
// a frame's file and line, in Chromium ("at f (http://h/src/chat/Chat.tsx?t=1:120:15)") and WebKit ("f@tauri://…:120:15")
const FRAME = /([a-z][a-z0-9+.-]*:\/\/[^\s()@]+?)(?:\?[^\s():]*)?:(\d+)(?::\d+)?\)?\s*$/i;
// files that are not ours: libraries, Vite's own client and pre-bundled dependencies
const NOT_OURS = /\/node_modules\/|\/\.vite\/|\/@vite\/|\/@react-refresh|\/@id\//;

export type Crash = { kind: string; where: string };

/** The class and our file:line of `error`; undefined when no frame of the stack is in our code. */
export function crashReport(error: unknown): Crash | undefined {
  const name = error instanceof Error ? error.name || error.constructor?.name : typeof error;
  const kind = KIND.test(name) ? name : "Error";
  const stack = error instanceof Error && typeof error.stack === "string" ? error.stack : "";
  for (const line of stack.split("\n")) {
    const found = FRAME.exec(line.trim());
    if (!found || NOT_OURS.test(found[1]!)) continue;
    const file = found[1]!.split("/").pop() ?? "";
    const where = `${file}:${found[2]}`;
    if (WHERE.test(where)) return { kind, where };
  }
  return undefined;
}

const sent = new Set<string>();
let version: Promise<string | undefined> | undefined;

/** Sends the crash once; never throws, whatever the core answers. */
export async function reportCrash(error: unknown): Promise<void> {
  const crash = crashReport(error);
  if (!crash || sent.has(`${crash.kind} ${crash.where}`)) return;
  sent.add(`${crash.kind} ${crash.where}`);
  version ??= api("/about")
    .then((r) => (r.ok ? (r.json() as Promise<{ version?: string }>) : undefined))
    .then((about) => (about?.version && KIND.test(about.version) ? about.version : undefined))
    .catch(() => undefined);
  const known = await version;
  if (!known) return;
  await api("/usage/crash", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ from: "screen", ...crash, version: known }),
  }).catch(() => undefined);
}

/** Every error the screen does not catch itself: thrown in a handler, or a promise nobody waited on. */
export function installCrashReports(target: Window = window): void {
  target.addEventListener("error", (event) => void reportCrash(event.error));
  target.addEventListener("unhandledrejection", (event) => void reportCrash(event.reason));
}

/** For tests: forget what was sent. */
export function resetCrashReports(): void {
  sent.clear();
  version = undefined;
}
