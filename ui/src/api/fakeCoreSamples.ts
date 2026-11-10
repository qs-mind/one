// The fake core's memory: samples.json held for one test, and how a tender moves when the engineer answers. A test
// imports fakeCore.ts, which hands on what it needs from here. NEVER import this from application code.
//
// samples.json is the contract's sample set: every name says it is a sample in both languages, no person is named and
// the numbers add up. Its keys are `<shape>`, `<shape>:<project id>`, and `…:<name>` for another scenario of a route.
import type { Schemas as S } from "./client";
import { publish } from "./fakeCoreLive";
import raw from "./samples.json?raw";

const tender = (n: number) => "5a" + String(n).padStart(30, "0");
/** The sample tenders: P1 waits for its plan's approval; P2 has an approved plan, a decision and a Suggested change
 * waiting; P3 is Confidential with no plan; P4 is finished and closed; P5 is being read; P6 cannot be read. */
export const P1 = tender(1), P2 = tender(2), P3 = tender(3), P4 = tender(4), P5 = tender(5), P6 = tender(6);

/** A sample of a route by its name in samples.json: the first one ("home") or another scenario ("home:empty"). */
export type Scenario =
  | "home" | "home:empty" | "home:no_ai" | "home:cut_off" | "profile" | "profile:incomplete"
  | "setup" | "setup:downloading" | "setup:offline" | "setup:failed" | "setup:unavailable"
  | `tender:${string}:blocked`;

type Samples = {
  profile: S["Profile"]; lessons: S["Lessons"]; home: S["Home"]; members: S["Members"];
  setup: S["SetupState"]; settings: S["Settings"]; ai_link: S["AiLink"];
  [plan: `plan:${string}`]: S["PlanView"];
  [findings: `findings:${string}`]: S["Findings"];
  [team: `team_members:${string}`]: S["TeamMembers"];
  [room: `room:${string}`]: S["RoomPage"];
};

// The core's own words where it has them today; the others stand in until the job that builds the route writes them.
const WORDS = {
  PROJECT_NOT_FOUND: { en: "This project is not on this computer.", ar: "المشروع ده مش موجود على الجهاز ده." },
  PROJECT_NOT_OPEN: { en: "Open the project first.", ar: "افتح المشروع الأول." },
  BRIEF_NOT_FOUND: { en: "This Brief is not on this computer, or it is already finished.", ar: "التكليف ده مش على الجهاز ده، أو خلص خلاص." },
  NUMBER_NOT_EXACT: {
    en: "Send the number as text: digits and one decimal point, no thousands separators, e.g. 39850.50.",
    ar: "ابعت الرقم كنص: أرقام وعلامة عشرية واحدة، من غير فواصل آلاف، زي 39850.50.",
  },
  PLAN_EXISTS: { en: "This tender already has a plan.", ar: "العطاء ده ليه خطة بالفعل." },
  PLAN_NOT_FOUND: { en: "This tender has no plan yet.", ar: "العطاء ده لسه مالوش خطة." },
  PLAN_CHANGED: { en: "The plan changed while you were reading it. Read it again, then answer.", ar: "الخطة اتغيرت وإنت بتقراها. اقراها تاني وبعدين رد." },
  STAGE_NOT_FOUND: { en: "This stage is not in the plan.", ar: "المرحلة دي مش في الخطة." },
  STAGE_NOT_WAITING: { en: "This stage is not ready for your sign-off yet.", ar: "المرحلة دي لسه مش جاهزة لاعتمادك." },
  FINDING_NOT_FOUND: { en: "This Finding is not in this tender.", ar: "الملاحظة دي مش في العطاء ده." },
  FINDING_NOT_RAISED: { en: "This Finding does not wait for your decision.", ar: "الملاحظة دي مش مستنية قرارك." },
  FINDING_SETTLED: { en: "This Finding was settled another way.", ar: "الملاحظة دي اتحسمت بشكل تاني." },
  ROOM_EMPTY: { en: "Write a message first.", ar: "اكتب رسالة الأول." },
  ROOM_CURSOR_INVALID: { en: "This place in the team room is not known. Open the room again.", ar: "المكان ده في غرفة الفريق مش معروف. افتح الغرفة تاني." },
  PROFILE_BAD_VALUE: { en: "This is too long. Write 80 characters at most.", ar: "ده طويل زيادة. اكتب 80 حرف بالكتير." },
  ENGINEER_LESSON_NOT_FOUND: { en: "This lesson is not kept any more.", ar: "الدرس ده مش محفوظ دلوقتي." },
  SETTING_NOT_FOUND: { en: "ONE has no setting with this name.", ar: "مفيش إعداد بالاسم ده في ONE." },
  SETTING_BAD_VALUE: { en: "This value does not fit this setting.", ar: "القيمة دي مش مناسبة للإعداد ده." },
  KEY_NOT_RECOGNISED: { en: "ONE does not recognise this key. Check that you copied all of it.", ar: "ONE مش عارف المفتاح ده. اتأكد إنك نسخته كله." },
  AI_LINK_NOT_FOUND: { en: "This AI provider is not connected.", ar: "مزوّد الذكاء الاصطناعي ده مش متوصّل." },
} satisfies Record<string, S["Text"]>;
// ONE's words for a stage that asks for sign-off, and for a tender that waits, before the title of what it waits for.
const STAGE_WAITS: S["Text"] = { en: "Sign off the stage", ar: "اعتمد المرحلة" };
const WAITS = {
  decision: { en: "Waiting for your decision: ", ar: "مستني قرارك: " },
  stage: { en: "Waiting for your sign-off: ", ar: "مستني اعتمادك: " },
};

