import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { ApprovalCard } from "./ApprovalCard";
import { cardKinds } from "./cardKinds";
import { RowsCard } from "./RowsCard";
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

// What prices_propose sends (core/qsone/tools/prices.py): a table, a tick per row, Keep and Refuse.
const rows: CardData = {
  kind: "rows",
  title: { en: "Keep these prices?", ar: "أحفظ الأسعار دي؟" },
  detail: { en: "Tick the rows to keep.", ar: "علّم على الصفوف اللي تتحفظ." },
  options: ["keep", "no"],
  status: "pending",
  payload: {
    columns: [
      { key: "description", label: { en: "Item", ar: "البند" } },
      { key: "rate", label: { en: "Rate", ar: "السعر" } },
    ],
    rows: [
      { description: "أسمنت - عينة", rate: "3950" },
      { description: "رمل - عينة", rate: "250" },
      { description: "زلط - عينة", rate: "310" },
    ],
    tick: true,
  },
};

describe("RowsCard", () => {
  it("is the renderer for table cards", () => {
    expect(cardKinds.rows).toBe(RowsCard);
  });

  it("ticks rows and sends rows_ok", async () => {
    const fetch = core({ "POST /api/cards/c2": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c2" card={rows} />);
    expect(screen.getByRole("columnheader", { name: "البند" })).toBeInTheDocument();
    expect(screen.queryByText("description")).not.toBeInTheDocument(); // the label, not the key
    const keep = screen.getByRole("button", { name: texts.keepTicked.ar });
    expect(keep).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: "احفظ الصف 3" }));
    await user.click(screen.getByRole("checkbox", { name: "احفظ الصف 1" }));
    await user.click(keep);
    expect(bodyOf(fetch, "POST", "/api/cards/c2")).toEqual([{ choice: "keep", rows_ok: [0, 2] }]);
    expect(await screen.findByText("اتحفظ 2 من 3 صفوف.")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByText("رمل - عينة").closest("tr")).toHaveClass("line-through"); // left out
  });

  it("Refuse sends no rows", async () => {
    const fetch = core({ "POST /api/cards/c2": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c2" card={rows} />);
    await user.click(screen.getByRole("checkbox", { name: "احفظ الصف 2" }));
    await user.click(screen.getByRole("button", { name: texts.keepNone.ar }));
    expect(bodyOf(fetch, "POST", "/api/cards/c2")).toEqual([{ choice: "no" }]);
    expect(await screen.findByText(`ردّك: ${texts.keepNone.ar}`)).toBeInTheDocument();
  });

  it("answered, it stops waiting and folds to one line, which opens again on a click", async () => {
    core({ "POST /api/cards/c2": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    const { container } = render(<ApprovalCard id="c2" card={rows} />);
    expect(container.querySelector("section")).toHaveClass("border-copper");
    for (const n of [1, 2, 3]) await user.click(screen.getByRole("checkbox", { name: `احفظ الصف ${n}` }));
    await user.click(screen.getByRole("button", { name: texts.keepTicked.ar }));
    const line = await screen.findByRole("button", { name: /أحفظ الأسعار دي؟.*اتحفظ 3 من 3 صفوف\./ });
    expect(container.querySelector("section")).not.toHaveClass("border-copper");
    expect(screen.queryByRole("table")).toBeNull(); // folded: the next card is in sight
    await user.click(line);
    expect(line).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("a card settled in the stream shows what was kept, in English too", () => {
    setLanguage("en");
    render(<ApprovalCard id="c2" card={{ ...rows, status: "settled", choice: "keep", rows_ok: [1] }} />);
    expect(screen.getByText("1 of 3 rows kept.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { expanded: false }));
    expect(screen.getByRole("columnheader", { name: "Rate" })).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "true"); // only its line, opened
  });

  it("a withdrawn card shows its table with nothing to tick or press", () => {
    render(<ApprovalCard id="c2" card={{ ...rows, status: "withdrawn" }} />);
    expect(screen.getByText(texts.withdrawn.ar)).toBeInTheDocument();
    expect(screen.getByText("أسمنت - عينة")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"); // only its folded line
  });

  it("each cell finds its own direction; a long value shows two lines, all of it in the title; narrow, the rows stack", () => {
    const long = "بالمتر المكعب حفر لزوم الأساسات وخلافة طبقاً للأبعاد والبيانات بالرسومات والمناسيب في boq-priced.xls";
    const boq = { ...rows, payload: { ...rows.payload, rows: [{ description: long, rate: "1-1, 1-3, 1-4" }] } };
    const { container } = render(<ApprovalCard id="c2" card={boq} />);
    const cell = screen.getByTitle(long);
    expect(cell.tagName).toBe("TD");
    expect(cell).toHaveAttribute("dir", "auto");
    expect(cell.firstElementChild).toHaveClass("line-clamp-2");
    expect(cell.querySelector("bdi")).toHaveTextContent("boq-priced.xls"); // the English run stays whole
    expect(cell).toHaveTextContent(long);
    expect(screen.getByTitle("1-1, 1-3, 1-4")).toHaveAttribute("dir", "auto");
    // narrower than 32rem the rows stack, every column whole as "label: value"; wider, a table
    const scroller = container.querySelector("[data-rows-scroll]")!;
    expect(scroller).toHaveClass("@container");
    expect(scroller.querySelector("table")).toHaveClass("block", "@lg:table");
    expect(screen.getByTitle("1-1, 1-3, 1-4")).toHaveAttribute("data-label", "السعر: ");
    expect(cell).not.toHaveAttribute("data-label"); // the first column heads its row
    expect(screen.getByRole("columnheader", { name: "السعر" })).toBeInTheDocument(); // still a table to a reader
  });

  it("speaks the Brief's language: an Arabic Brief's card in the English page", () => {
    setLanguage("en");
    render(<ApprovalCard id="c2" card={rows} lang="ar" />);
    expect(screen.getByRole("heading", { name: rows.title.ar })).toBeInTheDocument();
    expect(screen.getByText(rows.detail.ar)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "البند" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.keepTicked.ar })).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "احفظ الصف 1" })).toBeInTheDocument();
    expect(screen.getByRole("heading").closest("section")).toHaveAttribute("dir", "rtl");
  });

  it("a table to read, with no ticks, is answered with the plain choice", async () => {
    const fetch = core({ "POST /api/cards/c3": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    const payload = { ...rows.payload, tick: false };
    render(<ApprovalCard id="c3" card={{ ...rows, payload }} />);
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.keepTicked.ar }));
    expect(bodyOf(fetch, "POST", "/api/cards/c3")).toEqual([{ choice: "keep" }]);
  });
});
