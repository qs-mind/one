// A number opened in place into its source card: the number and what it is glide into the card's header, then the
// source fades in under it: who quoted it or which document, the date, the file and its cell or page, who entered it,
// and "Open source". For a calculated number, the formula, each input with its own source, and the steps (Plan 3's
// explain); an input that was itself calculated opens as a new level on top, the one under it sinking behind
// (scale 0.96, 240 ms), with a Back that says where it goes. Escape closes it and gives the focus back. It is drawn
// in the top layer (a portal), by its number: a canvas frame never cuts it and the message box never covers it; it
// flips above the number or shifts along to stay whole on the screen (./place.ts), so «افتح المصدر» can always be
// reached. Only what the core has is shown: a number with no source says so.
import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { deliverablesApi } from "../deliverables/api";
import type { Explained, NumberCell, Source } from "../deliverables/types";
import { fill, language, pick, t, texts, type Text } from "../i18n";
import { DUR, play } from "../ui/motion";
import { FileName } from "../ui/FileName";
import { useScrollEdges } from "../ui/useScrollEdges";
import { formatDecimal } from "../viewers/sheet/format";
import { flipFrom } from "./flip";
import { formulaText, termText } from "./formula";
import { readingDirection } from "./mark";
import { placeCard } from "./place";
import { workspaceApi } from "../workspace/api";

/** Who entered a number, in words: the core records a role ("engineer", "calc_engine") or an agent's English name. */
const enteredBy: Record<string, Text> = {
  engineer: texts.enteredByYou,
  lead_qs: texts.enteredByLead,
  "Lead QS": texts.enteredByLead,
  checking_qs: texts.enteredByChecker,
  "Checking QS": texts.enteredByChecker,
  calc_engine: texts.enteredByCalc,
  "QS Mind Prices": texts.enteredByPrices,
};
const whoEntered = (by: string) => (enteredBy[by] ? pick(enteredBy[by]) : fill(t("sheetEnteredBy"), { who: by }));

/** A day from the core (YYYY-MM-DD, or a full time) in the app's date style: «5 نوفمبر 2026», "5 Nov 2026". */
export function dayText(date: string): string {
  const [y, m, d] = date.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return date;
  return new Intl.DateTimeFormat(language() === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { day: "numeric", month: "short", year: "numeric" }).format(
    new Date(y, m - 1, d),
  );
}

/** A currency's word as the app writes money: «ج.م.» on an Arabic page, "EGP" on an English one; a rate's unit keeps
 * what follows the code («ج.م./م3»). Anything else stays as the core sent it. */
export function unitText(unit: string): string {
  const found = /^([A-Z]{3})(\/.+)?$/.exec(unit);
  if (!found || language() !== "ar") return unit;
  try {
    const symbol = new Intl.NumberFormat("ar-EG", { style: "currency", currency: found[1] })
      .formatToParts(1)
      .find((part) => part.type === "currency")
      ?.value.replace(/[‎‏؜]/g, "");
    return symbol ? `${symbol}${found[2] ?? ""}` : unit;
  } catch {
    return unit;
  }
}

/** How long a level takes to sink behind the next, or come back (the dialog-stack idea, calm: no overshoot). */
export const SINK_MS = 240;
/** A level under the top one: smaller, a little up, faded. */
export const SUNK = "translateY(-8px) scale(0.96)";

function where(locator: Record<string, string | number> | undefined): string | undefined {
  const { page, sheet, row, line } = locator ?? {};
  if (page !== undefined) return fill(t("page"), { page });
  if (sheet !== undefined && row !== undefined) return fill(t("sheetRow"), { sheet, row });
  if (row !== undefined) return fill(t("row"), { row });
  if (line !== undefined) return fill(t("line"), { line });
  return undefined;
}

/** A source with no date of its own is dated the day One received it or read it (Plan 5 Task 7), and says so. */
function datedLabel(how: string | number | undefined) {
  if (how === "received") return "sourceDatedReceived";
  if (how === "read") return "sourceDatedRead";
  return "sheetDated";
}

const valueText = (value: string, unit?: string | null) => `${formatDecimal(value)}${unit ? ` ${unitText(unit)}` : ""}`;
/** The figure left to right, then its unit in its own direction: «4,100 ج.م.» reads number first in Arabic too. */
const shown = (value: string, unit?: string | null) => (
  <span>
    <bdi dir="ltr">{formatDecimal(value)}</bdi>
    {unit && (
      <>
        {" "}
        <bdi dir="auto">{unitText(unit)}</bdi>
      </>
    )}
  </span>
);

