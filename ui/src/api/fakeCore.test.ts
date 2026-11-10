import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { describe, expect, it, vi } from "vitest";
import { subscribeActivity, subscribeGeneral, subscribeTender } from "../activity";
import { api } from "../api";
import { client, type GeneralActivity, type Schemas as S, type TenderActivity } from "./client";
import { listening, P1, P2, publish, scenario, stageEnds, startFakeCore } from "./fakeCore";

// The contract as the core declares it. The tests below are driven from it, so a route it gains is tested at once.
type Schema = {
  $ref?: string; type?: string; enum?: unknown[]; const?: unknown; anyOf?: Schema[]; oneOf?: Schema[];
  properties?: Record<string, Schema>; required?: string[]; additionalProperties?: boolean | Schema;
  items?: Schema; prefixItems?: Schema[]; minItems?: number; maxItems?: number;
  minLength?: number; maxLength?: number; minimum?: number; maximum?: number;
};
type Content = { content?: { "application/json": { schema: Schema } } };
type Operation = { requestBody?: Content; responses: Record<string, Content> };
const contract = JSON.parse(readFileSync(join(__dirname, "openapi.json"), "utf8")) as {
  paths: Record<string, Record<string, Operation>>;
  components: { schemas: Record<string, Schema> };
};
const samples = JSON.parse(readFileSync(join(__dirname, "samples.json"), "utf8")) as Record<string, unknown>;

/** What in `value` does not fit `schema`, one line each; none when it fits. It knows the JSON Schema words the
 * contract uses, and it is strict: a key the contract does not declare does not fit. */
function misfits(schema: Schema, value: unknown, at = "$"): string[] {
  if (schema.$ref) return misfits(contract.components.schemas[schema.$ref.split("/").pop()!]!, value, at);
  const options = schema.anyOf ?? schema.oneOf;
  if (options) return options.some((option) => misfits(option, value, at).length === 0) ? [] : [`${at} fits none of its options`];
  if ("const" in schema && value !== schema.const) return [`${at} is not ${JSON.stringify(schema.const)}`];
  if (schema.enum && !schema.enum.includes(value)) return [`${at} is not one of ${JSON.stringify(schema.enum)}`];
  const kind = value === null ? "null" : Array.isArray(value) ? "array" : Number.isInteger(value) ? "integer" : typeof value;
  if (schema.type && schema.type !== kind && !(schema.type === "number" && kind === "integer")) return [`${at} is ${kind}, not ${schema.type}`];
  const text = typeof value === "string";
  const size = text || Array.isArray(value) ? value.length : value;
  const least = (text ? schema.minLength : Array.isArray(value) ? schema.minItems : schema.minimum) ?? -Infinity;
  const most = (text ? schema.maxLength : Array.isArray(value) ? schema.maxItems : schema.maximum) ?? Infinity;
  if (typeof size === "number" && (size < least || size > most)) return [`${at} is outside ${least} to ${most}`];
  if (Array.isArray(value)) {
    return value.flatMap((item, index) => {
      const inside = schema.prefixItems?.[index] ?? schema.items;
      return inside ? misfits(inside, item, `${at}[${index}]`) : [];
    });
  }
  if (kind !== "object") return [];
  const object = value as Record<string, unknown>;
  const open = typeof schema.additionalProperties === "object" ? schema.additionalProperties : undefined;
  return [
    ...(schema.required ?? []).filter((key) => !(key in object)).map((key) => `${at}.${key} is missing`),
    ...Object.entries(object).flatMap(([key, item]) => {
      const inside = schema.properties?.[key] ?? open;
      if (inside) return misfits(inside, item, `${at}.${key}`);
      return schema.properties ? [`${at}.${key} is not in the contract`] : [];
    }),
  ];
}

