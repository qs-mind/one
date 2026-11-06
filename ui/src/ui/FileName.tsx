// A file name or a title, shown so that a name mixing Arabic and Latin reads in order. The whole name is isolated
// from the text around it and takes its direction from its own first letter; the extension goes in that direction
// too, so in an Arabic name its dot stays by the name, «xlsx.عينة» (isolated left to right, the dot went to the far
// end: «عينةxlsx.»).
// A name that starts in Arabic and ends in Latin words keeps those words with the extension as one left-to-right
// run: «جدول كميات - عينة اختبار (sample BOQ).xlsx» reads «جدول كميات - عينة اختبار» then «(sample BOQ).xlsx», never
// «.xlsx(sample BOQ)» (the bracket and the extension thrown to the wrong side). The core does the same for names in
// its sentences (core/qsone/copy.py, file_name).
// In a list or a title (`fit`) the name keeps to one line: a name too long for its place loses the end of its words
// to «…» while the extension stays whole after them, «جدول كميات - عينة اخ… (sample BOQ).xlsx», and the full name
// shows in a Tip when it is cut.
import { Tip } from "./Tip";

const EXTENSION = /(\.[A-Za-z0-9]{1,8})$/;
const ARABIC = /[؀-ۿݐ-ݿࡰ-ࣿﭐ-﷿ﹰ-﻿]/;
const STRONG = /[A-Za-zÀ-ɏ؀-ۿݐ-ݿࡰ-ࣿﭐ-﷿ﹰ-﻿]/;
const LATIN = /[A-Za-z]/;

export function splitName(name: string): [stem: string, extension: string] {
  const found = EXTENSION.exec(name);
  return found && found.index > 0 ? [name.slice(0, found.index), found[1]!] : [name, ""];
}

/** The name in three runs: the words as they read (`head`), the Latin words at the end of a name that starts in
 * Arabic (`tail`, which goes left to right with the extension), and the extension. */
export function nameParts(name: string): { head: string; tail: string; extension: string } {
  const [stem, extension] = splitName(name);
  const first = STRONG.exec(stem)?.[0];
  let last = -1;
  for (let i = stem.length - 1; i >= 0; i--) {
    if (ARABIC.test(stem[i]!)) {
      last = i;
      break;
    }
  }
  const rest = stem.slice(last + 1);
  if (!first || !ARABIC.test(first) || last < 0 || !LATIN.test(rest)) return { head: stem, tail: "", extension };
  const space = rest.length - rest.trimStart().length;
  return { head: stem.slice(0, last + 1 + space), tail: rest.slice(space), extension };
}

/** Whether a fitted name is cut short on the screen now. */
function cut(el: Element): boolean {
  return [...el.querySelectorAll<HTMLElement>("[data-cut]")].some((part) => part.scrollWidth > part.clientWidth + 1);
}

export function FileName({ name, className = "", fit = false }: { name: string; className?: string; fit?: boolean }) {
  const { head, tail, extension } = nameParts(name);
  if (fit) {
    const spaced = /\s$/.test(head);
    const direction = ARABIC.test(STRONG.exec(name)?.[0] ?? "") ? "rtl" : "ltr";
    return (
      <Tip label={name} when={cut}>
        <bdi dir={direction} data-file-name className={`inline-flex min-w-0 max-w-full ${className}`}>
          <span data-cut dir={direction} className="min-w-0 truncate">
            {head}
          </span>
          {tail ? (
            <bdi dir="ltr" className={`inline-flex min-w-0 shrink-[0.25] ${spaced ? "ms-[0.3em]" : ""}`}>
              <span data-cut className="min-w-0 truncate">
                {tail}
              </span>
              {extension && <span className="shrink-0 whitespace-nowrap">{extension}</span>}
            </bdi>
          ) : (
            extension && <span className="shrink-0 whitespace-nowrap">{extension}</span>
          )}
        </bdi>
      </Tip>
    );
  }
  return (
    <bdi dir="auto" className={className || undefined}>
      {head}
      {tail ? (
        <bdi dir="ltr">
          {tail}
          {extension && <span className="whitespace-nowrap">{extension}</span>}
        </bdi>
      ) : (
        extension && <span className="whitespace-nowrap">{extension}</span>
      )}
    </bdi>
  );
}
