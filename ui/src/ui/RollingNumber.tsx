// A total that changes rolls its digits from the old value to the new one (docs/specs/2026-11-05-motion-design.md,
// motion 2): each digit that changed slides its old figure out and its new one in, 400 ms; separators and the digits
// that stayed never move. It rolls only on a change: the first render shows the value still, and nothing counts up
// from zero. It takes the text as the screen already formats it (a decimal string from the core, never passed through
// a float), so the digits and grouping are the locale's. At rest it is plain text; while it rolls, a screen reader
// reads the final text only.
import { useLayoutEffect, useRef, useState } from "react";
import { DUR, play, reducedMotion } from "./motion";

const DIGIT = /\p{Nd}/u;
const ZEROS = [0x30, 0x660, 0x6f0]; // Western, Arabic-Indic, Eastern Arabic-Indic

function digits(text: string): number[] {
  return [...text]
    .filter((c) => DIGIT.test(c))
    .map((c) => {
      const code = c.codePointAt(0)!;
      const zero = ZEROS.find((z) => code >= z && code <= z + 9);
      return zero === undefined ? code : code - zero;
    });
}

/** Whether `to` is more than `from`, read from their digits (the same format on both sides). */
function rises(from: string, to: string): boolean {
  const [a, b] = [digits(from), digits(to)];
  const larger = b.length !== a.length ? b.length > a.length : b.join(",") > a.join(",");
  const negative = /[-−]/.test(to);
  return negative ? !larger : larger;
}

type Roll = { from: string; up: boolean; n: number };

export function RollingNumber({ text }: { text: string }) {
  const last = useRef(text);
  const [roll, setRoll] = useState<Roll | null>(null);
  const face = useRef<HTMLSpanElement>(null);
  const latest = useRef(0);

  useLayoutEffect(() => {
    const from = last.current;
    last.current = text;
    if (from === text) return;
    if (reducedMotion() || typeof Element.prototype.animate !== "function") return setRoll(null);
    // a value that comes mid-roll starts again from the one before it, toward the newest
    setRoll({ from, up: rises(from, text), n: ++latest.current });
  }, [text]);

  useLayoutEffect(() => {
    const box = face.current;
    if (!roll || !box) return;
    const away = roll.up ? -100 : 100;
    const moves = [
      ...[...box.querySelectorAll("[data-roll-to]")].map((el) =>
        play(el, [{ transform: `translateY(${-away}%)` }, { transform: "translateY(0)" }], DUR.roll),
      ),
      ...[...box.querySelectorAll("[data-roll-from]")].map((el) =>
        play(el, [{ transform: "translateY(0)" }, { transform: `translateY(${away}%)` }], DUR.roll),
      ),
    ];
    void Promise.all(moves).then(() => {
      if (latest.current === roll.n) setRoll(null);
    });
  }, [roll]);

  if (!roll || last.current !== text) return <span>{text}</span>;

  const chars = [...text];
  const before = [...roll.from];
  return (
    <span className="relative">
      <span className="sr-only">{text}</span>
      <span ref={face} aria-hidden="true">
        {chars.map((c, i) => {
          const fromEnd = chars.length - 1 - i;
          const old = before[before.length - 1 - fromEnd];
          const key = `${roll.n}:${fromEnd}`;
          if (!DIGIT.test(c) || old === c) return <span key={key}>{c}</span>;
          return (
            <span key={key} data-roll="" className="roll-col">
              <span data-roll-to="" className="inline-block">
                {c}
              </span>
              {old !== undefined && DIGIT.test(old) && (
                <span data-roll-from="" className="roll-from" style={{ transform: `translateY(${roll.up ? -100 : 100}%)` }}>
                  {old}
                </span>
              )}
            </span>
          );
        })}
      </span>
    </span>
  );
}
