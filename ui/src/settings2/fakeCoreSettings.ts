// For tests only: the routes of today that Settings keeps using (GET /settings/ai, the roles, the prices, the web
// search key, Claude Code off, /costs, the Connectors and adding one, the Backup and restoring, signing out, Undo),
// served beside the fake core with today's shapes. NEVER
// import this from application code. Call serveSettings() once in a test file, after startFakeCore() (and
// serveFirstLaunch() for the AI consent); `kept` is what the core holds now, and every call is noted in `kept.calls`.
// Its numbers are sample data.
import { http, HttpResponse } from "msw";
import { beforeEach } from "vitest";
import { server } from "@/api/fakeCore";
import type { AiSettings, BackupState, ConnectorAsk, ConnectorRow, FoundTender, SearchState } from "@/api/settingsKept";
import { older } from "@/firstlaunch2/fakeCoreFirstLaunch";

type Kept = {
  ai: AiSettings;
  search: SearchState;
  connectors: ConnectorRow[];
  backup: BackupState;
  /** What GET /backup/found answers for any folder. */
  found: FoundTender[];
  /** The card POST /connectors answers. */
  card: ConnectorAsk;
  /** Undo tokens the core still holds, and what each puts back. */
  undo: Map<string, () => void>;
  calls: string[];
};

export const kept = {} as Kept;
const TOKEN = "5a" + "e0".padStart(30, "0");
export const CODE = "AB12C-DE34F-GH56J-KL78M-NP90Q"; // a sample recovery code
const sample = { on_device: false, price_in: "3", price_out: "15" };

function reset(): void {
  Object.assign(kept, {
    ai: {
      connectors: [
        { id: "anthropic", kind: "model", name: "Claude (sample)", provider: "Anthropic", on_device: false, key_set: true, error: null },
      ],
      sheet: [
        { connector: "anthropic", model: "claude-sample-large", name: "Claude large (sample)", provider: "Anthropic", ...sample },
        { connector: "anthropic", model: "claude-sample-small", name: "Claude small (sample)", provider: "Anthropic", ...sample },
      ],
      roles: {},
      defaults: { lead: { connector: "anthropic", model: "claude-sample-large" } },
    },
    search: { provider: null, own_key: false },
    connectors: [{ name: "drive-sample", transport: "http", runs: "https://mcp.example.com/drive", enabled: true, tools: 3 }],
    backup: {
      folder: "/home/engineer/Backups",
      reachable: true,
      last_run: "2026-11-09T18:00:00.000000+00:00",
      note: null,
      backup_key: { local: true, in_account: false, code_saved: false },
      projects: [],
    },
    found: [
      { id: "1".repeat(32), name: "Tower sample", last_backup: "2026-11-08T10:00:00.000000+00:00", needs: null },
      { id: "2".repeat(32), name: null, last_backup: "2026-11-07T10:00:00.000000+00:00", needs: "project_code" },
    ],
    card: {
      id: "c".repeat(32),
      title: { en: "Add the Connector «files-sample»?", ar: "نضيف الموصل «files-sample»؟" },
      detail: { en: "It runs: files-sample --serve", ar: "بيشغل: files-sample --serve" },
      options: ["yes", "no"],
      payload: {
        tools: [{ name: "read_file", purpose: "Reads a file (sample)", read_only: true, destructive: false, open_world: false }],
        questions: [{ id: "read_without_asking", options: ["yes", "no"] }, { id: "search", options: ["none", "read_file"] }],
      },
    },
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
  http.put("*/api/settings/ai/prices", async ({ request }) => {
    const body = (await note(request, "/settings/ai/prices")) as { connector: string; model: string; in: string; out: string };
    if (!/^\d+(\.\d+)?$/.test(body.in) || !/^\d+(\.\d+)?$/.test(body.out))
      return HttpResponse.json({ error: { en: "Write the number exactly.", ar: "اكتب الرقم بالظبط." }, field: "in" }, { status: 422 });
    const card = kept.ai.sheet.find((it) => it.connector === body.connector && it.model === body.model)!;
    Object.assign(card, { price_in: body.in, price_out: body.out });
    return HttpResponse.json(card);
  }),
  http.post("*/api/connectors", async ({ request }) => {
    await note(request, "/connectors");
    return HttpResponse.json({ card: kept.card });
  }),
  http.post("*/api/connectors/cards/:id", async ({ request, params }) => {
    const body = (await note(request, `/connectors/cards/${String(params.id)}`)) as { choice: string };
    if (body.choice !== "yes") return HttpResponse.json({ connector: null });
    const row: ConnectorRow = { name: "files-sample", transport: "stdio", runs: "files-sample --serve", enabled: true, tools: 1 };
    kept.connectors.push(row);
    return HttpResponse.json({ connector: row });
  }),
  http.get("*/api/backup/found", ({ request }) => {
    kept.calls.push(`GET /backup/found ${new URL(request.url).searchParams.get("path")}`);
    return HttpResponse.json({ projects: kept.found });
  }),
  http.post("*/api/backup/restore", async ({ request }) => {
    const body = (await note(request, "/backup/restore")) as { project_id: string; code?: string };
    const tender = kept.found.find((it) => it.id === body.project_id)!;
    if (tender.needs !== null && body.code !== CODE)
      return HttpResponse.json({ error: { en: "That code does not open it.", ar: "الكود ده مش بيفتحه." } }, { status: 422 });
    kept.found = kept.found.filter((it) => it !== tender);
    return HttpResponse.json({ id: tender.id, name: tender.name ?? "Hidden sample" });
  }),
  http.post("*/api/backup/recovery-code", async ({ request }) => {
    await note(request, "/backup/recovery-code");
    return HttpResponse.json({ code: CODE });
  }),
  http.post("*/api/backup/recovery-code/confirm", async ({ request }) => {
    const body = (await note(request, "/backup/recovery-code/confirm")) as { last_group: string };
    if (body.last_group !== CODE.slice(-5))
      return HttpResponse.json({ error: { en: "That is not its last group.", ar: "دي مش آخر مجموعة فيه." } }, { status: 422 });
    kept.backup = { ...kept.backup, backup_key: { ...kept.backup.backup_key, code_saved: true } };
    return HttpResponse.json({ saved: true });
  }),
  http.delete("*/api/account", async ({ request }) => {
    await note(request, "/account");
    older.account = { state: "signed_out" };
    return HttpResponse.json({ state: "signed_out" });
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
