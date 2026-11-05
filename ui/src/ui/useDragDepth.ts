// A drop target's "files are over me", for its highlight. dragenter and dragleave come for every child the pointer
// crosses (enter the child, then leave the parent), so a plain on/off blinks; the target counts them instead: on with
// the first enter, off only when the count is back to zero, or on a drop. Only drags that carry files count.
import { type DragEvent, useRef, useState } from "react";

const carriesFiles = (event: DragEvent) => event.dataTransfer?.types?.includes("Files") ?? false;

export function useDragDepth(accepts: (event: DragEvent) => boolean = carriesFiles) {
  const [over, setOver] = useState(false);
  const depth = useRef(0);
  const handlers = {
    onDragEnter(event: DragEvent) {
      if (!accepts(event)) return;
      depth.current += 1;
      setOver(true);
    },
    onDragOver(event: DragEvent) {
      if (accepts(event)) event.preventDefault(); // the webview lets the files drop here
    },
    onDragLeave() {
      if (depth.current === 0) return;
      depth.current -= 1;
      if (depth.current === 0) setOver(false);
    },
    onDrop() {
      depth.current = 0;
      setOver(false);
    },
  };
  return { over, handlers };
}