const id = (tail: string) => "5a" + tail.padStart(30, "0");
// One good call of each route: where its path points in the samples, and what its body says.
const WHERE: Record<string, string> = {
  project_id: P2,
  stage_id: id("1203"), // approved already: approving it again changes nothing
  finding_id: id("9002"), // the one raised Finding
  lesson_id: id("6001"),
  key: "look.theme",
  link_id: "anthropic",
  brief_id: id("b6"),
};
const BODIES: Record<string, unknown> = {
  ProfileIn: { first_name: "مهندس - عينة (sample)", last_name: "", position: "", company: "", org_type: null, country: "EG", currency: "EGP" },
  LessonIn: { text: "بيقيس الخرسانة بالمتر المكعب - عينة (sample)" },
  PlanApproveIn: { version: 1 },
  StageApproveIn: { version: 1 },
  PlanChangeIn: { change_id: id("a3"), accept: true },
  DecideIn: { choice: 0 },
  RoomMessageIn: { text: "استخدموا 5% هالك - عينة (sample)" },
  SettingIn: { value: "dark" },
  AiConnectIn: { key: "sk-ant-sample" },
};
// The routes the samples can only refuse: P2 has a plan already, and no sample Brief has failed.
const REFUSES: Record<string, number> = { "POST /projects/{project_id}/plan/request": 409, "POST /briefs/{brief_id}/retry": 404 };
// The shape of each sample, by the first word of its key.
const SHAPES: Record<string, string> = {
  profile: "Profile", lessons: "Lessons", home: "Home", tender: "TenderView", plan: "PlanView", findings: "Findings",
  members: "Members", team_members: "TeamMembers", room: "RoomPage", setup: "SetupState", settings: "Settings", ai_link: "AiLink",
};

const operations = Object.entries(contract.paths).flatMap(([path, methods]) =>
  Object.entries(methods).map(([method, operation]) => ({ name: `${method.toUpperCase()} ${path}`, method: method.toUpperCase(), path, operation })),
);

startFakeCore();

describe("the fake core answers every route of the contract", () => {
  it("the routes are read from the contract", () => {
    expect(operations.map((operation) => operation.name)).toContain("GET /home"); // the tests below are not an empty list
  });

  it.each(operations)("$name", async ({ name, method, path, operation }) => {
    const filled = path.replace(/\{(\w+)\}/g, (_, param: string) => WHERE[param] ?? expect.fail(`no sample value for {${param}}`));
    const asked = operation.requestBody?.content?.["application/json"].schema;
    const body = asked && (BODIES[asked.$ref?.split("/").pop() ?? ""] ?? expect.fail(`no sample body for ${name}`));
    if (asked) expect(misfits(asked, body)).toEqual([]);

    // A route with no handler is refused by msw, and this call rejects.
    const response = await api(filled, { method, ...(asked && { body: JSON.stringify(body), headers: { "content-type": "application/json" } }) });

    const declared = operation.responses[response.status]?.content?.["application/json"].schema;
    expect(declared, `the contract does not declare ${response.status} for ${name}`).toBeDefined();
    if (name in REFUSES) expect(response.status).toBe(REFUSES[name]);
    else expect(response.ok).toBe(true);
    expect(misfits(declared!, await response.json())).toEqual([]);
  });

  it("a call it has no route for fails, and nothing reaches the network", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    await expect(api("/projects")).rejects.toThrow(TypeError);
  });
});

describe("the samples", () => {
  it.each(Object.keys(samples))("%s fits its shape in the contract", (key) => {
    const shape = SHAPES[key.split(":")[0]!];
    expect(shape, `no shape is named for the sample ${key}`).toBeDefined();
    expect(misfits({ $ref: shape }, samples[key])).toEqual([]);
  });

  it("a value that does not fit is told apart", () => {
    const home = structuredClone(samples.home) as { tenders: Record<string, unknown>[]; waiting?: unknown };
    expect(misfits({ $ref: "Home" }, home)).toEqual([]);
    home.tenders[0]!.state = "asleep";
    home.tenders[0]!.files_read = "22";
    home.tenders[0]!.extra = true;
    (home.tenders[0]!.submission_source as { locator: object }).locator = { box: [72, 310.5, 523] };
    delete home.waiting;
    expect(misfits({ $ref: "Home" }, home)).toEqual([
      "$.waiting is missing",
      expect.stringContaining("$.tenders[0].state is not one of"),
      "$.tenders[0].submission_source fits none of its options",
      "$.tenders[0].files_read is string, not integer",
      "$.tenders[0].extra is not in the contract",
    ]);
  });
});

