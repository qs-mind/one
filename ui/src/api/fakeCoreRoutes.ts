// The fake core's routes: every Phase 1 route answered from the samples (fakeCoreSamples.ts), as msw handlers. Tests
// reach them through fakeCore.ts, the fake-core dev page through fakeCoreBrowser.ts. NEVER import this from
// application code.
import { http, HttpResponse } from "msw";
import type { Schemas as S } from "./client";
import type { paths } from "./contract";
import { activity, publish } from "./fakeCoreLive";
import { ai, closed, data, missing, newId, now, planOf, refuse, settle, tenderOf, wait } from "./fakeCoreSamples";

// What a route may answer, as [status, body]: only the statuses and shapes the contract declares for it. A route the
// contract gains or loses, or an answer of another shape, stops the typecheck here.
type Json<T> = T extends { content: { "application/json": infer Body } } ? Body : never;
type Reply<Op> = Op extends { responses: infer R } ? { [Status in keyof R]: [Status, Json<R[Status]>] }[keyof R] : never;
type Call<Op> = {
  path: Op extends { parameters: { path: infer Path } } ? Path : Record<string, never>;
  query: URLSearchParams;
  body: Op extends { requestBody: infer Body } ? Json<Body> : undefined;
};
type Routes = { [Path in keyof paths]: { [Method in keyof paths[Path]]: (call: Call<paths[Path][Method]>) => Reply<paths[Path][Method]> } };

const UNDO: S["Undoable"] = { undo: "5a" + "d0".padStart(30, "0"), window_ms: 6000 };
const EXACT = /^\d+(\.\d+)?$/; // money and numbers travel as exact decimal text

function fits(setting: S["ChoiceSetting"] | S["MoneySetting"] | S["NumberSetting"], value: string): boolean {
  if (setting.control === "choice") return setting.choices.some((choice) => choice.value === value);
  if (!EXACT.test(value)) return false;
  return setting.control === "money" || (Number(value) >= Number(setting.min) && Number(value) <= Number(setting.max));
}

