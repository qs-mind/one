// The tab underline: a 2 px Ink line under the chosen tab, measured from where the tabs really are, so it lands right
// in Arabic too; it glides (transform only) once placed, and with reduced motion it simply moves.
import { render, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { layout, motion } from "./testLayout";
import { TabUnderline } from "./TabUnderline";

function Tabs({ chosen, dir = "ltr" }: { chosen: string; dir?: "ltr" | "rtl" }) {
  return (
    <div role="tablist" dir={dir} className="relative flex">
      {["a", "b", "c"].map((k) => (
        <button key={k} type="button" role="tab" data-k={k} aria-selected={chosen === k}>
          {k}
        </button>
      ))}
      <TabUnderline />
    </div>
  );
}

const line = () => document.querySelector<HTMLElement>("[data-tab-underline]")!;
const at = () => ({ x: line().style.getPropertyValue("--x"), w: line().style.getPropertyValue("--w") });

describe("TabUnderline", () => {
  it("lands under the chosen tab and follows the choice", () => {
    motion(false);
    layout({ a: { left: 0, top: 0, width: 60, height: 32 }, b: { left: 64, top: 0, width: 80, height: 32 }, c: { left: 148, top: 0, width: 70, height: 32 } });
    const { rerender } = render(<Tabs chosen="a" />);
    expect(at()).toEqual({ x: "0px", w: "60" });
    rerender(<Tabs chosen="c" />);
    expect(at()).toEqual({ x: "148px", w: "70" });
    expect(line()).toHaveAttribute("aria-hidden", "true");
  });

  it("lands under the chosen tab in Arabic, where the first tab is on the right", () => {
    motion(false);
    layout({ a: { left: 158, top: 0, width: 60, height: 32 }, b: { left: 74, top: 0, width: 80, height: 32 }, c: { left: 0, top: 0, width: 70, height: 32 } });
    const { rerender } = render(<Tabs chosen="a" dir="rtl" />);
    expect(at()).toEqual({ x: "158px", w: "60" });
    rerender(<Tabs chosen="b" dir="rtl" />);
    expect(at()).toEqual({ x: "74px", w: "80" });
  });

  it("is placed at once, then glides; with reduced motion it never glides", async () => {
    motion(false);
    layout({ a: { left: 0, top: 0, width: 60, height: 32 } });
    render(<Tabs chosen="a" />);
    expect(line()).not.toHaveAttribute("data-ready"); // the first place shows without sliding in from the edge
    await waitFor(() => expect(line()).toHaveAttribute("data-ready"));
  });

  it("with reduced motion shows the end place at once and never glides", async () => {
    motion(true);
    layout({ b: { left: 64, top: 0, width: 80, height: 32 } });
    render(<Tabs chosen="b" />);
    expect(at()).toEqual({ x: "64px", w: "80" });
    await new Promise((done) => setTimeout(done, 40));
    expect(line()).not.toHaveAttribute("data-ready");
  });

  it("hides when no tab is chosen", () => {
    motion(false);
    render(<Tabs chosen="none" />);
    expect(line()).toHaveAttribute("data-hidden");
  });
});
