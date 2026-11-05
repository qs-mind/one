// Talking to One's core behind /api.
import { api } from "./api";
import type { Text } from "./i18n";

/** What fixes a core text, as the core says (core/qsone/copy.py FIXES): AI settings, the Connect AI step, the same
 * check once more, or the Backup panel. The core's words never say where to go; the screen adds the action that fits
 * where the text shows (none in the place itself). */
export type Fix = "ai" | "consent" | "retry" | "backup";
const FIXES: readonly string[] = ["ai", "consent", "retry", "backup"];

/** The `fix` the core sent with a text, when it is one the screen knows. */
export function fixOf(value: unknown): Fix | undefined {
  return typeof value === "string" && FIXES.includes(value) ? (value as Fix) : undefined;
}

// The core sends a failure as {error: {en, ar}, fix?}; anything else gets the screen's own line.
export async function coreAnswer(response: Response | undefined, fallback: Text): Promise<{ line: Text; fix?: Fix }> {
  const body = (await response?.json().catch(() => undefined)) as { error?: Partial<Text>; fix?: unknown } | undefined;
  const line = body?.error;
  if (typeof line?.en !== "string" || typeof line.ar !== "string") return { line: fallback };
  const fix = fixOf(body?.fix);
  return fix ? { line: line as Text, fix } : { line: line as Text };
}

export async function coreLine(response: Response | undefined, fallback: Text): Promise<Text> {
  return (await coreAnswer(response, fallback)).line;
}

/** Sends JSON to the core; a network failure (or `signal` stopping it) answers undefined, like a refused request. */
export function send(path: string, method: string, body?: unknown, signal?: AbortSignal): Promise<Response | undefined> {
  return api(path, {
    method,
    ...(body === undefined ? {} : { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
    ...(signal ? { signal } : {}),
  }).catch(() => undefined);
}