const routes: Routes = {
  "/engineer/profile": {
    get: () => [200, data.profile],
    put: ({ body }) => {
      if (body.first_name.length > 80) return refuse(422, "PROFILE_BAD_VALUE", { field: "first_name", example: "مهندس" });
      const said = [body.first_name, body.last_name, body.position, body.company].every((text) => text.trim() !== "");
      data.profile = { ...body, complete: said && body.org_type !== null && body.country !== null && body.currency !== null };
      return [200, data.profile];
    },
  },
  "/engineer/lessons": { get: () => [200, data.lessons] },
  "/engineer/lessons/{lesson_id}": {
    patch: ({ path, body }) => {
      const lesson = data.lessons.lessons.find((it) => it.id === path.lesson_id);
      if (!lesson) return refuse(404, "ENGINEER_LESSON_NOT_FOUND");
      lesson.text = body.text;
      publish("general", { type: "lessons" });
      return [200, lesson];
    },
    delete: ({ path }) => {
      const kept = data.lessons.lessons.filter((it) => it.id !== path.lesson_id);
      if (kept.length === data.lessons.lessons.length) return refuse(404, "ENGINEER_LESSON_NOT_FOUND");
      data.lessons.lessons = kept;
      publish("general", { type: "lessons" });
      return [200, UNDO];
    },
  },
  "/home": { get: () => [200, data.home] },
  "/projects/{project_id}/tender": {
    // It answers for a closed tender too, from its row.
    get: ({ path: { project_id: id } }) => missing(id) ?? [200, tenderOf(id)],
  },
  "/projects/{project_id}/plan": { get: ({ path: { project_id: id } }) => closed(id) ?? [200, { plan: planOf(id) }] },
  "/projects/{project_id}/plan/request": {
    post: ({ path: { project_id: id } }) => closed(id) ?? (planOf(id) ? refuse(409, "PLAN_EXISTS") : [202, { brief_id: newId() }]),
  },
  "/projects/{project_id}/plan/approve": {
    post: ({ path: { project_id: id }, body }) => {
      const refused = closed(id);
      if (refused) return refused;
      const plan = planOf(id);
      if (!plan) return refuse(404, "PLAN_NOT_FOUND");
      if (body.version !== plan.version) return refuse(409, "PLAN_CHANGED", { field: "version" });
      if (plan.status === "proposed") {
        plan.status = "approved";
        plan.approved_at = now();
        plan.stages[0]!.status = "now"; // the driver starts the first stage
        for (const member of data[`team_members:${id}`]!.members) member.proposed = false; // the team is approved with it
        settle(id, plan.id, "plan");
        publish(id, { type: "plan", plan });
      }
      return [200, { plan }];
    },
  },
  "/projects/{project_id}/plan/stages/{stage_id}/approve": {
    post: ({ path: { project_id: id, stage_id }, body }) => {
      const refused = closed(id);
      if (refused) return refused;
      const plan = planOf(id);
      if (!plan) return refuse(404, "PLAN_NOT_FOUND");
      const at = plan.stages.findIndex((it) => it.id === stage_id);
      const stage = plan.stages[at];
      if (!stage) return refuse(404, "STAGE_NOT_FOUND");
      if (body.version !== plan.version) return refuse(409, "PLAN_CHANGED", { field: "version" });
      if (stage.status === "approved") return [200, { plan }];
      if (stage.status !== "waiting_engineer") return refuse(409, "STAGE_NOT_WAITING");
      stage.status = "approved";
      const next = plan.stages[at + 1];
      if (next) next.status = "now"; // the driver starts the next stage
      settle(id, stage.id, "stage");
      publish(id, { type: "plan", plan });
      return [200, { plan }];
    },
  },
  "/projects/{project_id}/plan/change": {
    post: ({ path: { project_id: id }, body }) => {
      const refused = closed(id);
      if (refused) return refused;
      const plan = planOf(id);
      if (!plan) return refuse(404, "PLAN_NOT_FOUND");
      if (plan.change?.id !== body.change_id) return refuse(409, "PLAN_CHANGED", { field: "change_id" });
      // Accepted, the plan takes what the change says and keeps its own id, status and approval.
      const { submission_date, stages, team, expected_cost_usd, expected_minutes, cost_basis, paid } = plan.change;
      const accepted = { submission_date, stages, team, expected_cost_usd, expected_minutes, cost_basis, paid, version: plan.version + 1 };
      const next: S["TenderPlan"] = { ...plan, ...(body.accept ? accepted : {}), change: null };
      data[`plan:${id}`] = { plan: next };
      settle(id, plan.id, "plan_change");
      publish(id, { type: "plan", plan: next });
      return [200, { plan: next }];
    },
  },
  "/projects/{project_id}/findings": {
    get: ({ path: { project_id: id } }) => closed(id) ?? [200, data[`findings:${id}`] ?? { findings: [] }],
  },
  "/projects/{project_id}/findings/{finding_id}/decide": {
    post: ({ path: { project_id: id, finding_id }, body }) => {
      const refused = closed(id);
      if (refused) return refused;
      const findings = data[`findings:${id}`]?.findings ?? [];
      const finding = findings.find((it) => it.id === finding_id);
      if (!finding) return refuse(404, "FINDING_NOT_FOUND");
      if (finding.status === "settled") return finding.chosen === body.choice ? [200, finding] : refuse(409, "FINDING_SETTLED");
      if (finding.status !== "raised") return refuse(409, "FINDING_NOT_RAISED");
      const note = finding.note;
      finding.status = "settled";
      finding.chosen = body.choice;
      finding.note = null;
      finding.settled_at = now();
      for (const message of data[`room:${id}`]?.messages ?? []) {
        if (message.raised?.id !== finding.id) continue;
        message.raised.answered = true;
        publish(id, { type: "room", message });
      }
      settle(id, finding.id, "decision");
      publish(id, { type: "finding", finding });
      const next = findings.find((it) => it.status === "queued"); // one decision waits at a time: the next is raised
      if (next) {
        next.status = "raised";
        next.note = note;
        wait(id, next.id, "decision", next.title);
        publish(id, { type: "finding", finding: next });
      }
      return [200, finding];
    },
  },
  "/projects/{project_id}/members": { get: ({ path: { project_id: id } }) => closed(id) ?? [200, data[`team_members:${id}`]!] },
  "/team/members": { get: () => [200, data.members] },
  "/projects/{project_id}/room": {
    // Newest first. The cursor is the id of the last message of the page before.
    get: ({ path: { project_id: id }, query }) => {
      const refused = closed(id);
      if (refused) return refused;
      const messages = data[`room:${id}`]?.messages ?? [];
      const cursor = query.get("cursor");
      const start = cursor ? messages.findIndex((it) => it.id === cursor) + 1 : 0;
      if (cursor && start === 0) return refuse(422, "ROOM_CURSOR_INVALID", { field: "cursor" });
      const page = messages.slice(start, start + Number(query.get("limit") ?? 50));
      return [200, { messages: page, next_cursor: start + page.length < messages.length ? page.at(-1)!.id : null }];
    },
    post: ({ path: { project_id: id }, body }) => {
      const refused = closed(id);
      if (refused) return refused;
      if (body.text.trim() === "") return refuse(422, "ROOM_EMPTY", { field: "text" });
      const message: S["RoomMessage"] = { id: newId(), from_id: "engineer", to_id: "team", text: body.text, sources: [], at: now(), raised: null };
      (data[`room:${id}`] ??= { messages: [], next_cursor: null }).messages.unshift(message);
      publish(id, { type: "room", message });
      return [201, message];
    },
  },
  "/setup/parts": { get: () => [200, data.setup] },
  "/setup/parts/retry": {
    post: () => {
      for (const part of data.setup.parts) {
        if (part.state !== "failed") continue;
        part.state = "queued";
        part.reason = null;
        publish("general", { type: "setup", setup: data.setup });
      }
      return [200, data.setup];
    },
  },
  "/settings": { get: () => [200, data.settings] },
  "/settings/{key}": {
    patch: ({ path, body: { value } }) => {
      const setting = data.settings.settings.find((it) => it.key === path.key);
      if (!setting) return refuse(404, "SETTING_NOT_FOUND");
      if (setting.control === "toggle") {
        if (typeof value !== "boolean") return refuse(422, "SETTING_BAD_VALUE", { field: "value" });
        setting.value = value;
      } else if (typeof value !== "string" || !fits(setting, value)) {
        return setting.control === "money"
          ? refuse(422, "NUMBER_NOT_EXACT", { field: "value", example: "50" })
          : refuse(422, "SETTING_BAD_VALUE", { field: "value", example: setting.recommended });
      } else setting.value = value;
      setting.at_recommended = setting.value === setting.recommended;
      publish("general", { type: "setting", setting });
      return [200, setting];
    },
  },
  "/settings/ai/connect": {
    // The provider is read from the key's own form, and the key is never in an answer.
    post: ({ body: { key } }) => {
      if (!key.startsWith("sk-ant-")) return refuse(422, "KEY_NOT_RECOGNISED", { field: "key" });
      const again = ai.keys.has(key);
      ai.keys.add(key);
      ai.linked = true;
      return again ? [200, data.ai_link] : [201, data.ai_link];
    },
  },
  "/settings/ai/links/{link_id}": {
    delete: ({ path }) => {
      if (!ai.linked || path.link_id !== data.ai_link.id) return refuse(404, "AI_LINK_NOT_FOUND");
      ai.linked = false;
      return [200, UNDO];
    },
  },
  "/briefs/{brief_id}/retry": { post: () => refuse(404, "BRIEF_NOT_FOUND") }, // no sample Brief has failed or was stopped
};

const API = "*/api"; // any origin: the screen calls a path, and msw sees it under the page's address
type Answer = (call: { path: unknown; query: URLSearchParams; body: unknown }) => [number, object];
/** Every Phase 1 route, and the activity stream, as msw handlers. */
export const contractRoutes = [
  ...Object.entries(routes).flatMap(([path, methods]) =>
    Object.entries(methods).map(([method, answer]) =>
      http[method as "get" | "put" | "post" | "patch" | "delete"](`${API}${path.replace(/\{(\w+)\}/g, ":$1")}`, async ({ request, params }) => {
        const text = await request.text();
        const body = text ? JSON.parse(text) : undefined;
        const [status, reply] = (answer as Answer)({ path: params, query: new URL(request.url).searchParams, body });
        return HttpResponse.json(reply, { status });
      }),
    ),
  ),
  activity,
];
