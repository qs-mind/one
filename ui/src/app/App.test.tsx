import { act, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it } from "vitest";
import { server, startFakeCore } from "@/api/fakeCore";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { currentZoom } from "@/ui/scale";
import { App } from "./App";

startFakeCore();
beforeEach(stubBrowser);
afterEach(resetPage);

it("zooms with Ctrl and = - 0 on any place, kept in the core as look.zoom", async () => {
  const saved: unknown[] = [];
  server.use(
    http.patch("*/api/settings/look.zoom", async ({ request }) => {
      saved.push(await request.json());
      return new HttpResponse(null, { status: 503 });
    }),
  );
  renderIn("rtl", <App />);
  const press = (code: string) =>
    act(() => void document.body.dispatchEvent(new KeyboardEvent("keydown", { code, ctrlKey: true, bubbles: true, cancelable: true })));
  press("Equal");
  expect(currentZoom()).toBe(1.1);
  expect(document.documentElement.style.fontSize).toBe("110%");
  await waitFor(() => expect(saved).toEqual([{ value: "1.1" }]));
  press("Digit0");
  expect(document.documentElement.style.fontSize).toBe("100%");
});
