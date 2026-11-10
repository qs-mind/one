// The card bodies a thread draws beside a card's words, on the design system (decisions 17.8): a table whose rows are
// ticked or whose columns are mapped, a Connector being added, a model with no known price, and "Raise the cap".
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { server, startFakeCore } from "@/api/fakeCore";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { cardOption, cards } from "@/texts/cards";
import { text } from "@/texts/useText";
import type { CardData, Source, ThreadMessage } from "./parts";
import { Thread, type ThreadProps } from "./Thread";

startFakeCore();
let answered: { id: string; body: unknown }[];
let prices: unknown[];
beforeEach(() => {
  stubBrowser();
  answered = [];
  prices = [];
  server.use(
    http.post("*/api/cards/:id", async ({ params, request }) => {
      answered.push({ id: String(params.id), body: await request.json() });
      return new HttpResponse(null, { status: 204 });
    }),
    http.put("*/api/settings/ai/prices", async ({ request }) => {
      prices.push(await request.json());
      return HttpResponse.json({});
    }),
  );
});
afterEach(() => resetPage());

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const pair = (en: string) => ({ en, ar: `${en} - عينة` });
const source: Source = { kind: "sample", title: "Quote 12 (sample)", file_name: null, file_id: "f1", locator: { row: 4 }, url: null, dated: null, quote: null } as Source;
const priceRows: CardData = {
  kind: "rows",
  title: pair("Keep these prices (sample)"),
  detail: pair("From the supplier's quote (sample)"),
  options: ["keep", "no"],
  payload: {
    tick: true,
    columns: [{ key: "item", label: pair("Item") }, { key: "rate", label: pair("Rate") }],
    rows: [{ item: "Concrete C30 (sample)", rate: "1,850" }, { item: "Rebar (sample)", rate: "42,000" }],
    number_column: "rate",
    row_sources: [source, null],
  },
};
const boqColumns: CardData = {
  kind: "rows",
  title: pair("Import this BOQ (sample)"),
  detail: pair("These are the sheet's columns (sample)"),
  options: ["keep", "no"],
  payload: {
    columns: [{ key: "column", label: pair("Column") }, { key: "meaning", label: pair("Holds") }],
    rows: [{ column: "A", meaning: "item" }, { column: "B", meaning: "none" }],
    meanings: [{ key: "item", label: pair("Item number") }, { key: "none", label: pair("Not used") }],
    meaning_column: "meaning",
  },
};
const connector: CardData = {
  kind: "connector",
  title: pair("Add this Connector? (sample)"),
  detail: pair("A supplier catalogue (sample)"),
  options: ["yes", "no"],
  payload: {
    tools: [{ name: "find_price", purpose: "Finds a price (sample)", read_only: true, destructive: false, open_world: false }],
    questions: [{ id: "read_without_asking", text: "" }, { id: "search", text: "", options: ["none", "find_price"] }],
  },
};
const price: CardData = {
  kind: "price",
  title: pair("A model with no known price (sample)"),
  detail: pair("ONE does not know this model's price (sample)"),
  options: ["price", "nocap", "no"],
  payload: { model: { connector: "standard:x", model: "m1", name: "Model one (sample)" } },
};
const cap: CardData = {
  kind: "cap",
  title: pair("Spending Cap (sample)"),
  detail: pair("This work reached 80% of its cap (sample)"),
  options: ["continue", "raise", "report"],
};
const reply = (card: CardData): ThreadMessage => ({
  id: "b9-reply",
  role: "assistant",
  parts: [
    { type: "data-card", id: "c1", data: card },
    { type: "data-status", id: "b9", data: { state: "waiting_engineer", step: null } },
  ] as ThreadMessage["parts"],
});
const props = (card: CardData, over: Partial<ThreadProps> = {}): ThreadProps => ({
  messages: [reply(card)],
  leadName: "Lead QS",
  plan: null,
  findings: [],
  onApprovePlan: vi.fn(),
  onDiscussPlan: vi.fn(),
  onPlanChange: vi.fn(),
  onDecide: vi.fn(),
  ...over,
});

