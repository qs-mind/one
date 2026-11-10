// The fake core keeps state for one test: what a screen sees after the engineer presses a button.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { client } from "./client";
import { P1, P2, P3, P4, P5, P6, resetFakeCore, scenario, stageEnds, startFakeCore } from "./fakeCore";

const samples = JSON.parse(readFileSync(join(__dirname, "samples.json"), "utf8"));
const id = (tail: string) => "5a" + tail.padStart(30, "0");
const at = (project_id: string) => ({ params: { path: { project_id } } });

const home = async () => (await client.GET("/home")).data!;
const tender = async (project: string) => (await client.GET("/projects/{project_id}/tender", at(project))).data!;
const plan = async (project: string) => (await client.GET("/projects/{project_id}/plan", at(project))).data!.plan!;
const approvePlan = (project: string, version: number) => client.POST("/projects/{project_id}/plan/approve", { ...at(project), body: { version } });
const approveStage = (project: string, stage_id: string, version = 1) =>
  client.POST("/projects/{project_id}/plan/stages/{stage_id}/approve", { params: { path: { project_id: project, stage_id } }, body: { version } });
const decide = (finding_id: string, choice: 0 | 1) =>
  client.POST("/projects/{project_id}/findings/{finding_id}/decide", { params: { path: { project_id: P2, finding_id } }, body: { choice } });
const patch = (key: string, value: string | boolean) => client.PATCH("/settings/{key}", { params: { path: { key } }, body: { value } });

/** The numbers add up: each row counts its own waiting items, shows its plan's stages, and is its tender's header. */
async function addsUp() {
  const { tenders, waiting } = await home();
  for (const row of tenders) {
    const mine = waiting.filter((item) => item.project_id === row.project_id);
    expect(row.waiting).toBe(mine.length);
    expect(await tender(row.project_id)).toEqual({ tender: row, waiting: mine });
    if ([P1, P2].includes(row.project_id)) expect(row.stages).toEqual((await plan(row.project_id)).stages.map((stage) => stage.status));
  }
}

startFakeCore();

describe("the samples as they are served", () => {
  it("a tender's header is its Home row and what waits in it", async () => {
    expect(await tender(P2)).toEqual(samples[`tender:${P2}`]);
    await addsUp();
  });

  it("a tender Home lists but that is closed answers its header only", async () => {
    expect((await tender(P4)).tender.state).toBe("finished");
    const refused = await client.GET("/projects/{project_id}/plan", at(P4));
    expect(refused.response.status).toBe(409);
    expect(refused.error).toEqual({ error: { en: "Open the project first.", ar: "افتح المشروع الأول." } });
  });

  it("a tender that cannot be read refuses with its reason, and an unknown one is not found", async () => {
    const unreadable = await client.GET("/projects/{project_id}/tender", at(P6));
    expect(unreadable.response.status).toBe(409);
    expect(unreadable.error).toEqual({ error: samples.home.unreadable[0].reason });
    expect((await client.GET("/projects/{project_id}/members", at(id("77")))).response.status).toBe(404);
  });

  it("a tender with no sample of its own has no plan, no Findings and an empty room", async () => {
    expect((await client.GET("/projects/{project_id}/plan", at(P5))).data).toEqual({ plan: null });
    expect((await client.GET("/projects/{project_id}/findings", at(P5))).data).toEqual({ findings: [] });
    expect((await client.GET("/projects/{project_id}/room", at(P3))).data).toEqual({ messages: [], next_cursor: null });
  });

  it("a scenario puts another sample of a route in place", async () => {
    scenario("home:no_ai");
    expect((await home()).blocked?.fix).toBe("ai");
    scenario("home");
    scenario(`tender:${P3}:blocked`);
    expect((await tender(P3)).tender.blocked?.fix).toBe("ai");
    expect((await home()).tenders.find((row) => row.project_id === P3)?.blocked?.fix).toBe("ai");
    scenario("profile:incomplete");
    expect((await client.GET("/engineer/profile")).data).toEqual(samples["profile:incomplete"]);
  });

  it("a reset puts every sample back", async () => {
    await approvePlan(P1, 1);
    await patch("look.theme", "dark");
    scenario("home:empty");
    resetFakeCore();
    expect(await home()).toEqual(samples.home);
    expect(await plan(P1)).toEqual(samples[`plan:${P1}`].plan);
    expect((await client.GET("/settings")).data).toEqual(samples.settings);
  });
});

