// The one way the screen reaches One's core. `path` is the core's own route ("/projects", "/chat"…). In development the
// Vite server forwards /api to the core with the launch secret, so the page never holds it. In the installed app there
// is no server behind /api: the call goes to the shell (desktop/src/shim.rs), which adds the secret, lets through only
// the core's own routes and streams the answer back over a Channel. Either way the caller gets a plain Response.
import { Channel, invoke } from "@tauri-apps/api/core";

/** The installed app: a release build inside the Tauri window. */
export function inInstalledApp(): boolean {
  return import.meta.env.PROD && typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export function api(path: string, init?: RequestInit): Promise<Response> {
  if (!inInstalledApp()) return fetch("/api" + path, init);
  const body = init?.body;
  if (body instanceof Blob || body instanceof ArrayBuffer || ArrayBuffer.isView(body)) return upload(path, body, init!);
  return stream(path, init);
}

// What the shell sends over the Channel: a head, raw chunks, then the end or an error.
type ShellEvent =
  | { event: "head"; status: number; headers: [string, string][] }
  | { event: "end" }
  | { event: "error"; code: string };

// Statuses whose Response may not have a body.
const NO_BODY = new Set([204, 205, 304]);

const aborted = (signal: AbortSignal) => signal.reason ?? new DOMException("The call was stopped.", "AbortError");

// Like fetch when the network fails: the caller's own fallback line says it in words.
const unreachable = (why: string) => new TypeError(`One could not reach its core (${why}).`);

function pairs(headers: HeadersInit | undefined): [string, string][] {
  return [...new Headers(headers).entries()];
}

function textBody(body: BodyInit | null | undefined): string | null {
  if (body == null) return null;
  if (typeof body === "string") return body;
  if (body instanceof URLSearchParams) return body.toString();
  throw new TypeError("This kind of body cannot be sent to the core in the installed app.");
}

function stream(path: string, init: RequestInit | undefined): Promise<Response> {
  const signal = init?.signal ?? undefined;
  if (signal?.aborted) return Promise.reject(aborted(signal));
  let body: string | null;
  try {
    body = textBody(init?.body);
  } catch (error) {
    return Promise.reject(error);
  }
  const id = crypto.randomUUID();

  return new Promise((resolve, reject) => {
    let state: "waiting" | "open" | "done" = "waiting";
    let controller!: ReadableStreamDefaultController<Uint8Array>;
    const readable = new ReadableStream<Uint8Array>({
      start: (c) => void (controller = c),
      cancel: () => {
        if (state === "done") return;
        done();
        cancel();
      },
    });
    const cancel = () => void invoke("core_cancel", { id }).catch(() => undefined);
    const done = () => {
      state = "done";
      signal?.removeEventListener("abort", onAbort);
    };
    const fail = (error: unknown) => {
      if (state === "waiting") reject(error);
      else if (state === "open") controller.error(error);
      done();
    };
    const onAbort = () => {
      if (state === "done") return;
      cancel();
      fail(aborted(signal!));
    };
    signal?.addEventListener("abort", onAbort, { once: true });

    const onEvent = new Channel<ShellEvent | ArrayBuffer>((message) => {
      if (state === "done") return;
      if (!("event" in message)) {
        if (state === "open") controller.enqueue(new Uint8Array(message));
        return;
      }
      if (message.event === "head") {
        state = "open";
        const { status, headers } = message;
        resolve(new Response(NO_BODY.has(status) ? null : readable, { status, headers }));
      } else if (message.event === "end") {
        if (state === "waiting") return fail(unreachable("no answer"));
        controller.close();
        done();
      } else {
        fail(unreachable(message.code));
      }
    });

    const call = { id, method: (init?.method ?? "GET").toUpperCase(), path, headers: pairs(init?.headers), body, onEvent };
    invoke("core_fetch", call).catch((error: unknown) => fail(unreachable(String(error))));
  });
}

// A file, or other bytes, goes up whole as the raw body of the call, and its answer comes back whole.
async function upload(path: string, body: Blob | BufferSource, init: RequestInit): Promise<Response> {
  if (init.signal?.aborted) throw aborted(init.signal);
  const bytes =
    body instanceof Blob
      ? new Uint8Array(await body.arrayBuffer())
      : body instanceof ArrayBuffer
        ? new Uint8Array(body)
        : new Uint8Array(body.buffer, body.byteOffset, body.byteLength);
  const headers: Record<string, string> = Object.fromEntries(pairs(init.headers));
  if (body instanceof Blob && body.type && !headers["content-type"]) headers["content-type"] = body.type; // as fetch does
  headers["x-qsone-path"] = path;
  headers["x-qsone-method"] = (init.method ?? "POST").toUpperCase();
  headers["content-length"] = String(bytes.byteLength);
  const answer = await invoke<{ status: number; headers: [string, string][]; body: string }>("core_upload", bytes, {
    headers,
  }).catch((error: unknown) => {
    throw unreachable(String(error));
  });
  return new Response(NO_BODY.has(answer.status) ? null : answer.body, {
    status: answer.status,
    headers: answer.headers,
  });
}
