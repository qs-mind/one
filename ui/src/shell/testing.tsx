// For the shell's tests: a core behind a mocked fetch, the AI SDK stream as the core sends it, and a stand-in for
// the canvas (the real one has its own tests), which records what the shell asks of it.
import { vi } from "vitest";
import type { CanvasProps } from "../canvas/Canvas";

export const reply = [
  { type: "start", messageId: "m1" },
  { type: "start-step" },
  { type: "text-start", id: "t1" },
  { type: "text-delta", id: "t1", delta: "مرحبا" },
  { type: "text-delta", id: "t1", delta: " Hello" },
  { type: "text-end", id: "t1" },
  { type: "finish-step" },
  { type: "finish" },
];

export const running = { type: "data-status", id: "b1", data: { state: "running", step: null } };

// A body in the AI SDK UI message stream format. Left open (`end: false`), it behaves like a Brief still at work,
// which only ends when the request is aborted.
function stream(chunks: object[], signal?: AbortSignal | null, end = true) {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`));
      if (end) {
        controller.enqueue(encoder.encode("data: [DONE]\n\n"));
        controller.close();
      }
      signal?.addEventListener("abort", () => controller.error(new DOMException("aborted", "AbortError")));
    },
  });
}

const uiStream = { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1" };
export const streamed = (chunks: object[], init: RequestInit, end = true) =>
  new Response(stream(chunks, init.signal, end), { headers: uiStream });

export type Route = (init: RequestInit, url: string) => Response | Promise<Response>;

const anthropic = { id: "anthropic", kind: "model", name: "Claude", provider: "anthropic", on_device: false, key_set: true, error: null };
const opus = { connector: "anthropic", model: "claude-opus-5-5" };
const aiSettings = (keySet: boolean) => ({
  connectors: [{ ...anthropic, key_set: keySet }],
  sheet: keySet
    ? [
        {
          ...opus,
          name: "Claude Opus 5.5",
          provider: "anthropic",
          images: true,
          tools: true,
          context: 200000,
          price_in: "5.00",
          price_out: "25.00",
          price_source: "genai-prices sample: https://example.com/prices",
          on_device: false,
          subscription: false,
          efforts: ["low", "medium", "high"],
          effort_default: "high",
        },
        {
          connector: "anthropic",
          model: "claude-haiku-sample",
          name: "Claude Haiku (sample)",
          provider: "anthropic",
          images: false,
          tools: true,
          context: 200000,
          price_in: "1.00",
          price_out: "5.00",
          price_source: "genai-prices sample: https://example.com/prices",
          on_device: false,
          subscription: false,
          efforts: [],
          effort_default: null,
        },
      ]
    : [],
  roles: keySet ? { lead: opus, checker: opus, specialist: opus, quick: opus } : {},
  defaults: keySet ? { lead: opus, checker: opus, specialist: opus, quick: opus } : {},
});

export const P1 = { id: "p1", name: "مدرسة - عينة", created_at: "2026-11-04T08:00:00+00:00" };
export const P2 = { id: "p2", name: "برج - عينة", created_at: "2026-11-05T08:00:00+00:00" };

/** The core behind /api: the routes a test gives (by "METHOD url"), then what an idle core answers. */
export function core({ keySet = true, routes = {} }: { keySet?: boolean; routes?: Record<string, Route> } = {}) {
  let saved = keySet;
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const key = `${init.method ?? "GET"} ${url}`;
    const route = routes[key];
    if (route) return route(init, url);
    if (key === "GET /api/settings/ai") return Response.json(aiSettings(saved));
    if (key === "PUT /api/settings/ai-key") {
      saved = true;
      return Response.json({ set: true });
    }
    if (key === "GET /api/settings/ai/caps") {
      const caps = { brief: "3.00", day: "15.00", month: "150.00", budget_above: "0.50", subscription_stops: false };
      return Response.json({ caps, recommended: caps });
    }
    if (key === "GET /api/briefs/unfinished") return Response.json({ briefs: [] });
    if (key === "GET /api/projects") return Response.json({ projects: [{ ...P2, open: false }, { ...P1, open: false }] });
    const opened = /^POST \/api\/projects\/(p\d)\/open$/.exec(key)?.[1];
    if (opened) return Response.json(opened === "p1" ? P1 : P2);
    if (/^POST \/api\/projects\/[^/]+\/close$/.test(key)) return Response.json({ ok: true });
    if (/^GET \/api\/chat\/[^/]+\/messages$/.test(key)) return Response.json({ messages: [] });
    if (/^GET \/api\/chat\/[^/]+\/stream$/.test(key)) return new Response(null, { status: 204 });
    return new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

export const calls = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls.filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method);

export const bodyOf = (init: RequestInit | undefined) => JSON.parse(String(init!.body)) as Record<string, unknown>;

/** What the canvas stand-in was given, so a test can open a Deliverable full screen as the canvas would. */
export const shown: { props?: CanvasProps } = {};

/** Replaces ../canvas/Canvas in a test file:
 * `vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("./testing")).CanvasStandIn }))`. */
export function CanvasStandIn(props: CanvasProps) {
  shown.props = props;
  return (
    <section aria-label="canvas stand-in">
      <button type="button">frame</button>
    </section>
  );
}