describe.each(DIRS)("a card's body (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";

  it("keeps the ticked rows, strikes the others once answered, and opens a row's source", async () => {
    const opened = vi.fn();
    const { container } = renderIn(dir, <Thread {...props(priceRows, { onOpenSource: opened })} />);
    const keep = screen.getByRole("button", { name: text(cardOption.keepTicked, lang) });
    expect(keep).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: text(cards.sourceOf, lang, { value: "1,850" }) }));
    expect(opened).toHaveBeenCalledWith(source);
    await userEvent.click(screen.getByRole("checkbox", { name: text(cards.tickRow, lang, { n: 2 }) }));
    await userEvent.click(keep);
    await waitFor(() => expect(answered).toEqual([{ id: "c1", body: { choice: "keep", rows_ok: [1] } }]));
    await waitFor(() => expect(container.querySelectorAll("[data-left-out]")).toHaveLength(1));
    expect(container.querySelector("[data-left-out]")).toHaveTextContent("Concrete C30 (sample)");
  });

  it("folds a BOQ import's columns to one line and imports with them as mapped", async () => {
    const { container } = renderIn(dir, <Thread {...props(boqColumns)} />);
    expect(container.querySelector("table")).toBeNull();
    expect(container.querySelector("[data-columns-taken]")).toHaveTextContent(`${pair("Item number")[lang]}: A`);
    await userEvent.click(screen.getByRole("button", { name: text(cards.checkColumns, lang) }));
    expect(screen.getByRole("combobox", { name: text(cards.columnMeaning, lang, { letter: "B" }) })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: text(cards.keepColumns, lang) }));
    await waitFor(() => expect(answered).toEqual([{ id: "c1", body: { choice: "keep", answers: { A: "item", B: "none" } } }]));
  });

  it("adds a Connector with its reading tools let through", async () => {
    renderIn(dir, <Thread {...props(connector)} />);
    expect(screen.getByText("Finds a price (sample)")).toBeInTheDocument();
    expect(screen.getByText(text(cards.toolReadsOnly, lang))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("checkbox", { name: text(cards.readWithoutAsking, lang) }));
    await userEvent.click(screen.getByRole("button", { name: text(cardOption.addIt, lang) }));
    await waitFor(() =>
      expect(answered).toEqual([{ id: "c1", body: { choice: "yes", answers: { read_without_asking: "yes", search: "none" } } }]),
    );
  });

  it("saves a model's price, then goes on with it", async () => {
    renderIn(dir, <Thread {...props(price)} />);
    await userEvent.click(screen.getByRole("button", { name: text(cardOption.enterItsPrice, lang) }));
    fireEvent.change(screen.getByLabelText(text(cards.priceIn, lang)), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText(text(cards.priceOut, lang)), { target: { value: "15" } });
    await userEvent.click(screen.getByRole("button", { name: text(cards.useThisPrice, lang) }));
    await waitFor(() => expect(answered).toEqual([{ id: "c1", body: { choice: "price" } }]));
    expect(prices).toEqual([{ connector: "standard:x", model: "m1", in: "3", out: "15" }]);
  });

  it("raises the cap in place with the Spending caps of Settings", async () => {
    const { container } = renderIn(dir, <Thread {...props(cap)} />);
    await userEvent.click(screen.getByRole("button", { name: text(cardOption.capRaise, lang) }));
    await waitFor(() => expect(container.querySelector("[data-raise-caps]")).not.toBeNull());
    expect(screen.getByText(lang === "ar" ? "الشغلانة الواحدة" : "One piece of work")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: text(cards.raiseGo, lang) }));
    await waitFor(() => expect(answered).toEqual([{ id: "c1", body: { choice: "raise" } }]));
  });
});
