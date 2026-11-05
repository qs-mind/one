// One SVG over the whole window for the source line, the source mark and the row flash: fixed, never in the way of
// the pointer, and hidden from screen readers (the number and its source say everything in words). It multiplies
// with the page, so a Stone flash tints a row and leaves its words as they are.

const SVG = "http://www.w3.org/2000/svg";

export function overlay(): SVGSVGElement {
  const found = document.querySelector<SVGSVGElement>("svg[data-source-overlay]");
  if (found) return found;
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("data-source-overlay", "");
  svg.setAttribute("aria-hidden", "true");
  Object.assign(svg.style, {
    position: "fixed",
    inset: "0",
    width: "100%",
    height: "100%",
    pointerEvents: "none",
    overflow: "visible",
    zIndex: "60",
    mixBlendMode: "multiply", // on Paper a tint or a stroke shows its own colour, and words under a tint stay
  });
  document.body.append(svg);
  return svg;
}

/** A stroke that draws itself: `pathLength` 1, so the dash offset runs from 1 (nothing) to 0 (whole) whatever its
 * real length. Starts drawn: the caller animates from 1. */
export function stroke(d: string, color: string, width: number, kind: string): SVGPathElement {
  const path = document.createElementNS(SVG, "path");
  path.setAttribute("d", d);
  path.setAttribute("pathLength", "1");
  path.setAttribute("fill", "none");
  path.setAttribute("data-source", kind);
  Object.assign(path.style, {
    stroke: color,
    strokeWidth: String(width),
    strokeDasharray: "1",
    strokeDashoffset: "0",
    strokeLinecap: "round",
    strokeLinejoin: "round",
  });
  overlay().append(path);
  return path;
}

export function rectShape(r: DOMRect, color: string, kind: string): SVGRectElement {
  const rect = document.createElementNS(SVG, "rect");
  for (const [k, v] of Object.entries({ x: r.left, y: r.top, width: r.width, height: r.height }))
    rect.setAttribute(k, String(v));
  rect.setAttribute("data-source", kind);
  rect.style.fill = color;
  overlay().prepend(rect); // under the marks
  return rect;
}
