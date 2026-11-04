// Talking to One's core behind /api.
import type { Text } from "./i18n";

// The core sends a failure as {error: {en, ar}}; anything else gets the screen's own line.
export async function coreLine(response: Response | undefined, fallback: Text): Promise<Text> {
  const body = (await response?.json().catch(() => undefined)) as { error?: Partial<Text> } | undefined;
  const line = body?.error;
  return typeof line?.en === "string" && typeof line.ar === "string" ? (line as Text) : fallback;
}

/** Sends JSON to the core; a network failure answers undefined, like a refused request. */
export function send(url: string, method: string, body?: unknown): Promise<Response | undefined> {
  return fetch(url, {
    method,
    ...(body === undefined ? {} : { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
  }).catch(() => undefined);
}
