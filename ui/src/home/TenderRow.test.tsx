import { screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { TenderRow } from "./TenderRow";

beforeEach(stubBrowser);
afterEach(resetPage);

const today = new Date(2026, 10, 10);
const row: Schemas["TenderRow"] = {
  project_id: "p1",
  name: "Clinic",
  name_pair: null,
  confidential: false,
  sample: false,
  state: "working",
  line: null,
  blocked: null,
  stage: null,
  stages: [],
  submission_date: "2026-11-16",
  submission_source: { kind: "file", title: "Addendum 2", file_id: "f5", locator: { page: 1, ocr_low_confidence: true } },
  waiting: 0,
  files_read: 1,
  files_total: 1,
};

const draw = (it: Schemas["TenderRow"]) =>
  renderIn(
    "ltr",
    <MemoryRouter>
      <TenderRow row={it} today={today} near={false} samplePill />
    </MemoryRouter>,
  );

describe("TenderRow's submission date source", () => {
  it("names where the date was read, as words inside the row's one link", () => {
    draw(row);
    const link = screen.getByRole("link");
    expect(link).toHaveTextContent(/Addendum 2\W*, page \W?1/);
    expect(link).toHaveTextContent("OCR not sure: check it");
    expect(link.querySelector("button")).toBeNull();
  });

  it("says when the date is the engineer's own", () => {
    draw({ ...row, submission_source: { kind: "engineer", title: "", locator: {} } });
    expect(screen.getByRole("link")).toHaveTextContent("The date you gave");
  });

  it("shows no source without a date, or once the tender is finished", () => {
    const { unmount } = draw({ ...row, submission_date: null });
    expect(screen.getByRole("link")).not.toHaveTextContent("Addendum");
    unmount();
    draw({ ...row, state: "finished" });
    expect(screen.getByRole("link")).not.toHaveTextContent("Addendum");
  });
});
