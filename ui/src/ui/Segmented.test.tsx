// The segmented control: a few options, one chosen, saved at once by the caller. A Stone thumb sits under the chosen
// option, measured from the real positions (so it lands right in Arabic), moved by transform only.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { Segmented } from "./Segmented";
import { layout, motion } from "./testLayout";

const options = [
  { value: "image", label: "Page" },
  { value: "text", label: "Text" },
] as const;

function Choice({ first = "image", onChange = () => {}, dir = "ltr" }: { first?: string; onChange?: (v: string) => void; dir?: "ltr" | "rtl" }) {
  const [value, setValue] = useState(first);
  return (
    <div dir={dir}>
      <Segmented
        label="Show"
        options={options}
        value={value}
        onChange={(next) => {
          setValue(next);
          onChange(next);
        }}
      />
    </div>
  );
}

const thumb = () => document.querySelector<HTMLElement>("[data-segment-thumb]")!;
const at = () => ({ x: thumb().style.getPropertyValue("--x"), w: thumb().style.width });

describe("Segmented", () => {
  it("is a radio group whose thumb lands under the chosen option", () => {
    motion(false);
    layout({ image: { left: 2, top: 2, width: 70, height: 28 }, text: { left: 72, top: 2, width: 70, height: 28 } });
    const change = vi.fn();
    render(<Choice onChange={change} />);
    expect(screen.getByRole("radiogroup", { name: "Show" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Page" })).toHaveAttribute("aria-checked", "true");
    expect(at()).toEqual({ x: "2px", w: "70px" });

    fireEvent.click(screen.getByRole("radio", { name: "Text" }));
    expect(change).toHaveBeenCalledWith("text");
    expect(screen.getByRole("radio", { name: "Text" })).toHaveAttribute("aria-checked", "true");
    expect(at()).toEqual({ x: "72px", w: "70px" });
  });

  it("in Arabic the first option is on the right, and the thumb lands there", () => {
    motion(false);
    layout({ image: { left: 72, top: 2, width: 70, height: 28 }, text: { left: 2, top: 2, width: 70, height: 28 } });
    render(<Choice dir="rtl" />);
    expect(at()).toEqual({ x: "72px", w: "70px" });
    fireEvent.click(screen.getByRole("radio", { name: "Text" }));
    expect(at()).toEqual({ x: "2px", w: "70px" });
  });

  it("moves with the arrow keys the way the page reads, focusing and choosing as it goes", () => {
    motion(false);
    const change = vi.fn();
    const { unmount } = render(<Choice onChange={change} />);
    const page = screen.getByRole("radio", { name: "Page" });
    expect(page).toHaveAttribute("tabindex", "0");
    expect(screen.getByRole("radio", { name: "Text" })).toHaveAttribute("tabindex", "-1");
    fireEvent.keyDown(page, { key: "ArrowRight" });
    expect(change).toHaveBeenLastCalledWith("text");
    expect(screen.getByRole("radio", { name: "Text" })).toHaveFocus();
    unmount();

    render(<Choice dir="rtl" onChange={change} />);
    fireEvent.keyDown(screen.getByRole("radio", { name: "Page" }), { key: "ArrowLeft" }); // in Arabic, left is onward
    expect(change).toHaveBeenLastCalledWith("text");
  });

  it("glides only after it is first placed; with reduced motion it never glides", async () => {
    motion(false);
    const { unmount } = render(<Choice />);
    expect(thumb()).not.toHaveAttribute("data-ready");
    await waitFor(() => expect(thumb()).toHaveAttribute("data-ready"));
    unmount();

    motion(true);
    render(<Choice />);
    await new Promise((done) => setTimeout(done, 40));
    expect(thumb()).not.toHaveAttribute("data-ready");
  });
});
