// The Document viewer against the core's contract (Plan 6 Task 7), with fetch mocked: no core, no network.
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Change, DocumentView, Explained, Thread } from "../../deliverables/types";
import { count, setLanguage, texts } from "../../i18n";
import { DocumentViewer, type DocumentHandle } from "./DocumentViewer";

// jsdom has no editing: Slate only takes key and input events from a target whose isContentEditable is true, and
// uses the browser's beforeinput when getTargetRanges exists. Both are there in WebKitGTK and Chromium.
vi.hoisted(() => {
  (InputEvent.prototype as unknown as { getTargetRanges: () => [] }).getTargetRanges = () => [];
  Object.defineProperty(HTMLElement.prototype, "isContentEditable", {
    configurable: true,
    get(this: HTMLElement) {
      return this.closest("[contenteditable]")?.getAttribute("contenteditable") === "true";
    },
  });
});

const P = "p1";
const D = "d".repeat(32);
const SHEET = "e".repeat(32);
const base = `/api/projects/${P}`;
const PRICES = "الأسعار سارية حالياً لمدة ٣٠ يوماً";

// The core's sample covering letter (core/tests/samples.py): «عينة» in names, sources of kind sample.
function letter(more: Partial<DocumentView> = {}): DocumentView {
  return {
    id: D, kind: "document", variant: "letter", title: "خطاب العطاء - عينة", language: "ar",
    status: "draft", code: null, same_provider: false, off_desk: false,
    version: 1, at: "2026-11-05T09:00:00.000000+00:00", revision: null, sample: true,
    blocks: [
      { id: "b1", version: 1, node: { type: "h1", children: [{ text: "خطاب تقديم العطاء - عينة" }] } },
      { id: "b2", version: 1, node: { type: "p", children: [{ text: "السادة / شركة التطوير العقاري - عينة، تحية طيبة وبعد،" }] } },
      {
        id: "b3", version: 1,
        node: {
          type: "p",
          children: [
            { text: "نتشرف بتقديم عطائنا بإجمالي " },
            { type: "cell", deliverable: SHEET, row: "total", column: "amount", children: [{ text: "" }] },
            { text: " جنيه مصري حسب جدول الكميات المرفق." },
          ],
        },
      },
      { id: "b4", version: 1, node: { type: "p", children: [{ text: PRICES }] } },
    ],
    refs: {
      [`cell:${SHEET}:total:amount`]: { value: "4859830.00", currency: "EGP", number_id: "n-total", source: "s3", dated: "2026-11-01", calculated: true },
    },
    untraced: [{ block: "b4", text: "٣٠" }],
    sources: { s3: { kind: "calculation", title: "sum(amount)", locator: { calculation: "c9" } } },
    pending: 0, open_comments: 0, records_moved: false, progress: null,
    ...more,
  };
}

function change(id: string, more: Partial<Change> = {}): Change {
  return {
    id, deliverable_id: D,
    op: { op: "set_block", block: "b4", node: { type: "p", children: [{ text: "الأسعار سارية حالياً لمدة ٤٥ يوماً" }] }, expect: 1 },
    reason: null, author: "lead_qs", comment_id: null, status: "pending",
    created_at: "2026-11-05T09:01:00.000000+00:00", decided_at: null, decided_by: null, version_n: null,
    before: null, after: null, follows: [],
    segments: [
      { op: "same", text: "الأسعار سارية حالياً لمدة " },
      { op: "del", text: "٣٠" },
      { op: "ins", text: "٤٥" },
      { op: "same", text: " يوماً" },
    ],
    ...more,
  };
}

function thread(id: string, more: Partial<Thread> = {}): Thread {
  const anchor = { type: "text" as const, block: "b4", start: 14, end: 20, quote: "حالياً" };
  return {
    id, deliverable_id: D, parent_id: null, kind: "review", anchor, anchor_now: anchor,
    body: "راجع مدة السريان - عينة", author: "engineer", code: null, check_id: null, status: "open", version_n: 1,
    created_at: "2026-11-05T09:02:00.000000+00:00", closed_at: null, closed_by: null, fix_asked_at: null, replies: [],
    ...more,
  };
}

