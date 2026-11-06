import { useRef, useState, type PointerEvent, type ReactNode } from "react";
import type { PdfBox } from "../../deliverables/types";

/** Physical left/top coordinates are independent of the surrounding reading direction.
 * The SVG scales with the image, regardless of its download width or CSS display width. */
export function PdfRegions({ width, height, boxes, onSelect, children }: {
  width: number;
  height: number;
  boxes: PdfBox[];
  onSelect?: (box: PdfBox) => void;
  children: ReactNode;
}) {
  const start = useRef<[number, number] | null>(null);
  const pointer = useRef<number | null>(null);
  const [draft, setDraft] = useState<PdfBox | null>(null);

  function point(event: PointerEvent<SVGSVGElement>): [number, number] {
    const rect = event.currentTarget.getBoundingClientRect();
    return [
      Math.max(0, Math.min(width, (event.clientX - rect.left) * width / rect.width)),
      Math.max(0, Math.min(height, (event.clientY - rect.top) * height / rect.height)),
    ];
  }
  function region(end: [number, number]): PdfBox {
    return [
      Math.min(start.current![0], end[0]), Math.min(start.current![1], end[1]),
      Math.max(start.current![0], end[0]), Math.max(start.current![1], end[1]),
    ];
  }
  function cancel() {
    start.current = null;
    pointer.current = null;
    setDraft(null);
  }

  return (
    <div className="relative" style={{ direction: "ltr" }}>
      {children}
      <svg
        data-testid="pdf-regions"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="absolute inset-0 h-full w-full text-copper"
        style={{ pointerEvents: onSelect ? "auto" : "none", touchAction: onSelect ? "none" : "auto" }}
        onPointerDown={(event) => {
          if (!onSelect || event.button !== 0 || start.current) return;
          start.current = point(event);
          pointer.current = event.pointerId;
          event.currentTarget.setPointerCapture?.(event.pointerId);
          setDraft(region(start.current));
        }}
        onPointerMove={(event) => {
          if (start.current && event.pointerId === pointer.current) setDraft(region(point(event)));
        }}
        onPointerUp={(event) => {
          if (!start.current || event.pointerId !== pointer.current) return;
          const box = region(point(event));
          cancel();
          event.currentTarget.releasePointerCapture?.(event.pointerId);
          if (box[2] - box[0] >= 1 && box[3] - box[1] >= 1) onSelect?.(box);
        }}
        onPointerCancel={cancel}
        onLostPointerCapture={cancel}
      >
        {[...boxes, ...(draft ? [draft] : [])].map((box, index) => (
          <rect
            key={index}
            x={box[0]} y={box[1]} width={box[2] - box[0]} height={box[3] - box[1]}
            fill="currentColor" fillOpacity="0.09" stroke="currentColor" strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        ))}
      </svg>
    </div>
  );
}
