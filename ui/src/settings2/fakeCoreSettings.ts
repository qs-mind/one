// For tests only: the routes of today that Settings keeps using (GET /settings/ai, the roles, the web search key,
// Claude Code off, /costs, the Connectors, the Backup, Undo), served beside the fake core with today's shapes. NEVER
// import this from application code. Call serveSettings() once in a test file, after startFakeCore() (and
// serveFirstLaunch() for the AI consent); `kept` is what the core holds now, and every call is noted in `kept.calls`.
// Its numbers are sample data.
import { http, HttpResponse } from "msw";
import { beforeEach } from "vitest";
import { server } from "@/api/fakeCore";
import type { AiSettings, BackupState, ConnectorRow, SearchState } from "@/api/settingsKept";

type Kept = {
  ai: AiSettings;
  search: SearchState;
  connectors: ConnectorRow[];
  backup: BackupState;
  /** Undo tokens the core still holds, and what each puts back. */
  undo: Map<string, () => void>;
  calls: string[];
};

export const kept = {} as Kept;
const TOKEN = "5a" + "e0".padStart(30, "0");

function reset(): void {
  Object.assign(kept, {
    ai: {
      connectors: [
        { id: "anthropic", kind: "model", name: "Claude (sample)", provider: "Anthropic", on_device: false, key_set: true, error: null },
      ],
      sheet: [
        { connector: "anthropic", model: "claude-sample-large", name: "Claude large (sample)", provider: "Anthropic", on_device: false },
        { connector: "anthropic", model: "claude-sample-small", name: "Claude small (sample)", provider: "Anthropic", on_device: false },
      ],
      roles: {},
      defaults: { lead: { connector: "anthropic", model: "claude-sample-large" } },
    },
    search: { provider: null, own_key: false },
    connectors: [{ name: "drive-sample", transport: "http", runs: "https://mcp.example.com/drive", enabled: true, tools: 3 }],
    backup: { folder: "/home/engineer/Backups", reachable: true, last_run: "2026-11-09T18:00:00.000000+00:00", note: null, projects: [] },
    undo: new Map(),
    calls: [],
  } satisfies Kept);
}
reset();

async function note(request: Request, path: string): Promise<unknown> {
  const text = await request.text();
  kept.calls.push(`${request.method} ${path}${text ? ` ${text}` : ""}`);
  return text ? JSON.parse(text) : undefined;
}

const handlers = [
  http.get("*/api/settings/ai", () => HttpResponse.json(kept.ai)),
  http.put("*/api/settings/ai/roles", async ({ request }) => {
    const body = (await note(request, "/settings/ai/roles")) as AiSettings["roles"];
    kept.ai.roles = { ...kept.ai.roles, ...body };
    return HttpResponse.json(kept.ai.roles);
  }),
  http.put("*/api/settings/ai/claude-code", async ({ request }) => {
    await note(request, "/settings/ai/claude-code");
    kept.ai.connectors = kept.ai.connectors.filter((it) => it.id !== "claude-code");
    return HttpResponse.json({ on: false, path: null, keep_copy: true, notice: null });
  }),
  http.get("*/api/settings/search", () => HttpResponse.json(kept.search)),
  http.put("*/api/settings/search-key", async ({ request }) => {
    await note(request, "/settings/search-key");
    kept.search = { provider: "Brave", own_key: true };
    return HttpResponse.json({ set: true });
  }),
  http.get("*/api/costs", () =>
    HttpResponse.json({ today: "1.20", month: "9.65", equivalent: { today: "0", month: "0" }, brief: null }),
  ),
  http.get("*/api/connectors", () => HttpResponse.json({ connectors: kept.connectors })),
  http.put("*/api/connectors/:name/enabled", async ({ request, params }) => {
    const body = (await note(request, `/connectors/${String(params.name)}/enabled`)) as { enabled: boolean };
    const row = kept.connectors.find((it) => it.name === params.name)!;
    row.enabled = body.enabled;
    return HttpResponse.json({ connector: row });
  }),
  http.delete("*/api/connectors/:name", async ({ request, params }) => {
    await note(request, `/connectors/${String(params.name)}`);
    const row = kept.connectors.find((it) => it.name === params.name)!;
    kept.connectors = kept.connectors.filter((it) => it !== row);
    kept.undo.set(TOKEN, () => kept.connectors.push(row));
    return HttpResponse.json({ undo: TOKEN, window_ms: 6000 });
  }),
  http.get("*/api/backup", () => HttpResponse.json(kept.backup)),
  http.put("*/api/backup/folder", async ({ request }) => {
    const body = (await note(request, "/backup/folder")) as { path: string };
    kept.backup = { ...kept.backup, folder: body.path };
    return HttpResponse.json(kept.backup);
  }),
  http.post("*/api/backup/run", async ({ request }) => {
    await note(request, "/backup/run");
    kept.backup = { ...kept.backup, last_run: "2026-11-10T08:00:00.000000+00:00" };
    return HttpResponse.json({ backed_up: 2 });
  }),
  http.post("*/api/undo/:token", async ({ request, params }) => {
    await note(request, `/undo/${String(params.token)}`);
    const putBack = kept.undo.get(String(params.token));
    if (!putBack) return HttpResponse.json({ error: { en: "Too late to undo.", ar: "فات وقت التراجع." } }, { status: 404 });
    kept.undo.delete(String(params.token));
    putBack();
    return new HttpResponse(null, { status: 204 });
  }),
];

export function serveSettings(): void {
  beforeEach(() => {
    reset();
    server.use(...handlers);
  });
}