describe("the tender plan", () => {
  it("approving the plan starts its first stage, approves its team and clears what waited", async () => {
    const stale = await approvePlan(P1, 2);
    expect(stale.response.status).toBe(409);
    expect(stale.error).toMatchObject({ field: "version" });

    const approved = (await approvePlan(P1, 1)).data!.plan!;
    expect(approved).toMatchObject({ status: "approved", version: 1 });
    expect(approved.approved_at).not.toBeNull();
    expect(approved.stages.map((stage) => stage.status)).toEqual(["now", "pending", "pending", "pending", "pending", "pending", "pending"]);

    const { tender: row, waiting } = await tender(P1);
    expect(row).toMatchObject({ state: "working", waiting: 0, line: null, stage: approved.stages[0]!.title });
    expect(waiting).toEqual([]);
    expect((await home()).summary).toBeNull(); // it is written again: it never disagrees with the lists
    const { members } = (await client.GET("/projects/{project_id}/members", at(P1))).data!;
    expect(members.filter((member) => member.proposed)).toEqual([]);
    expect(members.find((member) => member.role === "lead")).toMatchObject({ state: "working", doing: null });
    await addsUp();

    expect((await approvePlan(P1, 1)).data!.plan).toEqual(await plan(P1)); // safe to repeat
  });

  it("a stage whose work ended waits for sign-off, and signing it off starts the next", async () => {
    await approvePlan(P1, 1);
    const [first, second] = (await plan(P1)).stages;
    expect((await approveStage(P1, first!.id)).response.status).toBe(409); // it is still running

    stageEnds(P1);
    expect((await plan(P1)).stages[0]!.status).toBe("waiting_engineer");
    const waits = await tender(P1);
    expect(waits.tender).toMatchObject({ state: "waiting", waiting: 1 });
    expect(waits.tender.line?.en).toBe(`Waiting for your sign-off: ${first!.title.en}`);
    expect(waits.waiting).toMatchObject([{ id: first!.id, kind: "stage", blocking: true }]);
    await addsUp();

    const signed = (await approveStage(P1, first!.id)).data!.plan!;
    expect(signed.stages.slice(0, 3).map((stage) => stage.status)).toEqual(["approved", "now", "pending"]);
    expect(await tender(P1)).toMatchObject({ tender: { state: "working", stage: second!.title, waiting: 0 }, waiting: [] });
    await addsUp();

    // The second stage hands over a Deliverable, which exists once its work has ended.
    expect(second!.outputs[0]!.id).toBeNull();
    stageEnds(P1);
    expect((await plan(P1)).stages[1]!.outputs[0]!.id).toMatch(/^5a[0-9a-f]{30}$/);
  });

  it("a stage that is running, approved or unknown is answered as the contract says", async () => {
    expect((await approveStage(P2, id("1204"))).response.status).toBe(409); // now
    expect((await approveStage(P2, id("1203"))).data).toEqual(samples[`plan:${P2}`]); // approved already: unchanged
    expect((await approveStage(P2, id("1299"))).response.status).toBe(404);
    expect((await approveStage(P2, id("1203"), 7)).error).toMatchObject({ field: "version" });
    expect(() => stageEnds(P2)).toThrow("a Finding still waits"); // the stage stays `now` while a decision waits
  });

  it("an accepted Suggested change becomes the plan", async () => {
    const change = samples[`plan:${P2}`].plan.change;
    const other = await client.POST("/projects/{project_id}/plan/change", { ...at(P2), body: { change_id: id("a9"), accept: true } });
    expect(other.response.status).toBe(409);
    expect(other.error).toMatchObject({ field: "change_id" });

    const accepted = (await client.POST("/projects/{project_id}/plan/change", { ...at(P2), body: { change_id: change.id, accept: true } })).data!.plan!;
    expect(accepted).toMatchObject({ version: 2, status: "approved", submission_date: "2026-11-16", expected_cost_usd: "3.10", change: null });
    expect(accepted.stages).toEqual(change.stages);
    expect(accepted.submission_source).toEqual(change.submission_source); // the date and where it was read
    expect(await plan(P2)).toEqual(accepted);
    const waits = await tender(P2);
    expect(waits.waiting.map((item) => item.kind)).toEqual(["decision"]); // the change left; the decision still stops work
    expect(waits.tender).toMatchObject({ state: "waiting", waiting: 1, line: samples.home.tenders[0].line });
    await addsUp();
  });

  it("a rejected Suggested change leaves the plan as it was", async () => {
    const before = samples[`plan:${P2}`].plan;
    const rejected = (await client.POST("/projects/{project_id}/plan/change", { ...at(P2), body: { change_id: before.change.id, accept: false } })).data!.plan!;
    expect(rejected).toEqual({ ...before, change: null });
    expect((await tender(P2)).waiting.map((item) => item.kind)).toEqual(["decision"]);
  });

  it("a plan can be asked for only where there is none", async () => {
    const started = await client.POST("/projects/{project_id}/plan/request", at(P3));
    expect(started.response.status).toBe(202);
    expect(started.data?.brief_id).toMatch(/^5a[0-9a-f]{30}$/);
    expect((await client.POST("/projects/{project_id}/plan/request", at(P1))).response.status).toBe(409);
  });
});

