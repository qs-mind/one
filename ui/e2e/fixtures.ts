// The core, as the screen sees it behind /api, for the end-to-end tests: every call is answered here with
// `page.route`, so Playwright never starts the core and no test reaches the network. A scene is a project's data
// (files, Deliverables, team, status, saved layout, live events); every name in it says it is a sample.
// The mock keeps what the screen writes (layout saves, chat requests), so a test can check them and a reload sees
// the saved layout, as it would from the project's own file.
import type { Page, Request, Route } from "@playwright/test";
import type { ActivityEvent, AgentInfo, FileInfo, FilePiece, FrameKey, Placed, ProjectStatus, Team, View } from "../src/canvas/types";
import type { DeliverableInfo, DocumentView, SheetView, View as DeliverableView } from "../src/deliverables/types";

export type Project = { id: string; name: string; created_at: string };

export type Scene = {
  project: Project;
  /** Other projects in the switcher. */
  others: Project[];
  files: FileInfo[];
  pages: Record<string, number>;
  text: Record<string, FilePiece[]>;
  deliverables: DeliverableInfo[];
  team: Team;
  status: ProjectStatus;
  layout: { frames: Placed[]; view: View | null };
  /** Sent on the first /activity request; later events go with `core.emit`. */
  activity: ActivityEvent[];
};

const at = "2026-11-05T09:00:00+00:00";
const P = "a".repeat(32);

function deliverable(fields: Partial<DeliverableInfo> & Pick<DeliverableInfo, "id" | "kind" | "title">): DeliverableInfo {
  return {
    language: "ar",
    status: "draft",
    code: null,
    same_provider: false,
    revision: null,
    desk: null,
    off_desk: false,
    progress: null,
    open_comments: 0,
    updated_at: at,
    pending: 0,
    total: null,
    sample: true,
    ...fields,
  };
}

function agent(fields: Partial<AgentInfo> & Pick<AgentInfo, "id" | "kind" | "role">): AgentInfo {
  return { desk_id: null, model: "claude-sonnet-5", state: "working", line: null, brief_id: "brief-sample", focus: null, at, ...fields };
}

const pricingDesk = { en: "Pricing Desk (sample)", ar: "قسم التسعير - عينة" };

export const estimator = agent({
  id: "est",
  kind: "specialist",
  role: { en: "Estimator (sample)", ar: "مهندس التسعير - عينة" },
  desk_id: "pricing",
  line: { en: "Pricing item 3/02 (sample)", ar: "بيسعّر البند 3/02 - عينة" },
  focus: { frame: "deliverable:pricing", anchor: null },
});

export const checker = agent({
  id: "chk",
  kind: "checker",
  role: { en: "Checking QS (sample)", ar: "مهندس المراجعة - عينة" },
  state: "thinking",
  focus: { frame: "deliverable:pricing", anchor: null },
});

/** A small tender: 4 files, 4 Deliverables, the team and one Desk; 8 frames (Project files, one opened PDF, the 4
 * Deliverables, the team and the Desk). */
