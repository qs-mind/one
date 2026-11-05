// The message box's two quiet chips, for the Lead QS of the next Brief: the model (a small card of the models the
// engineer's AI links give, above the box) and the effort (each click moves to the next level: no list). Both are real:
// what they show is what the message sends. A model that takes no effort shows no effort chip.
import { type KeyboardEvent, type RefObject, useRef, useState } from "react";
import { fill, t } from "../i18n";
import { type Choice, type Effort, keyOf, type ModelCard } from "../settings/AiSettings";
import { Glide } from "../ui/Glide";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";

/** Slate, borderless, no fill until hovered; a visible ring for the keyboard. */
export const chip =
  "flex h-8 min-w-0 items-center gap-1.5 rounded-full px-2.5 text-xs text-slate transition-colors duration-150 ease-out hover:bg-stone hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ink";

/** One plain glyph for every model (no company's mark): a block, as in a building's. */
function ModelGlyph() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" aria-hidden="true" className="shrink-0">
      <path d="M8 1.75 13.5 4.9v6.2L8 14.25 2.5 11.1V4.9z" />
      <path d="M2.5 4.9 8 8.05l5.5-3.15M8 8.05v6.2" />
    </svg>
  );
}

function Check() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className="ms-auto shrink-0">
      <path d="m3.5 8.5 3 3 6-7" />
    </svg>
  );
}

export function ModelChip({
  sheet,
  current,
  onPick,
  onOpenChange,
  above,
}: {
  sheet: ModelCard[];
  current: ModelCard | undefined;
  onPick(choice: Choice): void;
  onOpenChange(open: boolean): void;
  /** The card opens above this (the whole box), so it never covers what is written. */
  above: RefObject<HTMLElement | null>;
}) {
  const [open, setOpen] = useState(false);
  const [offset, setOffset] = useState(8);
  const trigger = useRef<HTMLButtonElement>(null);
  const change = (next: boolean) => {
    // 8px above the box's top edge, not the chip's
    const box = above.current?.getBoundingClientRect().top;
    const own = trigger.current?.getBoundingClientRect().top;
    if (next && box !== undefined && own !== undefined) setOffset(own - box + 8);
    setOpen(next);
    onOpenChange(next);
  };
  const name = current?.name ?? "";

  function move(event: KeyboardEvent<HTMLDivElement>) {
    const items = [...event.currentTarget.querySelectorAll<HTMLElement>("[role='menuitemradio']")];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const to = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: items.length - 1 }[event.key];
    if (to === undefined) return;
    event.preventDefault();
    items[(to + items.length) % items.length]?.focus();
  }

  return (
    <Popover open={open} onOpenChange={change}>
      <PopoverTrigger asChild>
        <button ref={trigger} type="button" aria-label={fill(t("modelChip"), { name })} title={name} className={chip}>
          <ModelGlyph />
          <span dir="auto" className="truncate">
            {name}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        sideOffset={offset}
        data-composer-pop
        className="composer-pop w-64 p-1.5!"
        onOpenAutoFocus={(event) => {
          // the model in use takes the focus, as a menu's checked item does
          event.preventDefault();
          (event.currentTarget as HTMLElement).querySelector<HTMLElement>("[aria-checked='true'], [role='menuitemradio']")?.focus();
        }}
      >
        <div role="menu" aria-label={t("models")} onKeyDown={move} className="relative isolate flex max-h-72 flex-col overflow-y-auto">
          {sheet.map((card) => {
            const checked = current !== undefined && keyOf(card) === keyOf(current);
            return (
              <button
                key={keyOf(card)}
                type="button"
                role="menuitemradio"
                aria-checked={checked}
                onClick={() => {
                  onPick({ connector: card.connector, model: card.model });
                  change(false);
                }}
                className={`flex min-h-9 items-center gap-2.5 rounded-[10px] px-2.5 text-start text-sm transition-colors duration-150 ease-out focus-visible:outline-none ${checked ? "text-ink" : "text-slate hover:text-ink"}`}
              >
                <ModelGlyph />
                <span dir="auto" className="truncate">
                  {card.name}
                </span>
                {checked && <Check />}
              </button>
            );
          })}
          <Glide />
        </div>
      </PopoverContent>
    </Popover>
  );
}

type Shown = Effort | "auto";
const label = (level: Shown) => t(`effort${level}` as const);

/** Three bars, as a signal's: as many filled as the level (none for the model's own). They mirror in Arabic. */
function Bars({ filled }: { filled: number }) {
  return (
    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true" className="shrink-0 rtl:-scale-x-100">
      {[4, 7, 10].map((height, i) => (
        <rect
          key={height}
          x={1 + i * 4}
          y={11 - height}
          width="2.5"
          height={height}
          rx="1"
          fill="currentColor"
          className={`transition-opacity duration-200 ease-out ${i < filled ? "opacity-100" : "opacity-25"}`}
        />
      ))}
    </svg>
  );
}

/** Each click moves straight to the next level (Low, Medium, High, then Low again); the bars fill and the word
 * cross-fades in place. "Auto" (the model's own, nothing sent) shows only until the first click. */
export function EffortChip({ levels, shown, onNext }: { levels: Effort[]; shown: Shown; onNext(level: Effort): void }) {
  const at = shown === "auto" ? -1 : levels.indexOf(shown);
  const next = levels[(at + 1) % levels.length]!;
  const now = shown === "auto" ? `${label("auto")} (${t("effortAutoHelp")})` : label(shown);
  const name = fill(t("effortChip"), { level: now, next: label(next) });
  const words: Shown[] = shown === "auto" ? ["auto", ...levels] : levels;
  return (
    <button type="button" aria-label={name} title={name} onClick={() => onNext(next)} className={chip}>
      <Bars filled={at + 1} />
      {/* every word in one cell, so the chip keeps its width and the words cross-fade */}
      <span className="grid" aria-hidden="true">
        {words.map((level) => (
          <span
            key={level}
            className={`col-start-1 row-start-1 transition-opacity ease-out ${level === shown ? "opacity-100 delay-[60ms] duration-150" : "opacity-0 duration-100"}`}
          >
            {label(level)}
          </span>
        ))}
      </span>
    </button>
  );
}
