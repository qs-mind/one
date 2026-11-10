// The fold of a reply (screen need S82): its first four lines show, the rest waits under Details. A line is a line
// of the Markdown that holds text; blank lines do not count. A fenced block or a table is never cut in two: the fold
// moves to its end.
export const SHOWN_LINES = 4;

export function fold(text: string, shown = SHOWN_LINES): { head: string; rest: string } {
  const lines = text.split("\n");
  let counted = 0;
  let fence = false;
  for (let index = 0; index < lines.length; index++) {
    const line = lines[index]!;
    if (/^\s*(```|~~~)/.test(line)) fence = !fence;
    if (line.trim() !== "") counted++;
    const next = lines[index + 1];
    const inTable = /^\s*\|/.test(line) && next !== undefined && /^\s*\|/.test(next);
    if (counted >= shown && !fence && !inTable) {
      const rest = lines.slice(index + 1).join("\n").trim();
      return { head: lines.slice(0, index + 1).join("\n").trimEnd(), rest };
    }
  }
  return { head: text.trimEnd(), rest: "" };
}
