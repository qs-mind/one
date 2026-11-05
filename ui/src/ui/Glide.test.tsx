// The gliding highlight: one Stone block behind the row the pointer is on or the keyboard has reached, moving between
// rows instead of each row lighting up on its own. It follows hover, focus and a list's own selection (cmdk's
// data-selected), so arrow keys still drive it; with reduced motion it jumps.
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Glide } from "./Glide";
import { layout, motion } from "./testLayout";

const ROWS = {
  a: { left: 8, top: 0, width: 200, height: 36 },
  b: { left: 8, top: 40, width: 200, height: 36 },
  c: { left: 8, top: 80, width: 200, height: 52 },
};

function List({ dir = "ltr" }: { dir?: "ltr" | "rtl" }) {
  return (
    <ul data-testid="list" dir={dir}>
      {(["a", "b", "c"] as const).map((k) => (
        <li key={k}>
          <button type="button" data-k={k} data-glide-item>
            {k}
          </button>
        </li>
      ))}
      <Glide as="li" />
    </ul>
  );
}

const mark = () => document.querySelector<HTMLElement>("[data-glide]")!;
const at = () => ({
  x: mark().style.getPropertyValue("--x"),
  y: mark().style.getPropertyValue("--y"),
  h: mark().style.height,
  on: mark().hasAttribute("data-on"),
});

describe("Glide", () => {
  it("rests hidden, then sits behind the row the pointer is on", () => {
    motion(false);
    layout(ROWS);
    render(<List />);
    expect(mark()).toHaveAttribute("aria-hidden", "true");
    expect(at().on).toBe(false);
    fireEvent.pointerOver(screen.getByText("b"));
    expect(at()).toEqual({ x: "8px", y: "40px", h: "36px", on: true });
    fireEvent.pointerOver(screen.getByText("c"));
    expect(at()).toEqual({ x: "8px", y: "80px", h: "52px", on: true });
  });

  it("follows keyboard focus, and the list's own selection (cmdk's data-selected)", async () => {
    motion(false);
    layout(ROWS);
    render(<List />);
    screen.getByText("c").focus();
    expect(at()).toMatchObject({ y: "80px", on: true });
    screen.getByText("a").setAttribute("data-selected", "true");
    await waitFor(() => expect(at()).toMatchObject({ y: "0px", on: true }));
  });

  it("goes when the pointer leaves the list and nothing in it is focused or selected", () => {
    motion(false);
    layout(ROWS);
    render(<List />);
    fireEvent.pointerOver(screen.getByText("b"));
    fireEvent.pointerLeave(screen.getByTestId("list"));
    expect(at().on).toBe(false);
  });

  it("lands under the row in Arabic, measured from where the row really is", () => {
    motion(false);
    layout({ ...ROWS, b: { left: 24, top: 40, width: 200, height: 36 } });
    render(<List dir="rtl" />);
    fireEvent.pointerOver(screen.getByText("b"));
    expect(at()).toMatchObject({ x: "24px", y: "40px" });
  });

  it("appears in place without sliding in; with reduced motion it never glides", async () => {
    motion(false);
    layout(ROWS);
    const { unmount } = render(<List />);
    fireEvent.pointerOver(screen.getByText("b"));
    expect(mark()).not.toHaveAttribute("data-ready");
    await waitFor(() => expect(mark()).toHaveAttribute("data-ready"));
    unmount();

    motion(true);
    render(<List />);
    fireEvent.pointerOver(screen.getByText("b"));
    await new Promise((done) => setTimeout(done, 40));
    expect(mark()).not.toHaveAttribute("data-ready");
    expect(at()).toMatchObject({ y: "40px", on: true });
  });
});
