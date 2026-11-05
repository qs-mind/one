// Approvals that can't be pressed by mistake: one card open at a time, the rest in a short queue; an answer that costs
// money or can't be taken back needs a press-and-hold (the core says which); a decided card folds to a one-line trace.
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { HOLD_MS } from "../../ui/HoldButton";
import { ApprovalCard, ApprovalQueue } from "./ApprovalCard";
import type { CardData } from "./types";

function core() {
  const fetch = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const card = (title: string, more: Partial<CardData> = {}): CardData => ({
  kind: "desk",
  title: { en: title, ar: title },
  detail: { en: `${title}: details - sample`, ar: `${title}: التفاصيل - عينة` },
  options: ["yes", "no"],
  status: "pending",
  ...more,
});

const budget = card("نبدأ التكليف؟ - عينة", { kind: "budget", hold: { why: "paid", options: ["yes"] } });
const outside = card("إرسال الطلب للمورد", { kind: "outside", hold: { why: "irreversible", options: ["yes"] } });

beforeEach(() => setLanguage("ar"));
afterEach(() => vi.useRealTimers());

describe("ApprovalQueue", () => {
  it("opens one card at a time; the rest wait in a short queue", async () => {
    core();
    const user = userEvent.setup();
    const cards = ["أ", "ب", "ج"].map((n) => ({ id: n, data: card(`بطاقة ${n} - عينة`) }));
    render(<ApprovalQueue cards={cards} />);
    expect(screen.getAllByRole("region")).toHaveLength(1);
    expect(screen.getByText("بطاقة أ - عينة: التفاصيل - عينة")).toBeInTheDocument();
    expect(screen.queryByText("بطاقة ب - عينة: التفاصيل - عينة")).toBeNull();
    expect(screen.getByText("اتنين كمان مستنيين")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: texts.keepDesk.ar }));
    // the first folds to its line, the next opens
    expect(await screen.findByText("بطاقة ب - عينة: التفاصيل - عينة")).toBeInTheDocument();
    expect(screen.getByText("واحدة كمان مستنية")).toBeInTheDocument();
    expect(screen.getAllByRole("region")).toHaveLength(2);
  });

  it("keeps the chat's marks: the open card is the first one waiting", () => {
    const cards = [
      { id: "done", data: card("قديمة - عينة", { status: "settled", choice: "yes" }) },
      { id: "a", data: card("أولى - عينة") },
      { id: "b", data: card("تانية - عينة") },
    ];
    const { container } = render(<ApprovalQueue cards={cards} />);
    const waiting = container.querySelectorAll("[data-waiting]");
    expect([...waiting].map((el) => (el as HTMLElement).dataset.card)).toEqual(["a"]);
    expect(container.querySelectorAll("[data-card]")).toHaveLength(3);
  });
});

describe("press-and-hold", () => {
  it("a paid answer goes only after a full hold; a click sends nothing", async () => {
    vi.useFakeTimers();
    const fetch = core();
    render(<ApprovalCard id="c1" card={budget} />);
    const yes = screen.getByRole("button", { name: texts.startBrief.ar });
    expect(yes).toHaveAccessibleDescription(texts.holdHintPaid.ar);
    fireEvent.click(yes);
    fireEvent.pointerDown(yes, { button: 0 });
    act(() => vi.advanceTimersByTime(HOLD_MS - 200));
    fireEvent.pointerUp(yes);
    expect(fetch).not.toHaveBeenCalled();
    fireEvent.pointerDown(yes, { button: 0 });
    await act(async () => vi.advanceTimersByTime(HOLD_MS));
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(JSON.parse(String(fetch.mock.calls[0]![1]!.body))).toEqual({ choice: "yes" });
  });

  it("an irreversible one says so; saying no stays one click", async () => {
    const fetch = core();
    const user = userEvent.setup();
    render(<ApprovalCard id="c2" card={outside} />);
    expect(screen.getByRole("button", { name: texts.allowOnce.ar })).toHaveAccessibleDescription(texts.holdHintIrreversible.ar);
    const no = screen.getByRole("button", { name: texts.dontAllow.ar });
    expect(no).not.toHaveAccessibleDescription();
    await user.click(no);
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("an ordinary approval is a single click", async () => {
    const fetch = core();
    const user = userEvent.setup();
    render(<ApprovalCard id="c3" card={card("مكتب - عينة")} />);
    await user.click(screen.getByRole("button", { name: texts.keepDesk.ar }));
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});

describe("a decided card", () => {
  it("folds to a one-line trace: the answer, what it was, and when", () => {
    const at = "2026-11-05T08:42:00.000Z";
    render(<ApprovalCard id="c1" card={{ ...outside, status: "settled", choice: "yes", settled_at: at }} />);
    const time = new Intl.DateTimeFormat("ar-EG-u-nu-latn", { hour: "numeric", minute: "2-digit" }).format(new Date(at));
    const line = screen.getByRole("button", { expanded: false });
    expect(line).toHaveTextContent(`ردّك: ${texts.allowOnce.ar} · إرسال الطلب للمورد · ${time}`);
    expect(line.querySelector("time")).toHaveAttribute("datetime", at);
  });
});
