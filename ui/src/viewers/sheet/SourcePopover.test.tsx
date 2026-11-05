import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { NumberCell, Source } from "../../deliverables/types";
import { fill, setLanguage, texts } from "../../i18n";
import { dayText } from "../../sources/SourceCard";
import { SourcePopover } from "./SourcePopover";

const DAY = "2026-11-01";

// A number and its source as the core's explain sends them; titles and values are sample data.
function explained(source: Source & { id: string }) {
  return {
    number: {
      id: "n1",
      item: { id: "i1", code: "03/02", kind: "boq_item" },
      name: "rate",
      value: "39850.50",
      unit: null,
      currency: "EGP",
      dated: DAY,
      recorded_at: `${DAY}T08:00:00+00:00`,
      recorded_by: "lead_qs",
      current: true,
      replaced_by: null,
      reason: null,
    },
    source: { file_id: null, url: null, dated: DAY, ...source },
    calculation: null,
  };
}

function popover(how: string | undefined) {
  const locator: Source["locator"] = how ? { page: 3, dated_how: how } : { page: 3 };
  const source: Source = { kind: "quote", title: "عرض سعر - عينة", file_name: "عرض سعر - عينة.pdf", locator, dated: DAY };
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => Response.json(explained({ id: "s1", ...source }))),
  );
  const cell: NumberCell = { value: "39850.50", currency: "EGP", number_id: "n1", source: "s1", dated: DAY };
  return render(
    <SourcePopover projectId="p1" cell={cell} sources={{ s1: source }} style={{}} focus={false} onClose={() => undefined} />,
  );
}

beforeEach(() => setLanguage("ar"));

describe("SourcePopover dates", () => {
  it("an undated file's number says it is the date One received it", async () => {
    const { unmount } = popover("received");
    expect(await screen.findByText(fill(texts.sourceDatedReceived.ar, { date: dayText(DAY) }))).toBeInTheDocument();
    expect(screen.queryByText(fill(texts.sheetDated.ar, { date: dayText(DAY) }))).toBeNull();
    unmount();
    setLanguage("en"); // the viewer around it re-renders it in the new language
    popover("received");
    expect(await screen.findByText(fill(texts.sourceDatedReceived.en, { date: dayText(DAY) }))).toBeInTheDocument();
  });

  it("a page or a Connector reply with no date of its own says it is the date One read it", async () => {
    popover("read");
    expect(await screen.findByText(fill(texts.sourceDatedRead.ar, { date: dayText(DAY) }))).toBeInTheDocument();
    expect(screen.queryByText(fill(texts.sheetDated.ar, { date: dayText(DAY) }))).toBeNull();
  });

  it("a document's own date stays as it was", async () => {
    for (const how of ["document", undefined]) {
      const { unmount } = popover(how);
      expect(await screen.findByText(fill(texts.sheetDated.ar, { date: dayText(DAY) }))).toBeInTheDocument();
      unmount();
    }
  });

  it("every new label exists in both languages", () => {
    for (const key of ["sourceDatedReceived", "sourceDatedRead"] as const) {
      expect(texts[key].en, key).not.toBe(texts[key].ar);
      expect(texts[key].ar, key).toContain("{date}");
    }
    expect(texts.sourceDatedReceived.ar).toContain("تاريخ الاستلام");
    expect(texts.sourceDatedRead.ar).toContain("تاريخ القراية");
  });
});
