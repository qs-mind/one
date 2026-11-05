// The project's live events (Plan 4's GET /projects/{id}/activity): one stream per project, however many parts of
// the screen listen (the canvas, the agent cards, Plan 6's viewers). Read with fetch, not EventSource, so the Tauri
// fetch shim carries it in release builds. Nothing is kept: after a reconnect each listener reloads its lists.
import type { ActivityEvent } from "./canvas/types";

type Subscriber = { listener: (event: ActivityEvent) => void; onReconnect?: () => void };
type Stream = { subscribers: Set<Subscriber>; controller: AbortController };

/** The waits before each new try after the stream ends or fails: 1, 2, 5, then every 10 s. */
export const RETRY_MS = [1000, 2000, 5000, 10000] as const;

const streams = new Map<string, Stream>();

/** Calls `listener` with each event of the project; `onReconnect` after the stream comes back. Returns the call that
 * stops listening; the last one stops the stream. */
export function subscribeActivity(
  projectId: string,
  listener: (event: ActivityEvent) => void,
  onReconnect?: () => void,
): () => void {
  let stream = streams.get(projectId);
  if (!stream) {
    stream = { subscribers: new Set(), controller: new AbortController() };
    streams.set(projectId, stream);
    void run(projectId, stream);
  }
  const subscriber: Subscriber = { listener, onReconnect };
  stream.subscribers.add(subscriber);
  const own = stream;
  return () => {
    own.subscribers.delete(subscriber);
    if (own.subscribers.size === 0) {
      own.controller.abort();
      if (streams.get(projectId) === own) streams.delete(projectId);
    }
  };
}

async function run(projectId: string, stream: Stream) {
  const { signal } = stream.controller;
  const url = `/api/projects/${encodeURIComponent(projectId)}/activity`;
  let failures = 0;
  let opened = false;
  while (!signal.aborted) {
    if (failures > 0) {
      await wait(RETRY_MS[Math.min(failures, RETRY_MS.length) - 1]!, signal);
      if (signal.aborted) return;
    }
    try {
      const response = await fetch(url, { signal, headers: { accept: "text/event-stream" } });
      if (response.ok && response.body) {
        if (opened) for (const s of [...stream.subscribers]) s.onReconnect?.();
        opened = true;
        failures = 0;
        await read(response.body, (event) => {
          for (const s of [...stream.subscribers]) s.listener(event);
        });
      }
    } catch {
      // the core went away or the stream was aborted: try again below
    }
    failures += 1;
  }
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(done, ms);
    signal.addEventListener("abort", done, { once: true });
    function done() {
      clearTimeout(timer);
      signal.removeEventListener("abort", done);
      resolve();
    }
  });
}

/** Server-sent events: `data:` lines up to a blank line make one event; `:` lines are comments (pings). */
async function read(body: ReadableStream<Uint8Array>, deliver: (event: ActivityEvent) => void) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let data: string[] = [];
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line === "") {
        const event = data.length ? parse(data.join("\n")) : undefined;
        data = [];
        if (event) deliver(event);
      } else if (line.startsWith("data:")) {
        data.push(line.slice(line.startsWith("data: ") ? 6 : 5));
      }
    }
  }
}

const isObject = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;

/** The event, or undefined for bad JSON, an unknown type or a missing field. Nothing about its content is logged. */
function parse(text: string): ActivityEvent | undefined {
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return undefined;
  }
  if (!isObject(value)) return undefined;
  switch (value.type) {
    case "agent":
      return isObject(value.agent) ? (value as ActivityEvent) : undefined;
    case "agent-gone":
      return typeof value.id === "string" ? (value as ActivityEvent) : undefined;
    case "deliverable":
      return isObject(value.deliverable) ? (value as ActivityEvent) : undefined;
    case "desk":
      return isObject(value.desk) ? (value as ActivityEvent) : undefined;
    case "waiting":
      return typeof value.count === "number" ? (value as ActivityEvent) : undefined;
    default:
      return undefined;
  }
}
