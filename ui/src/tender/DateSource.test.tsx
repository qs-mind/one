import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Source } from "@/conversation/parts";
import { renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { DateSource } from "./DateSource";

beforeEach(stubBrowser);
afterEach(resetPage);

const read: Source = { kind: "file", title: "Instructions to tenderers", file_id: "f1", locator: { page: 3 } };
const unsure: Source = { ...read, locator: { page: 1, ocr_low_confidence: true } };
const mine: Source = { kind: "engineer", title: "", locator: {}, dated: "2026-11-04" };

describe("DateSource", () => {
  it("opens the place the date was read, and marks an unsure OCR read", async () => {
    const onOpen = vi.fn();
    renderIn("ltr", <DateSource source={unsure} onOpen={onOpen} />);
    expect(screen.getByText("Read by OCR and not sure: check it")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Instructions to tenderers\W*, page \W?1/ }));
    expect(onOpen).toHaveBeenCalledWith(unsure);
  });

  it("leaves out the OCR mark for a sure read", () => {
    const { container } = renderIn("ltr", <DateSource source={read} onOpen={() => {}} />);
    expect(container).not.toHaveTextContent("OCR");
  });

  it("says the date is the engineer's own, with nothing to open", () => {
    renderIn("ltr", <DateSource source={mine} onOpen={() => {}} />);
    expect(screen.getByText("The date you gave")).toBeInTheDocument();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("is plain words when compact, with the short OCR mark", () => {
    const { container } = renderIn("ltr", <DateSource compact source={unsure} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(container).toHaveTextContent(/Instructions to tenderers\W*, page \W?1/);
    expect(screen.getByText("OCR not sure: check it")).toBeInTheDocument();
  });

  it("speaks Arabic in an Arabic page", () => {
    renderIn("rtl", <DateSource compact source={mine} />);
    expect(screen.getByText("التاريخ اللي إنت إديته")).toBeInTheDocument();
  });
});
