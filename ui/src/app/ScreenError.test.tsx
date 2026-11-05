import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { ScreenError } from "./ScreenError";

function Broken(): never {
  throw new Error("sample render error");
}

afterEach(() => vi.restoreAllMocks());

describe("ScreenError", () => {
  it("shows the screen while nothing fails", () => {
    render(<ScreenError>screen</ScreenError>);
    expect(screen.getByText("screen")).toBeInTheDocument();
  });

  it("a render error shows both languages and Reload, never a blank window", () => {
    setLanguage("ar");
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ScreenError>
        <Broken />
      </ScreenError>,
    );
    expect(screen.getByText(texts.screenFailed.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.screenFailed.en)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.reload.ar })).toBeInTheDocument();
  });
});
