// A stand-in for Plan 6's sheet viewer in the live layer's tests: its locate finds row "3/02" only. Its own file,
// so a test's mock of ../sources can import it without importing the canvas (which imports the mocked module).
import { forwardRef, useImperativeHandle } from "react";
import type { ViewerHandle, ViewerProps } from "../types";

export const FakeViewer = forwardRef<ViewerHandle, ViewerProps>(function FakeViewer({ deliverableId }, ref) {
  useImperativeHandle(ref, () => ({ locate: (a) => (a.row === "3/02" ? new DOMRect(10, 40, 200, 20) : null) }));
  return <div data-testid={`viewer-${deliverableId}`} />;
});
