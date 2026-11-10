// The fake core's live channel: GET /projects/{id}/activity as the core serves it (server-sent events, one `data:` line
// each, nothing kept), for a tender's id or "general". The fake core says here what its own writes change; a test says
// the rest with `publish`. A test imports fakeCore.ts, which hands this on. NEVER import this from application code.
import { http, HttpResponse } from "msw";
import type { ActivityEvent } from "../project/types";
import type { GeneralActivity, TenderActivity } from "./client";

type Stream = ReadableStreamDefaultController<Uint8Array>;
const open = new Map<string, Set<Stream>>(); // the streams that are open now, by channel

/** How many streams a channel has open: 1 while a screen listens to it, however many of its parts do. */
export const listening = (channel: string): number => open.get(channel)?.size ?? 0;

/** Says an event to whoever listens to the channel now, as the core does: a contract event, or one of today's (a
 * Deliverable or a file that changed, for the kept viewers). Nobody listening: nobody hears it. */
export function publish(channel: string, event: TenderActivity | GeneralActivity | ActivityEvent): void {
  const line = new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`);
  for (const stream of open.get(channel) ?? []) stream.enqueue(line);
}

/** Ends every open stream, as a core that went away does (and after each test). */
export function hangUp(): void {
  for (const streams of open.values()) for (const stream of streams) stream.close();
  open.clear();
}

export const activity = http.get("*/api/projects/:channel/activity", ({ params, request }) => {
  const channel = String(params.channel);
  const streams = open.get(channel) ?? new Set<Stream>();
  open.set(channel, streams);
  let mine: Stream;
  const leave = () => void streams.delete(mine); // the screen stopped listening
  const body = new ReadableStream<Uint8Array>({ start: (stream) => void streams.add((mine = stream)), cancel: leave });
  request.signal.addEventListener("abort", leave);
  return new HttpResponse(body, { headers: { "content-type": "text/event-stream" } });
});