describe("Findings", () => {
  it("a decision settles the Finding and raises the one queued behind it", async () => {
    const settled = (await decide(id("9002"), 0)).data!;
    expect(settled).toMatchObject({ status: "settled", chosen: 0, note: null });
    expect(settled.settled_at).not.toBeNull();

    const { findings } = (await client.GET("/projects/{project_id}/findings", at(P2))).data!;
    expect(findings.map((finding) => finding.status)).toEqual(["settled", "settled", "raised", "open", "settled"]);
    const next = findings[2]!;
    expect(next.note).toEqual({ en: "Waiting for your decision", ar: "مستني قرارك" });
    const waits = await tender(P2);
    expect(waits.waiting.map((item) => [item.kind, item.id])).toEqual([["plan_change", id("a2")], ["decision", next.id]]);
    expect(waits.tender.line).toEqual({ en: `Waiting for your decision: ${next.title.en}`, ar: `مستني قرارك: ${next.title.ar}` });
    const { messages } = (await client.GET("/projects/{project_id}/room", at(P2))).data!;
    expect(messages[0]!.raised).toEqual({ id: id("9002"), answered: true });
    await addsUp();

    await decide(next.id, 1);
    expect(await tender(P2)).toMatchObject({ tender: { state: "working", waiting: 1 }, waiting: [{ kind: "plan_change" }] });
    stageEnds(P2); // no decision waits any more, so the stage's work can end
    expect((await plan(P2)).change!.stages[3]!.status).toBe("waiting_engineer"); // the Suggested change shows the stage as it stands
    await addsUp();
  });

  it("only the raised Finding can be decided, and a settled one keeps its answer", async () => {
    expect((await decide(id("9003"), 0)).response.status).toBe(409); // open
    expect((await decide(id("9004"), 0)).response.status).toBe(409); // queued
    expect((await decide(id("9001"), 1)).response.status).toBe(409); // settled with the other option
    expect((await decide(id("9001"), 0)).response.status).toBe(200); // the same choice again
    expect((await decide(id("9099"), 0)).response.status).toBe(404);
  });
});

describe("the team room", () => {
  it("the engineer's message is stored and comes first", async () => {
    const text = "راجعوا بند 3/05 قبل التسعير - عينة (sample)";
    const posted = await client.POST("/projects/{project_id}/room", { ...at(P2), body: { text } });
    expect(posted.response.status).toBe(201);
    expect(posted.data).toMatchObject({ from_id: "engineer", to_id: "team", text, sources: [], raised: null });
    const { messages } = (await client.GET("/projects/{project_id}/room", at(P2))).data!;
    expect(messages).toHaveLength(7);
    expect(messages[0]).toEqual(posted.data);

    const blank = await client.POST("/projects/{project_id}/room", { ...at(P2), body: { text: " " } });
    expect(blank.response.status).toBe(422);
    expect(blank.error).toMatchObject({ field: "text" });
  });

  it("the room is read a page at a time, newest first", async () => {
    const page = (cursor?: string) => client.GET("/projects/{project_id}/room", { params: { path: { project_id: P2 }, query: { limit: 2, cursor } } });
    const first = (await page()).data!;
    const second = (await page(first.next_cursor!)).data!;
    const third = (await page(second.next_cursor!)).data!;
    expect([first, second, third].flatMap((it) => it.messages)).toEqual(samples[`room:${P2}`].messages);
    expect(third.next_cursor).toBeNull();
    const lost = await page("nowhere");
    expect(lost.response.status).toBe(422);
    expect(lost.error).toMatchObject({ field: "cursor" });
  });
});

