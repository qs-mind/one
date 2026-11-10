import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { P2, server, startFakeCore } from "@/api/fakeCore";
import type { Explained } from "@/deliverables/types";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { workspaceApi } from "@/workspace/api";
import { SourcePanel } from "./SourcePanel";

startFakeCore();
beforeEach(stubBrowser);
afterEach(resetPage);

// A number and its source as the core's explain sends them; titles and values are sample data.
const explained: Explained = {
  number: {
    id: "n1",
    item: { id: "i1", code: "3/02", kind: "rate" },
    name: "rate",
    value: "6480",
    unit: null,
    currency: "EGP",
    dated: "2026-11-02",
    recorded_at: "2026-11-02T08:00:00+00:00",
    recorded_by: "Lead QS",
    current: true,
    replaced_by: null,
    reason: null,
  },
  source: { id: "s1", kind: "sample", title: "Supplier quote (sample)", file_id: "f1", locator: { page: 2 }, url: null, dated: "2026-11-02" },
  calculation: { id: "c1", formula: "concrete + steel + formwork + labour", unit: "EGP", inputs: [], steps: [], stale: false, page: 1, pages: 1 },
};

const cell = { value: "6480", currency: "EGP", number_id: "n1", source: "s1", dated: "2026-11-02" };

describe("a number's source under the sheet", () => {
  it("shows the value, how it was made and where it comes from, and opens the file", async () => {
    server.use(http.get(`*/api/projects/${P2}/numbers/n1/explain`, () => HttpResponse.json(explained)));
    const open = vi.spyOn(workspaceApi, "open");
    const onClose = vi.fn();
    renderIn("ltr", <SourcePanel projectId={P2} asked={{ cell, label: "Rate of item 3/02", sources: {} }} onClose={onClose} />);
    const panel = await screen.findByRole("region", { name: "Where the number comes from" });
    expect(panel).toHaveTextContent("Rate of item 3/02");
    expect(panel).toHaveTextContent("6480");
    expect(await screen.findByText(/Worked out:/)).toHaveTextContent("concrete + steel");
    expect(screen.getByText(/Source:/)).toHaveTextContent("Supplier quote (sample)");
    expect(screen.getByText("Sample data")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Open the source" }));
    expect(open).toHaveBeenCalledWith("file:f1", expect.objectContaining({ page: 2 }));
    await userEvent.click(screen.getByRole("button", { name: "Close the source" }));
    expect(onClose).toHaveBeenCalled();
    open.mockRestore();
  });

  it("says so when the number has no source", async () => {
    renderIn("rtl", <SourcePanel projectId={P2} asked={{ cell: { ...cell, number_id: null, source: null }, label: "سعر", sources: {} }} onClose={() => {}} />);
    expect(await screen.findByText("الرقم ده لسه مالوش مصدر.")).toBeTruthy();
  });
});
