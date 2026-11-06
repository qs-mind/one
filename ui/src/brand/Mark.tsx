// The QS Mind mark, exactly as desktop/app-icon.svg has it (website/brand/qs-mind/mark/qs-mind-mark.svg), without the
// icon's Paper backing. It may draw itself and fill its face; it never rotates, glows, casts a shadow or sits on a
// tile. Drawn: the sphere's lines draw in (stroke-dashoffset), the far ones first, so the drawing closes on the face,
// which then fills copper. The animations are CSS (styles.css, .mark-line and .mark-face): their resting style is
// the whole mark, so reduced motion, turned on even mid-drawing, shows it whole at once.
import { type CSSProperties, useId } from "react";

const SPHERE =
  "M18 109.32L31.22 171.34M18 109.32L31.63 138.83M18 109.32L41.86 84.2M18 109.32L43.74 51.39M31.22 171.34L31.63 138.83M31.22 171.34L63.25 184.55M31.22 171.34L78.35 213.75M31.63 138.83L41.86 84.2M31.63 138.83L63.25 184.55M31.63 138.83L69.83 130.69M41.86 84.2L43.74 51.39M41.86 84.2L69.83 130.69M41.86 84.2L75.43 40.26M41.86 84.2L95.57 72.76M43.74 51.39L75.43 40.26M43.74 51.39L98.61 19.66M63.25 184.55L69.83 130.69M63.25 184.55L78.35 213.75M63.25 184.55L111.82 210.98M63.25 184.55L116.96 173.1M69.83 130.69L95.57 72.76M69.83 130.69L116.96 173.1M69.83 130.69L123.01 119.36M75.43 40.26L95.57 72.76M75.43 40.26L98.61 19.66M75.43 40.26L130.64 32.86M78.35 213.75L111.82 210.98M78.35 213.75L141.39 220.34M95.57 72.76L123.01 119.36M95.57 72.76L130.64 32.86M95.57 72.76L158.61 79.35M98.61 19.66L130.64 32.86M98.61 19.66L161.65 26.25M111.82 210.98L116.96 173.1M111.82 210.98L141.39 220.34M111.82 210.98L165.25 195.22M116.96 173.1L123.01 119.36M116.96 173.1L165.25 195.22M116.96 173.1L171.83 141.37M123.01 119.36L158.61 79.35M123.01 119.36L171.83 141.37M130.64 32.86L158.61 79.35M130.64 32.86L161.65 26.25M130.64 32.86L182.68 51.49M141.39 220.34L165.25 195.22M141.39 220.34L196.26 188.61M158.61 79.35L171.83 141.37M158.61 79.35L182.68 51.49M158.61 79.35L206.9 101.48M161.65 26.25L182.68 51.49M161.65 26.25L208.78 68.66M165.25 195.22L171.83 141.37M165.25 195.22L196.26 188.61M165.25 195.22L205.17 157M171.83 141.37L205.17 157M171.83 141.37L206.9 101.48M182.68 51.49L206.9 101.48M182.68 51.49L208.78 68.66M196.26 188.61L205.17 157M196.26 188.61L222 130.68M205.17 157L206.9 101.48M205.17 157L222 130.68M206.9 101.48L208.78 68.66M206.9 101.48L222 130.68M208.78 68.66L222 130.68";
const FACE = "182.68,51.49 206.9,101.48 158.61,79.35";

/** The lines draw in 600 ms in all: each takes LINE_MS, starting up to DRAW_STAGGER_MS apart; then the face fills. */
const LINE_MS = 360;
const DRAW_STAGGER_MS = 240;
export const DRAW_MS = LINE_MS + DRAW_STAGGER_MS;
export const FILL_MS = 200;

/** Each line's ends, its length, and when it starts drawing (ms): the farthest from the face first. */
const LINES = (() => {
  const [fx, fy] = [182.73, 77.44]; // the face's centre
  const lines = SPHERE.slice(1)
    .split("M")
    .map((segment) => {
      const [x1, y1, x2, y2] = segment.split(/[ L]/).map(Number) as [number, number, number, number];
      return { d: `M${segment}`, length: Math.hypot(x2 - x1, y2 - y1), far: Math.hypot((x1 + x2) / 2 - fx, (y1 + y2) / 2 - fy) };
    });
  const farthest = Math.max(...lines.map((line) => line.far));
  return lines.map((line) => ({ ...line, delay: Math.round((1 - line.far / farthest) * DRAW_STAGGER_MS) }));
})();

export function Mark({ draw = false, size = 24, className = "shrink-0" }: { draw?: boolean; size?: number; className?: string }) {
  const face = `qs-mind-face-${useId()}`;
  return (
    <svg
      viewBox="0 0 240 240"
      width={size}
      height={size}
      aria-hidden="true"
      className={className}
      data-mark=""
      data-draw={draw ? "" : undefined}
      // drawn in rem, so it follows the screen's scale (ui/scale.ts); `size` is its px at 100 %
      style={{
        width: `${size / 16}rem`,
        height: `${size / 16}rem`,
        ...(draw ? ({ "--line-ms": `${LINE_MS}ms`, "--fill-at": `${DRAW_MS}ms`, "--fill-ms": `${FILL_MS}ms` } as CSSProperties) : {}),
      }}
    >
      <defs>
        <linearGradient id={face} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#F0A35A" />
          <stop offset="1" stopColor="#C0582A" />
        </linearGradient>
      </defs>
      <polygon className="mark-face" points={FACE} fill={`url(#${face})`} />
      {draw ? (
        <g fill="none" stroke="#0E0F12" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round">
          {LINES.map((line) => (
            <path
              key={line.d}
              className="mark-line"
              d={line.d}
              style={
                {
                  "--len": `${line.length}`,
                  animationDelay: `${line.delay}ms`,
                } as CSSProperties
              }
            />
          ))}
        </g>
      ) : (
        <path d={SPHERE} fill="none" stroke="#0E0F12" strokeWidth="4.6" strokeLinecap="round" strokeLinejoin="round" />
      )}
    </svg>
  );
}
