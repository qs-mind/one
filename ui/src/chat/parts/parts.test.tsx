import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { ApprovalCard } from "./ApprovalCard";
import type { CardData } from "./types";

type Route = (init: RequestInit) => Response | Promise<Response>;

function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const route = routes[`${init.method ?? "GET"} ${String(input)}`];
    return route ? route(init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const bodyOf = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls
    .filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method)
    .map(([, init]) => JSON.parse(String(init!.body)) as unknown);


beforeEach(() => setLanguage("ar"));

describe("ApprovalCard", () => {
  const online: CardData = {
    kind: "online",
    title: { en: "Go online?", ar: "ندخل على النت؟" },
    detail: { en: "Market Pricer: searching prices. Allow it?", ar: "باحث الأسعار: بيدوّر على أسعار. نسمح بيه؟" },
    options: ["yes", "brief", "no"],
    status: "pending",
  };

  it("posts the choice and shows it settled", async () => {
    const fetch = core({ "POST /api/cards/c1": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={online} />);
    expect(screen.getByText(online.detail.ar)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: texts.allowBrief.ar }));
    expect(await screen.findByText("ردّك: سمحت للتكليف ده كله")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: texts.dontAllow.ar })).not.toBeInTheDocument();
    expect(bodyOf(fetch, "POST", "/api/cards/c1")).toEqual([{ choice: "brief" }]);
  });

  it("a card settled in the stream shows its choice, with no buttons", () => {
    render(<ApprovalCard id="c1" card={{ ...online, status: "settled", choice: "no" }} />);
    expect(screen.getByText(`ردّك: ${texts.didNotAllow.ar}`)).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"); // only its folded line
  });

  it("a refused answer keeps the buttons and says so", async () => {
    const options = { en: "Choose one of: yes, no.", ar: "اختار واحد من: yes، no." };
    core({ "POST /api/cards/c1": () => Response.json({ error: options }, { status: 422 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={online} />);
    await user.click(screen.getByRole("button", { name: texts.allowOnce.ar }));
    expect(await screen.findByRole("alert")).toHaveTextContent(options.ar);
    expect(screen.getByRole("button", { name: texts.allowOnce.ar })).toBeEnabled();
  });

  // Every card the core can send and its options (core/qsone/engine: gate.py, costs.py, team.py, runner.py).
  const emitted: [CardData["kind"], string[]][] = [
    ["outside", ["yes", "no"]],
    ["online", ["yes", "brief", "no"]],
    ["cap", ["continue", "raise", "report"]], // a pause at 80%
    ["cap", ["yes", "no"]], // a model of unknown price
    ["budget", ["yes", "no"]],
    ["fallback", ["yes", "no"]],
    ["desk", ["yes", "no"]],
    ["disagreement", ["yes", "no"]],
    // Plan 5 (core/qsone/engine/types.py Card kinds): ask_engineer, what to keep, prices, OCR cost, Connectors
    ["question", ["sent"]],
    ["keep", ["yes", "no"]],
    ["rows", ["keep", "no"]],
    ["cost", ["yes", "no"]],
    ["connector", ["yes", "no"]],
  ];

  it("every option of every card has its own words in both languages", () => {
    for (const lang of ["ar", "en"] as const) {
      setLanguage(lang);
      for (const [kind, options] of emitted) {
        const card: CardData = { kind, title: { en: "Sample", ar: "عينة" }, detail: { en: "Sample", ar: "عينة" }, options };
        const { unmount } = render(<ApprovalCard id="c1" card={card} />);
        const labels = screen.getAllByRole("button").map((button) => button.textContent ?? "");
        expect(labels.length, kind).toBe(options.length);
        expect(new Set(labels).size, kind).toBe(options.length);
        for (const label of labels) {
          expect(label.trim(), kind).not.toBe("");
          expect(options, `${kind}: ${label}`).not.toContain(label); // never the raw id
        }
        unmount();
      }
    }
  });

  it("a disagreement card names what each answer does", () => {
    const card: CardData = {
      kind: "disagreement",
      title: { en: "The Checking QS disagrees", ar: "مهندس المراجعة مش موافق" },
      detail: { en: "Sample", ar: "عينة" },
      options: ["yes", "no"],
    };
    render(<ApprovalCard id="c1" card={card} />);
    expect(screen.getByRole("button", { name: texts.keepAsIs.ar })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.sendBackToFix.ar })).toBeInTheDocument();
  });

  it("a cap card shows the real spent and cap in both languages", async () => {
    const cap: CardData = {
      kind: "cap",
      title: { en: "Spending Cap", ar: "سقف الصرف" },
      detail: {
        en: "ONE paused at 80% of the Spending Cap for this Brief: 2.41 of 3.00 USD spent.",
        ar: "ONE وقّف عند 80% من سقف الصرف بتاع التكليف ده: اتصرف 2.41 من 3.00 دولار.",
      },
      options: ["continue", "raise", "report"],
    };
    const { rerender } = render(<ApprovalCard id="cap1" card={cap} />);
    expect(screen.getByText(/2\.41 من 3\.00 دولار/)).toBeInTheDocument();
    for (const name of [texts.capContinue.ar, texts.capRaise.ar, texts.capReport.ar]) {
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    }
    setLanguage("en");
    rerender(<ApprovalCard id="cap1" card={cap} />);
    expect(screen.getByText(/2\.41 of 3\.00 USD/)).toBeInTheDocument();
  });

  it("a model of unknown price: the card links to Settings → AI, where its price is entered, until answered", async () => {
    const unpriced: CardData = {
      kind: "cap",
      title: { en: "Spending Cap", ar: "سقف الصرف" },
      detail: {
        en: "ONE does not know the price of Sample model, so the Spending Cap cannot protect you until you enter its price. Use it anyway in this Brief?",
        ar: "ONE مش عارف سعر Sample model، فسقف الصرف مش هيقدر يحميك لحد ما تكتب سعره. نستخدمه برضه في التكليف ده؟",
      },
      options: ["yes", "no"],
      fix: "ai",
      status: "pending",
    };
    const { rerender } = render(<ApprovalCard id="p1" card={unpriced} />);
    expect(screen.getByText(unpriced.detail.ar).textContent).not.toMatch(/فوق|«الذكاء الاصطناعي»/);
    expect(screen.getByRole("link", { name: texts.openAiSettings.ar })).toHaveAttribute("href", "#/settings/ai");
    rerender(<ApprovalCard id="p1" card={{ ...unpriced, status: "settled", choice: "yes" }} />);
    expect(screen.queryByRole("link", { name: texts.openAiSettings.ar })).toBeNull();
  });

  it("raising the cap saves the new caps as typed; going on waits for the last save, then answers", async () => {
    const amounts = { brief: "3.00", day: "15.00", month: "150.00", budget_above: "0.50" };
    const caps = { ...amounts, subscription_stops: false };
    const fetch = core({
      "GET /api/settings/ai/caps": () => Response.json({ caps, recommended: caps }),
      "PUT /api/settings/ai/caps": (init) => Response.json({ caps: { ...caps, ...JSON.parse(String(init.body)) }, recommended: caps }),
      "POST /api/cards/cap1": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    const cap: CardData = {
      kind: "cap",
      title: { en: "Spending Cap", ar: "سقف الصرف" },
      detail: { en: "2.41 of 3.00", ar: "2.41 من 3.00" },
      options: ["continue", "raise", "report"],
    };
    render(<ApprovalCard id="cap1" card={cap} />);
    await user.click(screen.getByRole("button", { name: texts.capRaise.ar }));
    const field = await screen.findByLabelText(texts.capBrief.ar);
    await waitFor(() => expect(field).toHaveValue("3.00"));
    await user.clear(field);
    await user.type(field, "5.00");
    // pressed before the pause is over: the change is saved first, then the card answered
    await user.click(screen.getByRole("button", { name: texts.capRaiseGo.ar }));

    expect(await screen.findByText("ردّك: رفعت السقف")).toBeInTheDocument();
    expect(bodyOf(fetch, "PUT", "/api/settings/ai/caps")).toEqual([{ ...amounts, brief: "5.00" }]);
    expect(bodyOf(fetch, "POST", "/api/cards/cap1")).toEqual([{ choice: "raise" }]);
  });
});

