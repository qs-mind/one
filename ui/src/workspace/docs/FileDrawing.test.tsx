import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { fakeSources } from "../../project/fake";
import { setLanguage } from "../../i18n";
import { FileDoc } from "./FileDoc";

test("drawings show a plain preview notice with extracted text", async () => {
  setLanguage("en");
  const sources = fakeSources({ files: [{ id: "drawing", name: "sample.dwg", status: "read", note: null, replaces: null }] });
  render(<FileDoc sources={sources} fileId="drawing" />);
  expect(await screen.findByText(/A drawing preview is not available yet/)).toBeInTheDocument();
});
