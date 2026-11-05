import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { ApprovalCard } from "./ApprovalCard";
import { ContinueBriefs } from "./ContinueBriefs";
import { CoordinationRoom } from "./CoordinationRoom";
import { CostNotice } from "./CostNotice";
import { ProgressLine } from "./ProgressLine";
import { ReviewBadge } from "./ReviewBadge";
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

const lead = { en: "Lead QS", ar: "كبير مهندسي الكميات" };
const estimator = { en: "Estimator", ar: "مهندس التسعير" };

beforeEach(() => setLanguage("ar"));

describe("ProgressLine", () => {
  it("shows one line per agent with its name and latest words", () => {
    render(
      <ProgressLine
        items={[
          { id: "r1", data: { agent: lead, text: { en: "planning the Brief", ar: "بيخطط للتكليف" } } },
          { id: "r2", data: { agent: estimator, text: { en: "reading page 12", ar: "بيقرا صفحة 12" } } },
        ]}
      />,
    );
    const lines = within(screen.getByRole("list", { name: texts.progressLine.ar })).getAllByRole("listitem");
    expect(lines.map((line) => line.textContent)).toEqual([
      expect.stringContaining("بيخطط للتكليف"),
      expect.stringContaining("بيقرا صفحة 12"),
    ]);
    expect(lines[1]).toHaveTextContent(estimator.ar);
  });

  it("speaks the Brief's language, not the page's: an Arabic Brief in the English page", () => {
    setLanguage("en");
    const text = { en: "Look at the BOQ columns in boq-priced.xls", ar: "يبص على أعمدة المقايسة في boq-priced.xls" };
    const { rerender } = render(<ProgressLine items={[{ id: "r1", data: { agent: lead, text, lang: "ar" } }]} />);
    const line = screen.getByRole("listitem");
    expect(line).toHaveTextContent(`${lead.ar} ${text.ar}`);
    expect(line).toHaveAttribute("dir", "rtl");
    // an older part with no language follows the Brief's from the chat; the page's only with neither
    rerender(<ProgressLine items={[{ id: "r1", data: { agent: lead, text } }]} lang="ar" />);
    expect(screen.getByRole("listitem")).toHaveTextContent(text.ar);
    rerender(<ProgressLine items={[{ id: "r1", data: { agent: lead, text } }]} />);
    expect(screen.getByRole("listitem")).toHaveTextContent(text.en);
  });

  it("shows nothing with no agent at work", () => {
    const { container } = render(<ProgressLine items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("CoordinationRoom", () => {
  it("is folded with its count, and opens to the agents' messages", async () => {
    const user = userEvent.setup();
    render(
      <CoordinationRoom
        messages={[
          { id: "m1", data: { sender: lead, recipient: estimator, text: "سعّر بند 03/02 - عينة" } },
          { id: "m2", data: { sender: estimator, recipient: lead, text: "Done: rate from the sample quote" } },
        ]}
      />,
    );
    const summary = screen.getByText("غرفة التنسيق، رسالتين");
    const first = screen.getByText("سعّر بند 03/02 - عينة");
    expect(first).not.toBeVisible();
    expect(first).toHaveAttribute("dir", "auto");

    await user.click(summary);
    expect(first).toBeVisible();
    expect(screen.getByText("من كبير مهندسي الكميات لـمهندس التسعير")).toBeVisible();
  });
});

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
    expect(await screen.findByText("ردّك: اسمح للتكليف ده كله")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: texts.dontAllow.ar })).not.toBeInTheDocument();
    expect(bodyOf(fetch, "POST", "/api/cards/c1")).toEqual([{ choice: "brief" }]);
  });

  it("a card settled in the stream shows its choice, with no buttons", () => {
    render(<ApprovalCard id="c1" card={{ ...online, status: "settled", choice: "no" }} />);
    expect(screen.getByText(`ردّك: ${texts.dontAllow.ar}`)).toBeInTheDocument();
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
        en: "One paused at 80% of the Spending Cap for this Brief: 2.41 of 3.00 USD spent.",
        ar: "One وقّف عند 80% من سقف الصرف بتاع التكليف ده: اتصرف 2.41 من 3.00 دولار.",
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

  it("raising the cap saves the new caps first, then answers", async () => {
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
    await user.click(screen.getByRole("button", { name: texts.save.ar }));

    expect(await screen.findByText("ردّك: ارفع السقف")).toBeInTheDocument();
    expect(bodyOf(fetch, "PUT", "/api/settings/ai/caps")).toEqual([{ ...amounts, brief: "5.00" }]);
    expect(bodyOf(fetch, "POST", "/api/cards/cap1")).toEqual([{ choice: "raise" }]);
  });
});

describe("CostNotice", () => {
  it("shows the core's words with the real amounts", () => {
    render(
      <CostNotice
        cost={{
          level: "stopped",
          scope: "brief",
          spent: "3.00",
          cap: "3.00",
          equivalent: false,
          text: { en: "The Spending Cap for this Brief is reached: 3.00 of 3.00 USD.", ar: "وصلنا لسقف الصرف بتاع التكليف ده: 3.00 من 3.00 دولار." },
        }}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("3.00 من 3.00 دولار");
    expect(screen.queryByText(texts.equivalentCost.ar)).not.toBeInTheDocument();
  });

  it("says when the cost is the subscription's equivalent cost", () => {
    render(
      <CostNotice
        cost={{
          level: "info",
          scope: "day",
          spent: "4.10",
          cap: "15.00",
          equivalent: true,
          text: { en: "4.10 of 15.00 USD today.", ar: "4.10 من 15.00 دولار النهارده." },
        }}
      />,
    );
    expect(screen.getByText(texts.equivalentCost.ar)).toBeInTheDocument();
  });
});

describe("ReviewBadge", () => {
  const comments = [
    { about: "Item 03/02", text: "The rate's quote is older than three months." },
    { about: "بند 04/01", text: "الكمية من اللوحة S-101 - عينة" },
  ];

  it("shows Code B with its comments when opened, and the same-provider note", async () => {
    const user = userEvent.setup();
    render(<ReviewBadge review={{ code: "B", comments, same_provider: true }} />);
    await user.click(screen.getByText(texts.codeB.ar));
    expect(screen.getByText(comments[0]!.text)).toBeVisible();
    expect(screen.getByText(comments[1]!.text)).toHaveAttribute("dir", "auto");
    expect(screen.getByText(texts.sameProvider.ar)).toBeInTheDocument();
  });

  it("names each code with the glossary's words", () => {
    const { rerender } = render(<ReviewBadge review={{ code: "A", comments: [], same_provider: false }} />);
    expect(screen.getByText(texts.codeA.ar)).toBeInTheDocument();
    expect(screen.queryByText(texts.sameProvider.ar)).not.toBeInTheDocument();
    rerender(<ReviewBadge review={{ code: "C", comments: [], same_provider: false }} />);
    expect(screen.getByText(texts.codeC.ar)).toBeInTheDocument();
  });
});

describe("ContinueBriefs", () => {
  const briefs = [
    {
      id: "b1",
      chat_id: "p1",
      project_name: "مدرسة - عينة",
      step: { en: "Estimator pricing item 03/02", ar: "مهندس التسعير بيسعّر بند 03/02" },
      state: "running",
    },
    { id: "b2", chat_id: "general", project_name: null, step: { en: "planning", ar: "بيخطط" }, state: "paused_cap" },
  ];

  it("offers each unfinished Brief, and continues only on press", async () => {
    const fetch = core({
      "GET /api/briefs/unfinished": () => Response.json({ briefs }),
      "POST /api/briefs/b1/continue": () => Response.json({ state: "running" }),
    });
    const onContinued = vi.fn();
    const user = userEvent.setup();
    render(<ContinueBriefs onContinued={onContinued} />);

    const card = (await screen.findByText(/مهندس التسعير بيسعّر بند 03\/02/)).closest("section")!;
    expect(within(card).getByText("مدرسة - عينة")).toBeInTheDocument();
    expect(screen.getByText(texts.generalChat.ar)).toBeInTheDocument();
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false); // nothing by itself

    await user.click(within(card).getByRole("button", { name: texts.continue.ar }));
    await waitFor(() => expect(onContinued).toHaveBeenCalledWith(expect.objectContaining({ id: "b1", chat_id: "p1" })));
    expect(screen.queryByText("مدرسة - عينة")).not.toBeInTheDocument();
    expect(fetch.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  it("leave hides it without asking the core", async () => {
    const fetch = core({ "GET /api/briefs/unfinished": () => Response.json({ briefs: briefs.slice(0, 1) }) });
    const user = userEvent.setup();
    render(<ContinueBriefs onContinued={() => undefined} />);
    await user.click(await screen.findByRole("button", { name: texts.leave.ar }));
    expect(screen.queryByText("مدرسة - عينة")).not.toBeInTheDocument();
    expect(fetch.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
  });
});