/** The samples as they stand now. */
export let data: Samples;
/** The sample AI provider: whether it is connected, and the keys pasted so far (to know one that comes again). */
export const ai = { linked: true, keys: new Set<string>() };
let made = 0; // ids given since the last reset

/** Puts every sample back as it was. */
export function resetFakeCore(): void {
  data = JSON.parse(raw) as Samples;
  ai.linked = true;
  ai.keys.clear();
  made = 0;
}
resetFakeCore();

export const newId = () => "5a" + (0x8000 + ++made).toString(16).padStart(30, "0");
/** This moment as the core writes one. */
export const now = () => new Date().toISOString().replace("Z", "000+00:00");
/** A refusal as a route answers it: its status, the words, and what stands beside them (`field`, `example`). */
export const refuse = <Status extends number>(status: Status, words: keyof typeof WORDS, more: Omit<S["Refusal"], "error"> = {}) =>
  [status, { error: WORDS[words], ...more }] as [Status, S["Refusal"]];

export const rowOf = (id: string) => data.home.tenders.find((row) => row.project_id === id);
export const planOf = (id: string) => data[`plan:${id}`]?.plan ?? null;
/** A tender's header and what waits in it: its Home row, and its own waiting items. */
export const tenderOf = (id: string): S["TenderView"] => ({ tender: rowOf(id)!, waiting: data.home.waiting.filter((item) => item.project_id === id) });

/** The refusal for a tender Home does not list: one ONE cannot read, or one it does not know. */
export function missing(id: string) {
  const unreadable = data.home.unreadable.find((it) => it.project_id === id);
  if (unreadable) return [409, { error: unreadable.reason }] as [409, S["Refusal"]];
  return rowOf(id) ? undefined : refuse(404, "PROJECT_NOT_FOUND");
}
/** The refusal for a tender whose content cannot be read or changed now. An open tender has a team; P4 is closed. */
export const closed = (id: string) => missing(id) ?? (data[`team_members:${id}`] ? undefined : refuse(409, "PROJECT_NOT_OPEN"));

/** After a change in a tender: its row, its Lead and Home say what its plan and its waiting items now say, and the
 * live channel says so (`tender`, `member`, `home`). */
