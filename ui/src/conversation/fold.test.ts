import { describe, expect, it } from "vitest";
import { fold } from "./fold";
import { briefState, livePlaces, isLive, liveProgress, type ThreadMessage } from "./parts";
import { planShape } from "./plan";
import { planProposed, planWithChange, sampleThread } from "./gallery/samples";

describe("fold", () => {
  it("keeps four lines or fewer whole", () => {
    expect(fold("one\ntwo\n\nthree\nfour")).toEqual({ head: "one\ntwo\n\nthree\nfour", rest: "" });
  });

  it("shows the first four lines with text and folds the rest", () => {
    expect(fold("a\n\nb\nc\nd\ne\nf")).toEqual({ head: "a\n\nb\nc\nd", rest: "e\nf" });
  });

  it("never cuts a fenced block or a table in two", () => {
    expect(fold("a\nb\nc\n```\nx\ny\n```\nafter")).toEqual({ head: "a\nb\nc\n```\nx\ny\n```", rest: "after" });
    expect(fold("a\nb\nc\n| h |\n|---|\n| 1 |\nafter").rest).toBe("after");
  });
});

describe("parts", () => {
  const thread = sampleThread("en");

  it("knows the newest Brief's state and what it does now", () => {
    expect(briefState(thread)).toBe("running");
    expect(liveProgress(thread)?.agent.en).toMatch(/Contracts engineer/);
    const done: ThreadMessage[] = [thread[0]!, thread[1]!];
    expect(briefState(done)).toBeNull();
    expect(liveProgress(done)).toBeNull();
  });

  it("makes only the last copy of a pointer part live", () => {
    const again: ThreadMessage = { ...thread[3]!, id: "b3-reply" };
    const messages = [...thread, again];
    const live = livePlaces(messages);
    const index = thread[3]!.parts.findIndex((p) => p.type === "data-plan");
    expect(isLive(live, thread[3]!, index)).toBe(false);
    expect(isLive(live, again, index)).toBe(true);
  });
});

describe("planShape", () => {
  it("counts stages and days and weighs each stage by its days", () => {
    const shape = planShape(planProposed.stages);
    expect(shape.count).toBe(7);
    expect(shape.days).toBe(12);
    expect(shape.bar.map((s) => s.weight)).toEqual([1, 1, 2, 2, 4, 1, 1]);
    expect(shape.current).toBeNull();
    expect(shape.allDone).toBe(false);
  });

  it("finds the stage that runs and maps each status to a segment", () => {
    const shape = planShape(planWithChange.stages);
    expect(shape.current?.step).toBe(4);
    expect(shape.bar.map((s) => s.state)).toEqual(["done", "done", "done", "now", "pending", "pending"]);
  });
});