export function small(): Scene {
  return {
    project: { id: P, name: "برج إداري - عينة", created_at: at },
    others: [{ id: "b".repeat(32), name: "مدرسة - عينة", created_at: "2026-11-01T09:00:00+00:00" }],
    files: [
      { id: "spec", name: "المواصفات الفنية - عينة.pdf", status: "read", note: null, replaces: null },
      { id: "boq", name: "مقايسة العميل - عينة.xlsx", status: "read", note: null, replaces: null },
      { id: "dwg", name: "لوحات معمارية A-101 - عينة.pdf", status: "partly_read", note: null, replaces: null },
      { id: "quote", name: "عرض سعر حديد - عينة.pdf", status: "read", note: null, replaces: null },
    ],
    pages: { spec: 18, dwg: 6, quote: 2 },
    text: { boq: [{ locator: { sheet: "BOQ", row: 12 }, text: "3/02 خرسانة مسلحة للأعمدة - عينة" }] },
    deliverables: [
      deliverable({ id: "takeoff", kind: "sheet", title: "ملخص الحصر - عينة", status: "signed_off", code: "A", revision: 1, progress: { done: 64, total: 64 } }),
      deliverable({ id: "pricing", kind: "sheet", title: "تسعير المقايسة - عينة", status: "checked", code: "B", desk: pricingDesk, progress: { done: 180, total: 420 }, open_comments: 1 }),
      deliverable({ id: "quotes", kind: "sheet", title: "مقارنة عروض الموردين - عينة", desk: pricingDesk, progress: { done: 3, total: 5 } }),
      deliverable({ id: "letter", kind: "document", title: "خطاب العطاء - مسودة عينة" }),
    ],
    team: { desks: [{ id: "pricing", name: pricingDesk, stage: "temporary" }], agents: [estimator, checker] },
    status: {
      stage: { en: "Tender (sample)", ar: "مناقصة - عينة" },
      submission_date: "2026-11-18",
      days_left: 13,
      boq_value: { value: "48200000.00", currency: "EGP", deliverable_id: "pricing", revision: null, status: "checked", sample: true },
      open_comments: 1,
    },
    layout: { frames: [{ key: "file:spec", x: -600, y: 0, w: 480, h: 640, z: 0, collapsed: false }], view: null },
    activity: [],
  };
}

const kinds = ["sheet", "sheet", "document"] as const;
const states = ["draft", "checked", "signed_off"] as const;

/** `n` frames in all: Project files, the team, and n - 2 Deliverables. `saved` gives them a saved grid layout (a
 * project opened before); without it the canvas places them all, as on a first open. */
export function many(n: number, { saved = true } = {}): Scene {
  const scene = small();
  scene.deliverables = Array.from({ length: n - 2 }, (_, i) =>
    deliverable({
      id: `d${i}`,
      kind: kinds[i % kinds.length]!,
      title: `بند ${i + 1} - عينة`,
      status: states[i % states.length]!,
      code: i % 3 === 1 ? "B" : null,
      progress: { done: i % 50, total: 50 },
      open_comments: i % 7 === 0 ? 1 : 0,
    }),
  );
  scene.team = { desks: [], agents: [] };
  scene.status = {};
  scene.layout = { frames: [], view: null };
  if (saved) {
    const keys: FrameKey[] = ["files:all", "team:core", ...scene.deliverables.map((d) => `deliverable:${d.id}` as const)];
    const columns = Math.ceil(Math.sqrt(n));
    scene.layout = {
      frames: keys.map((key, i) => ({ key, x: (i % columns) * 1040, y: Math.floor(i / columns) * 1020, w: 960, h: 900, z: 0, collapsed: false })),
      view: null,
    };
  }
  return scene;
}

// Deliverable views, for the live viewers inside zoomed frames ----------------------------------------------------

const head = (d: DeliverableInfo) => ({
  id: d.id, variant: d.kind === "sheet" ? "boq" : "letter", title: d.title, language: d.language, status: d.status,
  code: d.code, same_provider: d.same_provider, off_desk: d.off_desk, version: 1, at, revision: null, sample: true,
  sources: { s1: { kind: "sample", title: "بيانات تجريبية - عينة", file_name: null, locator: {}, url: null, dated: null } },
  pending: 0, open_comments: 0, records_moved: false,
});

const num = (value: string, id: string) => ({ value, number_id: id, source: "s1", dated: "2026-11-01" });

