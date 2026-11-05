// The facts beside a reply, from ONE's records (core: engine/truth.py): the tender day's weak model said «تم الانتهاء
// من تسعير كافة بنود المقايسة» over 8 priced items. The core sends the reply back once to be fixed (data-redo: the
// screen drops the words it replaces) and puts what its records hold beside the answer (data-facts).
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { setCurrentProject } from "../records/project";
import { App } from "../shell/App";
import { core, streamed } from "../shell/testing";
import { withoutRedone } from "./parts/FactsLine";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("../shell/testing")).CanvasStandIn }));

const claimed = "تم الانتهاء من تسعير كافة بنود المقايسة.";
const fixed = "اتسعّر 8 بنود من 325، والباقي لسه.";
const answer = (redo: boolean) => [
  { type: "start", messageId: "m1" },
  { type: "start-step" },
  { type: "text-start", id: "t1" },
  { type: "text-delta", id: "t1", delta: claimed },
  ...(redo ? [{ type: "data-redo", id: "b1", data: { from: 0, to: claimed.length } }] : []),
  { type: "text-delta", id: "t1", delta: fixed },
  { type: "text-end", id: "t1" },
  {
    type: "data-facts",
    id: "b1",
    data: {
      text: { en: "From ONE's records: 8 of 325 items priced · no Deliverable yet", ar: "من سجلات ONE: اتسعّر 8 من 325 بند · مفيش مخرج لسه" },
      flags: [{ en: "The reply says a Deliverable is ready; there is none yet.", ar: "الرد بيقول إن فيه مخرج جاهز، ومفيش مخرج لسه." }],
    },
  },
  { type: "data-status", id: "b1", data: { state: "done", step: null } },
  { type: "finish-step" },
  { type: "finish" },
];
const box = () => screen.findByRole("textbox", { name: texts.message.ar });

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: false, media: query, addEventListener() {}, removeEventListener() {} }));
});

describe("the facts beside a reply", () => {
  it("drops the words sent back and shows what the records hold", async () => {
    core({ routes: { "POST /api/chat": (init) => streamed(answer(true), init) } });
    const user = userEvent.setup();
    render(<App />);
    await user.type(await box(), "سعّر المقايسة{enter}");
    expect(await screen.findByText("من سجلات ONE: اتسعّر 8 من 325 بند · مفيش مخرج لسه")).toBeInTheDocument();
    expect(screen.getByText("الرد بيقول إن فيه مخرج جاهز، ومفيش مخرج لسه.")).toHaveAttribute("role", "status");
    expect(screen.getByText(fixed)).toBeInTheDocument();
    expect(screen.queryByText(new RegExp(claimed))).toBeNull();
  });

  it("cuts in the reply's own units", () => {
    expect(withoutRedone("أ😀ب", { from: 1, to: 3 })).toBe("أب");
    expect(withoutRedone("نص", undefined)).toBe("نص");
  });
});
