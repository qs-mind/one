// Another chat's work on the real app and core, with the bench's fake AI: a project's Brief waits for the engineer
// while they are in the General chat, and the top bar's mark and the project's row say so; answered from outside,
// it ends, a quiet notice at the chat's foot says so, and Open goes there. The projects list is compact: New project is
// one row that turns into a field (walk.createProject). Screenshots: test-results/bench/shots.
import { fill, texts } from "../src/i18n";
import { expect, test } from "./bench";

type Part = { type: string; id?: string; data?: { status?: string; options?: string[]; payload?: { questions: { id: string; options?: string[] }[] } } };

test("another chat waits, then finishes, in Arabic", async ({ walk, page }) => {
  await walk.start("ar");
  await walk.createProject("test");
  await walk.shot("activity-project-created");
  await page.getByRole("textbox", { name: walk.w.message }).fill("bench:question عايز أعرف محتاج مني إيه بالظبط في المشروع ده"); // more Arabic letters than Latin: an Arabic Brief
  await page.getByRole("button", { name: walk.w.send, exact: true }).click();
  await expect(page.locator("[data-waiting]").first()).toBeVisible();

  const top = page.locator('[data-region="topbar"]');
  const list = page.getByRole("region", { name: texts.projects.ar });
  await top.getByRole("button", { name: /^test/ }).click();
  await walk.shot("activity-picker");
  await list.getByRole("button", { name: new RegExp(texts.generalChat.ar) }).click();

  const elsewhere = (state: keyof typeof texts) => top.getByRole("img", { name: fill(texts.activityElsewhere.ar, { state: texts[state].ar }) });
  await expect(elsewhere("activityWaiting")).toBeVisible();
  await walk.shot("activity-topbar-waiting");
  await top.getByRole("button", { name: new RegExp(texts.generalChat.ar) }).click();
  await expect(list.getByRole("button", { name: `test ${texts.activityWaiting.ar}` })).toBeVisible();
  await walk.shot("activity-picker-waiting");
  await page.keyboard.press("Escape");
  await expect(list).toHaveCount(0);

  // answered from outside its chat, the Brief goes on and ends: the notice says so
  const { messages } = (await (await page.request.get(`/api/chat/${walk.projectId}/messages`)).json()) as { messages: { parts: Part[] }[] };
  const card = messages.flatMap((m) => m.parts).find((p) => p.type === "data-card" && p.data?.status === "pending");
  expect(card, "the question card waits in the core").toBeTruthy();
  const answers = Object.fromEntries(card!.data!.payload!.questions.map((q) => [q.id, q.options?.[0] ?? "عينة"]));
  const answered = await page.request.post(`/api/cards/${card!.id}`, { data: { choice: card!.data!.options![0], answers } });
  expect(answered.status()).toBe(204);
  const notice = page.getByRole("region", { name: fill(texts.activityNoticeDone.ar, { name: "⁨test⁩" }) });
  await expect(notice).toBeVisible();
  await expect(elsewhere("activityDone")).toBeVisible();
  await walk.shot("activity-notice-done");

  await notice.getByRole("button", { name: texts.activityOpen.ar }).click();
  await expect(top.getByRole("button", { name: /^test/ })).toBeVisible();
  await expect(notice).toHaveCount(0);
  await expect(top.getByRole("img")).toHaveCount(0); // seen: the done mark is gone
  await walk.shot("activity-opened");
});