function viewOf(d: DeliverableInfo): DeliverableView {
  if (d.kind === "document") {
    const doc: DocumentView = {
      ...head(d), kind: "document", refs: {}, untraced: [],
      blocks: [
        { id: "b1", version: 1, node: { type: "h1", children: [{ text: `${d.title}` }] } },
        { id: "b2", version: 1, node: { type: "p", children: [{ text: "الأسعار سارية لمدة ٣٠ يوماً - نص عينة" }] } },
      ],
    };
    return doc;
  }
  const sheet: SheetView = {
    ...head(d), kind: "sheet", incomplete: {}, total: num("4859830.00", `${d.id}-total`),
    columns: [
      { key: "code", label: { en: "Item", ar: "البند" }, kind: "text", edit: false, frozen: true, wrap: false, width: 70 },
      { key: "description", label: { en: "Description", ar: "بيان الأعمال" }, kind: "text", edit: true, frozen: false, wrap: true, width: 360 },
      { key: "quantity", label: { en: "Qty", ar: "الكمية" }, kind: "number", edit: true, frozen: false, wrap: false, width: 90 },
      { key: "rate", label: { en: "Rate", ar: "الفئة" }, kind: "number", edit: true, frozen: false, wrap: false, width: 110 },
    ],
    rows: Array.from({ length: 12 }, (_, i) => ({
      id: `r${i}`, kind: "item" as const, item_id: `i${i}`, item_version: 1, version: 1, code: `03/${String(i + 1).padStart(2, "0")}`,
      cells: { description: { text: `خرسانة مسلحة - بند عينة ${i + 1}` }, quantity: num(String(10 + i), `q${i}`), rate: num("2589.00", `r${i}`) },
    })),
  };
  return sheet;
}

// The Lead QS's reply, as the AI SDK UI message stream the core sends ----------------------------------------------

export const replyText = { ar: "تمام، هراجع التسعير - رد عينة", en: "Sure, I will check the pricing (sample reply)" };

function uiStream(text: string): string {
  const chunks = [
    { type: "start", messageId: `m${Date.now()}` },
    { type: "start-step" },
    { type: "text-start", id: "t1" },
    { type: "text-delta", id: "t1", delta: text },
    { type: "text-end", id: "t1" },
    { type: "finish-step" },
    { type: "finish" },
  ];
  return chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join("") + "data: [DONE]\n\n";
}

// A 2×2 PNG of Stone: what a page image is to the screen.
const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAEklEQVR4nGP49O75p3fPGSAUAE3+Cx2IEDYSAAAAAElFTkSuQmCC",
  "base64",
);

const aiSettings = {
  connectors: [{ id: "anthropic", kind: "model", name: "Claude", provider: "anthropic", on_device: false, key_set: true, error: null }],
  sheet: [
    {
      connector: "anthropic", model: "claude-opus-5-5", name: "Claude Opus 5.5", provider: "anthropic", images: true, tools: true,
      context: 200000, price_in: "5.00", price_out: "25.00", price_source: "sample prices", on_device: false, subscription: false,
    },
  ],
  roles: {},
  defaults: {},
};

export type Core = {
  scene: Scene;
  /** Every PUT /canvas/frames body, in order. */
  frameSaves: { frames: Placed[]; removed: FrameKey[] }[];
  viewSaves: View[];
  /** Every POST /api/chat body. */
  chats: Record<string, unknown>[];
  /** Calls no route here answers (they get 404), so a test can see what the screen asked that the mock lacks. */
  unknown: string[];
  /** Sends live events now: they answer the /activity request the screen holds open (the screen then reconnects, as
   * after any stream that ends, and its next request is held open again). */
  emit(events: ActivityEvent[]): void;
  /** Resolves with the next PUT /canvas/frames that `match` accepts. */
  nextFrameSave(match?: (body: { frames: Placed[]; removed: FrameKey[] }) => boolean): Promise<{ frames: Placed[]; removed: FrameKey[] }>;
};

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: "application/json", headers: { "cache-control": "no-store" }, body: JSON.stringify(body) });

/** Answers every /api call of `page` from `scene`; blocks every request that would leave the machine. Also opens the
 * scene's project on load (as the remembered one) unless `remembered` is false, and sets the page language. */