describe("Settings and the engineer", () => {
  it("a setting is saved at once and says whether it is the recommended value", async () => {
    expect((await patch("caps.month_usd", "150")).data).toMatchObject({ value: "150", at_recommended: true });
    expect((await patch("caps.month_usd", "80.50")).data).toMatchObject({ value: "80.50", at_recommended: false });
    expect((await patch("privacy.usage_stats", true)).data).toMatchObject({ value: true, at_recommended: false });
    expect((await patch("look.zoom", "1.2")).data).toMatchObject({ value: "1.2" });
    const { settings } = (await client.GET("/settings")).data!;
    expect(settings.find((setting) => setting.key === "caps.month_usd")?.value).toBe("80.50");
  });

  it("a value that does not fit is refused with the field and an example", async () => {
    const money = await patch("caps.month_usd", "abc");
    expect(money.response.status).toBe(422);
    expect(money.error).toMatchObject({ field: "value", example: "50" });
    expect((await patch("look.theme", "pink")).error).toMatchObject({ field: "value", example: "system" });
    expect((await patch("look.zoom", "3")).response.status).toBe(422);
    expect((await patch("privacy.usage_stats", "yes")).response.status).toBe(422);
    expect((await patch("look.colour", "red")).response.status).toBe(404);
    expect((await client.GET("/settings")).data).toEqual(samples.settings);
  });

  it("the profile is saved half-filled, and is complete when every field is said", async () => {
    const { complete: _complete, ...whole } = samples.profile;
    const half = await client.PUT("/engineer/profile", { body: { ...whole, company: " ", currency: null } });
    expect(half.data).toEqual({ ...whole, company: " ", currency: null, complete: false });
    expect((await client.PUT("/engineer/profile", { body: whole })).data?.complete).toBe(true);
    expect((await client.GET("/engineer/profile")).data).toEqual(samples.profile);

    const long = await client.PUT("/engineer/profile", { body: { ...whole, first_name: "م".repeat(81) } });
    expect(long.response.status).toBe(422);
    expect(long.error).toMatchObject({ field: "first_name" });
  });

  it("a lesson is changed, and removed with an Undo", async () => {
    const lesson_id = id("6001");
    const text = "بيقيس الخرسانة هندسي - عينة (sample)";
    expect((await client.PATCH("/engineer/lessons/{lesson_id}", { params: { path: { lesson_id } }, body: { text } })).data?.text).toBe(text);
    const removed = await client.DELETE("/engineer/lessons/{lesson_id}", { params: { path: { lesson_id } } });
    expect(removed.data).toEqual({ undo: id("d0"), window_ms: 6000 });
    expect((await client.GET("/engineer/lessons")).data!.lessons.map((lesson) => lesson.id)).toEqual([id("6002")]);
    expect((await client.DELETE("/engineer/lessons/{lesson_id}", { params: { path: { lesson_id } } })).response.status).toBe(404);
  });

  it("an AI provider is connected with a pasted key and disconnected with an Undo", async () => {
    const connect = (key: string) => client.POST("/settings/ai/connect", { body: { key } });
    const made = await connect("sk-ant-sample");
    expect([made.response.status, made.data]).toEqual([201, samples.ai_link]);
    expect((await connect("sk-ant-sample")).response.status).toBe(200); // that key was linked already
    const unknown = await connect("x");
    expect(unknown.response.status).toBe(422);
    expect(unknown.error).toMatchObject({ field: "key" });

    const unlink = (link_id: string) => client.DELETE("/settings/ai/links/{link_id}", { params: { path: { link_id } } });
    expect((await unlink("claude-code")).response.status).toBe(404);
    expect((await unlink("anthropic")).data).toEqual({ undo: id("d0"), window_ms: 6000 });
    expect((await unlink("anthropic")).response.status).toBe(404);
  });
});

describe("Automatic setup", () => {
  it("moves from downloading to ready", async () => {
    scenario("setup:downloading");
    const downloading = (await client.GET("/setup/parts")).data!;
    expect(downloading.ready).toBe(false);
    expect(downloading.parts.map((part) => [part.state, part.done_bytes])).toEqual([["downloading", 62000000], ["present", 28400000], ["queued", 0]]);
    scenario("setup");
    expect((await client.GET("/setup/parts")).data).toMatchObject({ ready: true, parts: [{ state: "present" }, { state: "present" }, { state: "present" }] });
  });

  it("a failed part is queued again by Retry", async () => {
    scenario("setup:failed");
    const failed = (await client.GET("/setup/parts")).data!;
    expect(failed.parts[2]).toMatchObject({ id: "dwg-reader", state: "failed", reason: { en: "The downloaded file was damaged three times in a row." } });
    const retried = (await client.POST("/setup/parts/retry")).data!;
    expect(retried).toEqual({ ready: false, parts: [failed.parts[0], failed.parts[1], { ...failed.parts[2], state: "queued", reason: null }] });
    expect((await client.POST("/setup/parts/retry")).data).toEqual(retried); // nothing failed: the same state
  });
});