// One event of each kind the contract declares, made from the samples, and the stream it travels on.
const sample = <Shape>(key: string) => samples[key] as Shape;
const EVENTS: Record<string, { on: string; event: TenderActivity | GeneralActivity }> = {
  PlanEvent: { on: P2, event: { type: "plan", ...sample<S["PlanView"]>(`plan:${P2}`) } },
  FindingEvent: { on: P2, event: { type: "finding", finding: sample<S["Findings"]>(`findings:${P2}`).findings[0]! } },
  RoomEvent: { on: P2, event: { type: "room", message: sample<S["RoomPage"]>(`room:${P2}`).messages[0]! } },
  MemberEvent: { on: P2, event: { type: "member", member: sample<S["TeamMembers"]>(`team_members:${P2}`).members[0]! } },
  TenderEvent: { on: P2, event: { type: "tender", ...sample<S["TenderView"]>(`tender:${P2}`) } },
  BriefEvent: { on: P2, event: { type: "brief", brief_id: id("b6"), state: "running" } },
  HomeEvent: { on: "general", event: { type: "home" } },
  SettingEvent: { on: "general", event: { type: "setting", setting: sample<S["Settings"]>("settings").settings[0]! } },
  SetupEvent: { on: "general", event: { type: "setup", setup: sample<S["SetupState"]>("setup:downloading") } },
  LessonsEvent: { on: "general", event: { type: "lessons" } },
};
const events = Object.keys(contract.components.schemas).filter((name) => name.endsWith("Event"));
/** What in an event does not fit the contract's shape for its type ("plan" is a PlanEvent). */
const eventMisfits = (event: { type: string }) => misfits({ $ref: event.type[0]!.toUpperCase() + event.type.slice(1) + "Event" }, event);

/** A screen that listens to a tender and to what belongs to none, as the new screens do: what it was told, in order. */
async function listen(project: string) {
  const told: (TenderActivity | GeneralActivity)[] = [];
  const stops = [subscribeTender(project, (event) => told.push(event)), subscribeGeneral((event) => told.push(event))];
  await vi.waitFor(() => expect([listening(project), listening("general")]).toEqual([1, 1]));
  const of = <Type extends string>(type: Type) => told.filter((event) => event.type === type) as Extract<TenderActivity | GeneralActivity, { type: Type }>[];
  return { told, of, stop: () => stops.forEach((stop) => stop()) };
}