export async function mockCore(
  page: Page,
  scene: Scene,
  { language = "ar", remembered = true }: { language?: "ar" | "en"; remembered?: boolean } = {},
): Promise<Core> {
  const waiters: { match: (b: { frames: Placed[]; removed: FrameKey[] }) => boolean; resolve: (b: { frames: Placed[]; removed: FrameKey[] }) => void }[] = [];
  const core: Core = {
    scene,
    frameSaves: [],
    viewSaves: [],
    chats: [],
    unknown: [],
    nextFrameSave: (match = () => true) => new Promise((resolve) => waiters.push({ match, resolve })),
    emit(events) {
      queued.push(...events);
      const held = open;
      open = undefined;
      held?.();
    },
  };
  const saved = new Map(scene.layout.frames.map((f) => [f.key, f]));
  const queued: ActivityEvent[] = [...scene.activity];
  let open: (() => void) | undefined; // answers the held /activity request with what is queued
  const projects = [scene.project, ...scene.others];
  const deliverables = new Map(scene.deliverables.map((d) => [d.id, d]));

  await page.addInitScript(
    ({ language, project }) => {
      // the two keys the screen keeps in localStorage, set before the page reads them; only on the first load
      // (the screen writes the language on every load), so a reload keeps what the screen set itself
      if (localStorage.getItem("qsone.language") === null) {
        localStorage.setItem("qsone.language", language);
        if (project) localStorage.setItem("qsone.project", project);
      }
    },
    { language, project: remembered ? scene.project.id : null },
  );

  await page.route(
    (url) => url.hostname !== "127.0.0.1" && url.protocol !== "data:" && url.protocol !== "blob:",
    (route) => route.abort("blockedbyclient"),
  );

  await page.route("**/api/**", async (route: Route, request: Request) => {
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const method = request.method();
    const key = `${method} ${path}`;
    const base = `/projects/${scene.project.id}`;

    if (key === "GET /health") return json(route, { ok: true });
    // past the first launch (Plan 8), with the AI consent given
    if (key === "GET /setup") return json(route, { done: true, steps: { language: "done", account: "skipped", ai: "done", card: "skipped", usage: "skipped" } });
    if (key === "GET /settings/ai-consent") return json(route, { at: "2026-11-05T08:00:00+00:00", text_version: 1 });
    if (key === "GET /settings/ai") return json(route, aiSettings);
    if (key === "GET /settings/ai/caps") return json(route, { caps: null, recommended: null });
    if (key === "GET /briefs/unfinished") return json(route, { briefs: [] });
    if (key === "GET /projects") return json(route, { projects: projects.map((p) => ({ ...p, open: p.id === scene.project.id })) });
    const opened = /^POST \/projects\/([^/]+)\/(open|close)$/.exec(key);
    if (opened) {
      const project = projects.find((p) => p.id === opened[1]);
      return project ? json(route, opened[2] === "open" ? project : { ok: true }) : json(route, { error: { en: "No such project", ar: "مفيش مشروع بالاسم ده" } }, 404);
    }

    // the chat (Plan 4): earlier messages, no Brief running, and one short reply per message
    if (/^GET \/chat\/[^/]+\/messages$/.test(key)) return json(route, { messages: [] });
    if (/^GET \/chat\/[^/]+\/stream$/.test(key)) return route.fulfill({ status: 204 });
    if (key === "POST /chat") {
      core.chats.push(request.postDataJSON() as Record<string, unknown>);
      return route.fulfill({
        status: 200,
        headers: { "content-type": "text/event-stream", "x-vercel-ai-ui-message-stream": "v1", "cache-control": "no-store" },
        body: uiStream(language === "ar" ? replyText.ar : replyText.en),
      });
    }

    if (path.startsWith(base)) {
      const rest = path.slice(base.length);
      const r = `${method} ${rest}`;
      if (r === "GET /files") return json(route, { files: scene.files });
      if (r === "GET /deliverables") return json(route, { deliverables: [...deliverables.values()] });
      if (r === "GET /team") return json(route, scene.team);
      if (r === "GET /status") return json(route, scene.status);
      if (r === "GET /canvas") return json(route, { frames: [...saved.values()], view: scene.layout.view });
      if (r === "PUT /canvas/frames") {
        const body = request.postDataJSON() as { frames: Placed[]; removed: FrameKey[] };
        for (const k of body.removed) saved.delete(k);
        for (const f of body.frames) saved.set(f.key, f);
        core.frameSaves.push(body);
        for (const w of [...waiters]) {
          if (!w.match(body)) continue;
          waiters.splice(waiters.indexOf(w), 1);
          w.resolve(body);
        }
        return json(route, { ok: true });
      }
      if (r === "PUT /canvas/view") {
        const view = request.postDataJSON() as View;
        scene.layout.view = view;
        core.viewSaves.push(view);
        return json(route, { ok: true });
      }
      if (r === "GET /activity") {
        // a stream with nothing new is held open (never answered, so the screen does not reconnect every second)
        if (!queued.length) await new Promise<void>((resolve) => (open = resolve));
        const events = queued.splice(0);
        return route
          .fulfill({
            status: 200,
            headers: { "content-type": "text/event-stream", "cache-control": "no-store" },
            body: events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join(""),
          })
          .catch(() => undefined); // the page went away meanwhile
      }
      const pages = /^GET \/files\/([^/]+)\/pages$/.exec(r);
      if (pages) return scene.pages[pages[1]!] ? json(route, { pages: scene.pages[pages[1]!] }) : json(route, { error: { en: "No pages", ar: "مفيش صفحات" } }, 409);
      if (/^GET \/files\/[^/]+\/pages\/\d+$/.test(r)) return route.fulfill({ status: 200, contentType: "image/png", body: PNG });
      const text = /^GET \/files\/([^/]+)\/text$/.exec(r);
      if (text) return json(route, { pieces: scene.text[text[1]!] ?? [] });
      if (r.startsWith("GET /search")) return json(route, { hits: [] });
      const view = /^GET \/deliverables\/([^/]+)$/.exec(r);
      if (view && deliverables.has(view[1]!)) return json(route, viewOf(deliverables.get(view[1]!)!));
      if (/^GET \/deliverables\/[^/]+\/changes$/.test(r)) return json(route, { changes: [] });
      if (/^GET \/deliverables\/[^/]+\/comments$/.test(r)) return json(route, { comments: [] });
    }

    core.unknown.push(key);
    return json(route, { error: { en: "Not found (e2e mock)", ar: "مش موجود (e2e)" } }, 404);
  });

  return core;
}