/** The figure as a file may write it, for the mark to go round it alone: 39,850.50, 39850.50, 39850.5. */
export function figuresOf(value: string): string[] {
  const plain = value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
  return [...new Set([formatDecimal(value), value, plain, formatDecimal(plain)])];
}

type Head = { value: string; unit?: string | null };

function Level({
  projectId,
  numberId,
  cell,
  viewSource,
  onOpen,
  onHead,
  onClose,
}: {
  projectId: string;
  numberId: string | null;
  /** The first level only: what the viewer already knows of the number and its source. */
  cell?: NumberCell;
  viewSource?: Source;
  onOpen: (id: string) => void;
  onHead: (head: Head) => void;
  onClose: () => void;
}) {
  const [page, setPage] = useState(1);
  const [explained, setExplained] = useState<Explained>();
  const [failed, setFailed] = useState<Text>();
  const head = useRef(onHead);
  head.current = onHead;

  useEffect(() => {
    let live = true;
    setExplained(undefined);
    setFailed(undefined);
    if (numberId === null) return; // a number not in Project Records yet: a pending change's, or a card's row
    void deliverablesApi.explain(projectId, numberId, page).then((answer) => {
      if (!live) return;
      if (answer.ok) {
        setExplained(answer.data);
        head.current({ value: answer.data.number.value, unit: answer.data.number.currency ?? answer.data.number.unit });
      } else setFailed(answer.error);
    });
    return () => {
      live = false;
    };
  }, [projectId, numberId, page]);

  const source: Source | undefined = viewSource ?? explained?.source;
  const dated = cell?.dated ?? explained?.number.dated ?? source?.dated;
  const by = explained?.number.recorded_by;
  const calc = explained?.calculation;
  const fileName = viewSource?.file_name;
  const at = where(source?.locator);
  const fileId = source?.file_id;
  const sourcePage = source?.locator?.page;
  const chat = source?.kind === "chat";
  // worked out by the Calc Engine: it says so, in place of a formula as a title and whoever asked for the number
  const calculated = source?.kind === "calculation" || Boolean(calc);

  function openSource() {
    if (!fileId) return;
    // the file opens as the document, at its page; the card has done its job
    workspaceApi.open(`file:${fileId}`, typeof sourcePage === "number" ? { page: sourcePage } : {});
    onClose();
  }

  return (
    <>
      <section aria-label={t("sheetSource")} className="flex flex-col">
        <span className="text-xs text-slate">{t("sheetSource")}</span>
        {chat ? (
          <span>{t("sourceSaidInChat")}</span>
        ) : source?.kind === "calculation" ? (
          <span>{t("enteredByCalc")}</span>
        ) : source?.title ? (
          <FileName name={source.title} />
        ) : (
          !source && !failed && <span className="text-slate">{t("noSource")}</span>
        )}
        {source?.supplier && <span dir="auto">{fill(t("sourceSupplier"), { name: source.supplier })}</span>}
        {(fileName || at) && (
          // the file's name isolated (a name mixing Arabic and Latin keeps its order), then where in it
          <span className="text-slate">
            {fileName && <FileName name={fileName} />}
            {fileName && at && (language() === "ar" ? "، " : ", ")}
            {at && <bdi>{at}</bdi>}
          </span>
        )}
        {source?.quote && (
          <blockquote dir="auto" className="my-1 rounded bg-copper/9 px-2 py-1 ring-1 ring-inset ring-copper/25">
            {source.quote}
          </blockquote>
        )}
        {source?.locator?.covers === "supply" && <span className="text-copper">{t("supplyOnly")}</span>}
        {dated && <span>{fill(t(datedLabel(source?.locator?.dated_how)), { date: dayText(dated) })}</span>}
        {calculated ? source?.kind !== "calculation" && <span>{t("enteredByCalc")}</span> : by && <span>{whoEntered(by)}</span>}
        {fileId && (
          <button type="button" className="self-start rounded px-1 underline hover:text-copper" onClick={openSource}>
            {t(typeof sourcePage === "number" ? "sourceOpenPage" : "sourceOpenFile")}
          </button>
        )}
      </section>
      {failed && <p role="alert" className="text-copper">{pick(failed)}</p>}
      {calc && (
        <>
          <section className="flex flex-col">
            <span className="text-xs text-slate">{t("sheetFormula")}</span>
            <bdi dir="auto">{formulaText(calc.formula)}</bdi>
          </section>
          {calc.inputs.length > 0 && (
            <section className="flex flex-col">
              <span className="text-xs text-slate">{t("sheetInputs")}</span>
              <ul className="flex flex-col gap-1">
                {calc.inputs.map((input) => (
                  <li key={`${input.name}-${input.seq ?? ""}-${input.number}`} className="flex flex-col">
                    {input.calculated ? (
                      <button type="button" className="self-start underline hover:text-copper" onClick={() => onOpen(input.number)}>
                        <bdi dir="auto">{termText(input.name)}</bdi> = {shown(input.value, input.unit)}
                      </button>
                    ) : (
                      <span>
                        <bdi dir="auto">{termText(input.name)}</bdi> = {shown(input.value, input.unit)}
                      </span>
                    )}
                    <span dir="auto" className="text-slate">
                      {input.source.kind === "calculation" ? (
                        <bdi dir="auto">{formulaText(input.source.title)}</bdi> // worked out: its formula in words
                      ) : (
                        <FileName name={input.source.title} />
                      )}
                      {input.dated ? ` · ${fill(t("sheetDated"), { date: dayText(input.dated) })}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {calc.steps.length > 0 && (
            <section className="flex flex-col">
              <span className="text-xs text-slate">{t("sheetSteps")}</span>
              <ol className="flex flex-col">
                {calc.steps.map((step) => (
                  <li key={step.n}>
                    <bdi dir="ltr">
                      {step.n}. {formulaText(step.text)} = {formatDecimal(step.value)}
                      {step.unit ? ` ${unitText(step.unit)}` : ""}
                    </bdi>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {calc.pages > 1 && (
            <div className="flex items-center justify-between gap-2">
              <button type="button" disabled={page <= 1} className="rounded px-2 hover:bg-stone disabled:text-slate" onClick={() => setPage(page - 1)}>
                {t("sheetPreviousPage")}
              </button>
              <span>{fill(t("sheetPageOf"), { page: calc.page, pages: calc.pages })}</span>
              <button type="button" disabled={page >= calc.pages} className="rounded px-2 hover:bg-stone disabled:text-slate" onClick={() => setPage(page + 1)}>
                {t("sheetNextPage")}
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}

export type SourceCardProps = {
  projectId: string;
  cell: NumberCell;
  sources: Record<string, Source>;
  /** Where it stands inside its owner, when it has no number to stand by (`from`); with one it is placed itself. */
  style?: CSSProperties;
  /** Opened from the keyboard: focus moves in. A click leaves it where it was, so a sheet's arrows keep moving. */
  focus: boolean;
  onClose: () => void;
  /** The element the number was clicked in: the number glides from it into the header, and focus goes back to it. */
  from?: HTMLElement | null;
  /** What the number is: its column («الفئة», "Rate"). */
  label?: string;
};

/** Another number opened while one is open gets a card of its own: its levels and its glide start afresh. */
export function SourceCard(props: SourceCardProps) {
  const { cell } = props;
  return <Card key={`${cell.number_id ?? ""}|${cell.source ?? ""}|${cell.value}`} {...props} />;
}

function Card({ projectId, cell, sources, style, focus, onClose, from, label }: SourceCardProps) {
  const box = useRef<HTMLDivElement>(null);
  useScrollEdges(box); // a card taller than the room fades where it scrolls, never just cut
  const headValue = useRef<HTMLSpanElement>(null);
  const body = useRef<HTMLDivElement>(null);
  const levels = useRef<(HTMLDivElement | null)[]>([]);
  const [stack, setStack] = useState<(string | null)[]>([cell.number_id]); // the number shown, and the ones it was opened from
  const [heads, setHeads] = useState<Head[]>([{ value: cell.value, unit: cell.currency ?? cell.unit }]);
  const depth = useRef(1);
  const closed = useRef(false);
  const close = useRef(() => {});
  close.current = () => {
    if (closed.current) return;
    closed.current = true;
    if (from?.isConnected) from.focus({ preventScroll: true });
    onClose();
  };

  // the card reads in the direction and language of the words round its number, wherever it is drawn
  const [side] = useState(() => (from ? readingDirection(from) : undefined));
  const [lang] = useState(() => from?.closest<HTMLElement>("[lang]")?.lang || undefined);

  // It stands by its number (./place.ts) and keeps to it while the canvas pans or zooms or the chat scrolls: placed
  // again on each frame the number, the card or the window has moved or changed size.
  useLayoutEffect(() => {
    if (!from) return;
    let frame = 0;
    let last = "";
    const place = () => {
      const el = box.current;
      if (el && from.isConnected) {
        const at = from.getBoundingClientRect();
        const now = [at.top, at.left, at.width, at.height, el.offsetWidth, el.scrollHeight, innerWidth, innerHeight].join();
        if (now !== last) {
          last = now;
          const view = { width: innerWidth, height: innerHeight };
          const placed = placeCard(at, { width: el.offsetWidth, height: el.scrollHeight }, view, side === "rtl");
          el.style.top = `${placed.top}px`;
          el.style.left = `${placed.left}px`;
          el.style.maxHeight = `${placed.maxHeight}px`;
        }
      }
      if (typeof requestAnimationFrame === "function") frame = requestAnimationFrame(place);
    };
    place();
    return () => cancelAnimationFrame(frame);
  }, [from, side]);

  useEffect(() => {
    if (focus) box.current?.focus({ preventScroll: true });
  }, [focus]);

  // Escape closes it wherever the focus is (a click leaves focus outside, and WebKit never focuses a clicked button)
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      close.current();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  // The number glides from where it was clicked into the header; the rest fades in
  useLayoutEffect(() => {
    const figure = from?.querySelector("bdi") ?? from;
    if (figure && headValue.current) void flipFrom(figure.getBoundingClientRect(), headValue.current, readingDirection(headValue.current));
    if (body.current) void play(body.current, [{ opacity: 0 }, { opacity: 1 }], DUR.short);
    // once, on opening
  }, []);

  // A new level comes in on top and the one under it sinks behind; Back brings that one up again
  useLayoutEffect(() => {
    const now = stack.length;
    const before = depth.current;
    depth.current = now;
    if (now === before) return;
    const top = levels.current[now - 1];
    const under = levels.current[now - 2];
    if (now > before) {
      if (under) void play(under, [{ transform: "none", opacity: 1 }, { transform: SUNK, opacity: 0.5 }], SINK_MS);
      if (top) void play(top, [{ transform: "translateY(8px)", opacity: 0 }, { transform: "none", opacity: 1 }], SINK_MS);
    } else if (top) void play(top, [{ transform: SUNK, opacity: 0.5 }, { transform: "none", opacity: 1 }], SINK_MS);
  }, [stack.length]);

  const viewSource = cell.source !== null ? sources[cell.source] : undefined; // the view knows the file's name
  const head = heads[stack.length - 1] ?? heads[0]!;
  const back = heads[stack.length - 2];

  function open(id: string) {
    setStack((s) => [...s, id]);
    setHeads((h) => [...h.slice(0, stack.length), { value: "" }]);
  }
  function pop() {
    setStack((s) => s.slice(0, -1));
    setHeads((h) => h.slice(0, -1));
  }

  const card = (
    <div
      ref={box}
      role="dialog"
      aria-label={t("sheetSource")}
      tabIndex={-1}
      dir={side}
      lang={lang}
      style={from ? undefined : style}
      className={`${
        from ? "fixed z-[60] max-w-[calc(100vw-16px)] shadow-[0_2px_12px_rgb(14_15_18/0.1)]" : "absolute z-20 max-w-[90%]"
      } scroll-fade flex max-h-96 w-80 flex-col gap-2 overflow-auto rounded-md border border-slate bg-paper p-3 text-start text-ink outline-none`}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          event.preventDefault();
          close.current();
        }
      }}
      onMouseDown={(event) => event.stopPropagation()}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="flex min-w-0 flex-col">
          {label && (
            <span dir="auto" className="text-xs text-slate">
              {label}
            </span>
          )}
          <span ref={headValue} data-card-value className="inline-block self-start font-semibold">
            {head.value ? shown(head.value, head.unit) : <span className="text-slate">…</span>}
          </span>
        </span>
        <button type="button" className="rounded px-2 hover:bg-stone" onClick={() => close.current()}>
          {t("close")}
        </button>
      </div>
      {back && (
        <button type="button" className="self-start rounded px-2 hover:bg-stone" onClick={pop}>
          {fill(t("sourceBackTo"), { value: back.value ? valueText(back.value, back.unit) : "…" })}
        </button>
      )}
      <div ref={body} className="grid">
        {stack.map((numberId, i) => {
          const isTop = i === stack.length - 1;
          const under = i === stack.length - 2;
          return (
            <div
              key={`${i}-${numberId ?? ""}`}
              ref={(el) => {
                levels.current[i] = el;
              }}
              data-level={i}
              aria-hidden={isTop ? undefined : true}
              inert={!isTop}
              hidden={!isTop && !under}
              // the one under the top stays in sight, sunk behind it; the top covers it
              style={isTop ? undefined : { transform: SUNK, opacity: 0.5, pointerEvents: "none" }}
              className="col-start-1 row-start-1 flex flex-col gap-2 bg-paper"
            >
              <Level
                projectId={projectId}
                numberId={numberId}
                cell={i === 0 ? cell : undefined}
                viewSource={i === 0 ? viewSource : undefined}
                onOpen={open}
                onClose={() => close.current()}
                onHead={(h) => setHeads((all) => all.map((x, n) => (n === i ? h : x)))}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
  // in the top layer: above every frame, the chat and its message box, never cut by the box the number is in
  return from ? createPortal(card, document.body) : card;
}