describe("the fake core's live channel", () => {
  it("the contract's events are read from the contract", () => {
    expect(events).toContain("PlanEvent"); // the tests below are not an empty list
  });

  it.each(events)("a %s reaches a screen", async (name) => {
    const { on, event } = EVENTS[name] ?? expect.fail(`no sample is made for ${name}`);
    expect(misfits({ $ref: name }, event)).toEqual([]);
    const told: unknown[] = [];
    const stop = on === "general" ? subscribeGeneral((it) => told.push(it)) : subscribeTender(on, (it) => told.push(it));
    await vi.waitFor(() => expect(listening(on)).toBe(1));

    publish(on, event);

    await vi.waitFor(() => expect(told).toEqual([event]));
    stop();
    await vi.waitFor(() => expect(listening(on)).toBe(0)); // the fake core sees the screen leave
  });

  it("a write says what it changed: approving a plan moves the plan, the tender's header, its Lead and Home", async () => {
    const screen = await listen(P1);

    await client.POST("/projects/{project_id}/plan/approve", { params: { path: { project_id: P1 } }, body: { version: 1 } });

    await vi.waitFor(() => expect(screen.told.map((event) => event.type).sort()).toEqual(["home", "member", "plan", "tender"]));
    for (const event of screen.told) expect(eventMisfits(event)).toEqual([]);
    const at = { params: { path: { project_id: P1 } } };
    expect(screen.of("plan")[0]!.plan).toEqual((await client.GET("/projects/{project_id}/plan", at)).data!.plan);
    expect(screen.of("plan")[0]!.plan).toMatchObject({ status: "approved" });
    const { type: _, ...header } = screen.of("tender")[0]!;
    expect(header).toEqual((await client.GET("/projects/{project_id}/tender", at)).data);
    expect(screen.of("member")[0]!.member).toMatchObject({ role: "lead", state: "working" });
    screen.stop();
  });

  it("what the core does by itself is said too: a stage ends, a download moves, Home changes", async () => {
    await client.POST("/projects/{project_id}/plan/approve", { params: { path: { project_id: P1 } }, body: { version: 1 } });
    const screen = await listen(P1);

    stageEnds(P1);
    await vi.waitFor(() => expect(screen.of("plan")).toHaveLength(1));
    expect(screen.of("plan")[0]!.plan!.stages[0]!.status).toBe("waiting_engineer");
    await vi.waitFor(() => expect(screen.of("tender").at(-1)).toMatchObject({ tender: { state: "waiting" }, waiting: [{ kind: "stage", blocking: true }] }));

    scenario("setup:downloading");
    await vi.waitFor(() => expect(screen.of("setup").at(-1)?.setup).toEqual(samples["setup:downloading"]));

    const before = screen.of("home").length;
    scenario("home:cut_off");
    await vi.waitFor(() => expect(screen.of("home").length).toBe(before + 1));
    for (const event of screen.told) expect(eventMisfits(event)).toEqual([]);
    screen.stop();
  });

  it("the room, a Finding, a setting and a lesson are said as they change", async () => {
    const screen = await listen(P2);
    const at = { path: { project_id: P2 } };

    const said = await client.POST("/projects/{project_id}/room", { params: at, body: { text: "استخدموا 5% هالك - عينة (sample)" } });
    await client.POST("/projects/{project_id}/findings/{finding_id}/decide", { params: { path: { ...at.path, finding_id: id("9002") } }, body: { choice: 0 } });
    await client.PATCH("/settings/{key}", { params: { path: { key: "look.theme" } }, body: { value: "dark" } });
    await client.DELETE("/engineer/lessons/{lesson_id}", { params: { path: { lesson_id: id("6001") } } });

    await vi.waitFor(() => expect(screen.of("lessons")).toHaveLength(1));
    expect(screen.of("room")[0]!.message).toEqual(said.data);
    expect(screen.of("finding").map(({ finding }) => [finding.id, finding.status])).toEqual([[id("9002"), "settled"], [id("9004"), "raised"]]);
    expect(screen.of("setting")[0]!.setting).toMatchObject({ key: "look.theme", value: "dark" });
    for (const event of screen.told) expect(eventMisfits(event)).toEqual([]);
    screen.stop();
  });

  it("today's events travel on the same stream, to the listeners of today", async () => {
    const old: unknown[] = [];
    const stops = [subscribeActivity(P2, (event) => old.push(event)), subscribeTender(P2, () => {})];
    await vi.waitFor(() => expect(listening(P2)).toBe(1)); // one stream, however many listen

    publish(P2, { type: "waiting", count: 2 });

    await vi.waitFor(() => expect(old).toEqual([{ type: "waiting", count: 2 }]));
    stops.forEach((stop) => stop());
  });
});

// msw and the samples must stay out of the app: only tests, and the fake-core dev page (ui/src/fake, which Vite never
// builds), may import the fake core, its samples or msw, with or without the file's extension.
const FAKE = /["'`](?:msw(?:\/[^"'`\n]*)?|[^"'`\n]*\/(?:fakeCore\w*(?:\.tsx?)?|samples\.json))["'`]/;

it("no application file imports the fake core", () => {
  const root = join(__dirname, "..");
  const files = (dir: string): string[] =>
    readdirSync(dir).flatMap((name) => {
      const path = join(dir, name);
      return statSync(path).isDirectory() ? files(path) : [path];
    });
  const importers = files(root)
    .filter((path) => /\.tsx?$/.test(path) && !/\.test\.tsx?$/.test(path) && !/fakeCore\w*\.ts$/.test(path))
    .filter((path) => !relative(root, path).startsWith(join("fake", "")))
    .filter((path) => FAKE.test(readFileSync(path, "utf8")))
    .map((path) => relative(root, path));
  expect(importers).toEqual([]);
});

it("the guard sees every way in", () => {
  for (const line of [
    'import { scenario } from "./api/fakeCore";',
    'import { scenario } from "./api/fakeCore.ts";',
    'export * from "../api/fakeCoreSamples";',
    'import samples from "./api/samples.json";',
    'import { http } from "msw";',
    'import { setupServer } from "msw/node";',
  ])
    expect(FAKE.test(line), line).toBe(true);
  for (const line of ['import { api } from "./api";', 'import { client } from "./api/client";', 'const name = "mswatch";'])
    expect(FAKE.test(line), line).toBe(false);
});