/** The frames on the canvas, by key, once the canvas has drawn them. */
export const frame = (page: Page, key: FrameKey) => page.locator(`.react-flow__node[data-id="${key}"]`);

/** A frame's position in world coordinates, read from React Flow's transform. */
export async function positionOf(page: Page, key: FrameKey): Promise<{ x: number; y: number }> {
  const transform = await frame(page, key).evaluate((el) => (el as HTMLElement).style.transform);
  const [, x, y] = /translate\(\s*(-?[\d.]+)px,\s*(-?[\d.]+)px\)/.exec(transform) ?? [];
  return { x: Number(x), y: Number(y) };
}

/** Waits for the screen to settle on the canvas: frames drawn and the fonts loaded. */
export async function canvasReady(page: Page, key: FrameKey = "files:all") {
  await frame(page, key).waitFor();
  await page.evaluate(() => document.fonts.ready.then(() => undefined));
}

/** "Show everything" from the palette: every frame in view. A first open shows only what can be read at once (the
 * Project files first), so a test that needs all of them on screen asks for them, as the engineer would. */
export async function showAll(page: Page, language: "ar" | "en" = "ar") {
  const mod = await page.evaluate(() => (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent) ? "Meta" : "Control"));
  await page.keyboard.press(`${mod}+KeyK`);
  await page.keyboard.type(language === "ar" ? "اعرض كل حاجة" : "Show everything");
  await page.keyboard.press("Enter");
  await page.waitForTimeout(500); // the view's glide
}