function refresh(id: string): void {
  const { tender: row, waiting } = tenderOf(id);
  const plan = planOf(id);
  const blocking = waiting.find((item) => item.blocking);
  row.waiting = waiting.length;
  if (plan) {
    row.stages = plan.stages.map((stage) => stage.status);
    row.stage = plan.stages.find((stage) => stage.status === "now" || stage.status === "waiting_engineer")?.title ?? null;
    // A Suggested change always shows the stages as they stand now.
    for (const next of plan.change?.stages ?? []) {
      const stage = plan.stages.find((it) => it.id === next.id);
      if (!stage) continue;
      next.status = stage.status;
      next.result = stage.result;
      next.outputs = stage.outputs;
    }
  }
  row.state = blocking ? "waiting" : plan?.stages.every((stage) => stage.status === "approved") ? "finished" : "working";
  if (!blocking) row.line = null;
  else if (blocking.kind === "decision" || blocking.kind === "stage") {
    const title = blocking.kind === "stage" ? plan!.stages.find((stage) => stage.id === blocking.id)!.title : blocking.title;
    row.line = { en: WAITS[blocking.kind].en + title.en, ar: WAITS[blocking.kind].ar + title.ar };
  }
  const lead = data[`team_members:${id}`]?.members.find((member) => member.role === "lead");
  if (lead) {
    lead.state = blocking ? "waiting" : row.state === "working" ? "working" : "idle";
    lead.doing = row.line;
    publish(id, { type: "member", member: lead });
  }
  data.home.summary = null; // the Lead writes it again: a summary never disagrees with the lists under it
  publish(id, { type: "tender", tender: row, waiting });
  publish("general", { type: "home" });
}

/** The engineer answered what waited: it leaves the list, and the tender moves on. */
export function settle(projectId: string, id: string, kind: S["WaitingItem"]["kind"]): void {
  data.home.waiting = data.home.waiting.filter((item) => !(item.id === id && item.kind === kind));
  refresh(projectId);
}

/** Something new waits for the engineer in a tender, and stops its work. */
export function wait(projectId: string, id: string, kind: "decision" | "stage", title: S["Text"]): void {
  data.home.waiting.push({ id, kind, project_id: projectId, title, text: null, since: now(), blocking: true });
  refresh(projectId);
}

/** Puts a sample of a route in place: scenario("home:empty"), scenario("setup:failed"), then scenario("setup"). A screen
 * that listens is told, as when the core changes it by itself (`home`, `tender`, `setup`). */
export function scenario(name: Scenario): void {
  const fresh = JSON.parse(raw) as Record<string, unknown>;
  const shape = name.split(":")[0]!;
  if (shape === "tender") {
    const { tender } = fresh[name] as S["TenderView"];
    data.home.tenders = data.home.tenders.map((row) => (row.project_id === tender.project_id ? tender : row));
    publish(tender.project_id, { type: "tender", ...tenderOf(tender.project_id) });
  } else Object.assign(data, { [shape]: fresh[name] });
  if (shape === "setup") publish("general", { type: "setup", setup: data.setup });
  if (shape === "home" || shape === "tender") publish("general", { type: "home" });
}

/** What the core does by itself: the work of the stage that is `now` ends and asks for the engineer's sign-off. */
export function stageEnds(projectId: string): void {
  const stage = planOf(projectId)?.stages.find((it) => it.status === "now");
  const undecided = data[`findings:${projectId}`]?.findings.some((it) => it.status === "raised" || it.status === "queued");
  if (!stage || undecided) throw new Error("No stage can end here: none is running, or a Finding still waits for a decision.");
  stage.status = "waiting_engineer";
  for (const output of stage.outputs) if (output.kind === "deliverable" || output.kind === "file") output.id ??= newId();
  wait(projectId, stage.id, "stage", STAGE_WAITS);
  publish(projectId, { type: "plan", plan: planOf(projectId) });
}