type Route = (url: string, init: RequestInit) => Response | Promise<Response>;
function core(routes: Record<string, Route> = {}) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const route = routes[`${init.method ?? "GET"} ${url.split("?")[0]}`];
    return route ? route(url, init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
const bodies = (fetch: ReturnType<typeof core>, method: string, path: string) =>
  fetch.mock.calls
    .filter(([u, init]) => String(u).split("?")[0] === path && (init?.method ?? "GET") === method)
    .map(([, init]) => JSON.parse(String(init!.body)) as unknown);

const blockEl = (id: string) => document.querySelector(`[data-block-id="${id}"]`) as HTMLElement;
const settle = () => act(() => new Promise((r) => setTimeout(r, 120))); // Slate reads the DOM selection, throttled

/** Puts the caret in a block's text (at its end by default), as a click would, and types. */
async function typeIn(id: string, text: string, at?: number) {
  const strings = [...blockEl(id).querySelectorAll("[data-slate-string]")];
  const node = (at === undefined ? strings[strings.length - 1] : strings[0])!.firstChild!;
  const user = userEvent.setup();
  await user.click(blockEl(id));
  window.getSelection()!.collapse(node, at ?? node.textContent!.length);
  document.dispatchEvent(new Event("selectionchange"));
  await settle();
  await user.keyboard(text);
}

beforeEach(() => setLanguage("ar"));

describe("DocumentViewer", () => {
  it("every block has dir auto and the document's lang; an Arabic letter is rtl in an English screen", () => {
    setLanguage("en");
    render(<DocumentViewer projectId={P} view={letter()} />);
    expect(screen.getByRole("textbox", { name: "خطاب العطاء - عينة" })).toHaveAttribute("dir", "rtl");
    const blocks = document.querySelectorAll("[data-block-id]");
    expect(blocks).toHaveLength(4);
    for (const b of blocks) {
      expect(b).toHaveAttribute("dir", "auto");
      expect(b).toHaveAttribute("lang", "ar");
    }
    expect(blockEl("b1").tagName).toBe("H1");
    expect(blockEl("b4")).toHaveTextContent(PRICES);
  });

  it("a number reference shows its value, cannot be typed over, and opens its source", async () => {
    const explained: Explained = {
      number: {
        id: "n-total", item: { id: "i9", code: null, kind: "bill" }, name: "amount", value: "4859830.00", unit: null, currency: "EGP",
        dated: "2026-11-01", recorded_at: "2026-11-01T08:00:00Z", recorded_by: "calc_engine", current: true, replaced_by: null, reason: null,
      },
      source: { id: "s3", kind: "calculation", title: "sum(amount)", file_id: null, locator: {}, url: null, dated: null },
      calculation: { id: "c9", formula: "sum(amount)", unit: "EGP", inputs: [], steps: [], stale: false, page: 1, pages: 1 },
    };
    core({ [`GET ${base}/numbers/n-total/explain`]: () => Response.json(explained) });
    render(<DocumentViewer projectId={P} view={letter()} />);
    const value = within(blockEl("b3")).getByRole("button", { name: "4,859,830.00" });
    expect(value).toHaveTextContent("4,859,830.00");
    expect(value.querySelector("bdi")).toHaveAttribute("dir", "ltr");
    expect(value.closest("[contenteditable='false']")).not.toBeNull(); // a void: no caret, no typing inside
    await userEvent.setup().click(value);
    const popover = await screen.findByRole("dialog", { name: texts.sheetSource.ar });
    expect(await within(popover).findByText("مجموع الإجمالي", { selector: "bdi" })).toBeInTheDocument(); // the formula in words
  });

  it("pending segments draw struck and inserted words, never split letters, with ✓ and ✗", async () => {
    const fetch = core({ [`POST ${base}/deliverables/${D}/changes/accept`]: () => Response.json({ version: 2, accepted: ["c1"], stale: [] }) });
    const onChanged = vi.fn();
    render(<DocumentViewer projectId={P} view={letter()} changes={[change("c1")]} onChanged={onChanged} />);
    const block = blockEl("b4");
    expect(block.querySelector("del")).toHaveTextContent(/^٣٠$/);
    expect(block.querySelector("ins")).toHaveTextContent(/^٤٥$/);
    expect(block.querySelector("del")!.className).toContain("line-through");
    expect(block).toHaveTextContent("الأسعار سارية حالياً لمدة ٣٠٤٥ يوماً");
    await userEvent.setup().click(within(block).getByRole("button", { name: texts.sheetAccept.ar }));
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes/accept`)).toEqual([{ ids: ["c1"] }]);
    await waitFor(() => expect(blockEl("b4").querySelector("ins")).toBeNull());
    expect(onChanged).toHaveBeenCalled();
    expect(within(blockEl("b4")).queryByRole("button", { name: texts.sheetReject.ar })).toBeNull();
  });

  it("with no segments from the core, the old text is struck whole and the new one sits beside it", () => {
    render(<DocumentViewer projectId={P} view={letter()} changes={[change("c1", { segments: undefined })]} />);
    expect(blockEl("b4").querySelector("del")).toHaveTextContent(PRICES);
    expect(blockEl("b4").querySelector("ins")).toHaveTextContent("الأسعار سارية حالياً لمدة ٤٥ يوماً");
  });

  it("a suggested new paragraph and a removal show in place", () => {
    const insert = change("c2", {
      op: { op: "insert_block", after: "b2", node: { type: "p", children: [{ text: "فقرة جديدة - عينة" }] } },
      segments: undefined,
    });
    const remove = change("c3", { op: { op: "remove_block", block: "b1", expect: 1 }, segments: undefined });
    render(<DocumentViewer projectId={P} view={letter()} changes={[insert, remove]} />);
    const ids = [...document.querySelectorAll("[data-block-id]")].map((b) => b.getAttribute("data-block-id"));
    expect(ids).toEqual(["b1", "b2", "new:c2", "b3", "b4"]);
    expect(blockEl("new:c2").querySelector("ins")).toHaveTextContent("فقرة جديدة - عينة");
    expect(blockEl("b1").querySelector("del")).toHaveTextContent("خطاب تقديم العطاء - عينة");
  });

  it("comment decorations mark the quoted text; a moved comment shows on its block", () => {
    const moved = thread("t2", {
      kind: "note",
      anchor_now: { type: "row", block: "b2", moved: true },
      body: "كانت على «تحية» - عينة",
    });
    render(<DocumentViewer projectId={P} view={letter()} comments={[thread("t1"), moved, thread("t3", { status: "closed" })]} />);
    const marked = blockEl("b4").querySelectorAll("[data-comment='review']");
    expect([...marked].map((m) => m.textContent).join("")).toBe("حالياً");
    expect(marked[0]).toHaveAttribute("title", texts.reviewComment.ar);
    expect(within(blockEl("b2")).getByRole("note")).toHaveAccessibleName(`${texts.reviewNote.ar}: ${texts.docMoved.ar}`);
    expect(document.querySelectorAll("[data-comment]")).toHaveLength(marked.length); // the closed one is not drawn
  });

  it("untraced digits are underlined with a label", () => {
    render(<DocumentViewer projectId={P} view={letter()} />);
    const untraced = blockEl("b4").querySelector("[data-untraced]");
    expect(untraced).toHaveTextContent(/^٣٠$/);
    expect(untraced).toHaveAttribute("title", texts.docUntraced.ar);
    expect(screen.getByText(count("docUntracedCount", 1, {}, "ar"))).toBeInTheDocument();
  });

  it("its notes read in the page's direction: an Arabic letter on an English page starts no note with a full stop (tender day)", () => {
    setLanguage("en");
    render(
      <div dir="rtl">
        <DocumentViewer projectId={P} view={letter()} />
      </div>,
    );
    for (const note of [screen.getByText(count("docUntracedCount", 1, {}, "en")), screen.getByText(texts.docCommitHint.en)]) {
      expect(note).toHaveAttribute("dir", "ltr");
      expect(note).toHaveAttribute("lang", "en");
    }
  });

  it("an edit is sent on Ctrl+Enter as one set_block op with the block's version, then shows as suggested", async () => {
    const added = " - عينة";
    const posted = change("c9", {
      author: "engineer",
      op: { op: "set_block", block: "b4", node: { type: "p", id: "b4", children: [{ text: PRICES + added }] }, expect: 1 },
      segments: [{ op: "same", text: PRICES }, { op: "ins", text: added }],
    });
    const fetch = core({ [`POST ${base}/deliverables/${D}/changes`]: () => Response.json({ changes: [posted] }, { status: 201 }) });
    const onChanged = vi.fn();
    render(<DocumentViewer projectId={P} view={letter()} onChanged={onChanged} />);
    await typeIn("b4", added);
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)).toEqual([]); // never on each keystroke
    await userEvent.setup().keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() =>
      expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)).toEqual([
        { ops: [{ op: "set_block", block: "b4", node: { type: "p", id: "b4", children: [{ text: PRICES + added }] }, expect: 1 }], reason: null },
      ]),
    );
    await waitFor(() => expect(blockEl("b4").querySelector("ins")).toHaveTextContent(added.trim()));
    expect(onChanged).toHaveBeenCalled();
  });

  it("leaving the editor sends the edit too", async () => {
    const fetch = core({ [`POST ${base}/deliverables/${D}/changes`]: () => Response.json({ changes: [] }, { status: 201 }) });
    render(
      <>
        <DocumentViewer projectId={P} view={letter()} />
        <button type="button">after</button>
      </>,
    );
    await typeIn("b2", "س");
    act(() => screen.getByRole("button", { name: "after" }).focus());
    await waitFor(() => expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)).toHaveLength(1));
  });

  it("a block waiting for a decision cannot be typed in", async () => {
    const fetch = core();
    render(<DocumentViewer projectId={P} view={letter()} changes={[change("c1")]} />);
    const before = blockEl("b4").textContent;
    await typeIn("b4", "X", 2);
    await userEvent.setup().keyboard("{Control>}{Enter}{/Control}");
    await settle();
    expect(blockEl("b4").textContent).toBe(before);
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/changes`)).toEqual([]);
  });

  it("a refused edit stays on screen and says why in plain words", async () => {
    const error = { en: "This paragraph changed after you started. Ask ONE again, or edit it yourself.", ar: "الفقرة دي اتغيّرت. - عينة" };
    core({ [`POST ${base}/deliverables/${D}/changes`]: () => Response.json({ error, field: "ops[0].expect" }, { status: 422 }) });
    render(<DocumentViewer projectId={P} view={letter()} />);
    await typeIn("b4", "!");
    await userEvent.setup().keyboard("{Control>}{Enter}{/Control}");
    expect(await screen.findByRole("alert")).toHaveTextContent(error.ar);
    expect(blockEl("b4")).toHaveTextContent(`${PRICES}!`);
  });

  it("locate finds a block or its text in the viewer's own pixels, and null for an unknown block", () => {
    const ref = createRef<DocumentHandle>();
    render(<DocumentViewer projectId={P} view={letter()} ref={ref} />);
    expect(ref.current!.locate({ row: "b4" })).toBeInstanceOf(DOMRect);
    expect(ref.current!.locate({ row: "b4", text: [14, 20] })).toBeInstanceOf(DOMRect);
    expect(ref.current!.locate({ row: "nope" })).toBeNull();
  });

  it("selected text is reported as a comment anchor with its quote", async () => {
    const onSelection = vi.fn();
    render(<DocumentViewer projectId={P} view={letter()} onSelection={onSelection} />);
    const node = blockEl("b2").querySelector("[data-slate-string]")!.firstChild!;
    await userEvent.setup().click(blockEl("b2"));
    window.getSelection()!.setBaseAndExtent(node, 13, node, 9);
    document.dispatchEvent(new Event("selectionchange"));
    await settle();
    expect(onSelection).toHaveBeenLastCalledWith({ type: "text", block: "b2", start: 9, end: 13, quote: "شركة" });
  });

  it("the sample banner and the status chip have text labels", () => {
    render(<DocumentViewer projectId={P} view={letter({ status: "checked", code: "B", revision: { no: 2, version: 1, signed_off: false } })} />);
    expect(screen.getByText(texts.sheetSample.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.statusChecked.ar.replace("{code}", "B"))).toBeInTheDocument();
    expect(screen.getByText(texts.reviewRev.ar.replace("{n}", "2"))).toBeInTheDocument();
  });
});
