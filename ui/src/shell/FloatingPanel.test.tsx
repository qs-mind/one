// The floating panel closes on a click outside it, but only one that both starts and ends outside: selecting text or
// dragging a scroll bar from inside it out past its edge keeps it open, and so does a press outside let go inside.
import { fireEvent, render, screen } from "@testing-library/react";
import { createPortal } from "react-dom";
import { describe, expect, it, vi } from "vitest";
import { FloatingPanel } from "./FloatingPanel";

function Page({ onClose }: { onClose: () => void }) {
  return (
    <div>
      <button type="button">Outside</button>
      <FloatingPanel onClose={onClose}>
        <p>Inside text</p>
        {/* a menu the panel opened, drawn at the page's end (as Radix popovers are) */}
        {createPortal(<button type="button">In a menu</button>, document.body)}
      </FloatingPanel>
    </div>
  );
}

function press(from: HTMLElement, to: HTMLElement) {
  fireEvent.pointerDown(from);
  fireEvent.pointerUp(to);
  fireEvent.click(from === to ? to : document.body, { detail: 1 }); // a click goes to what both ends share
}

describe("FloatingPanel", () => {
  it("closes on a click that starts and ends outside it, saying so", () => {
    const onClose = vi.fn();
    render(<Page onClose={onClose} />);
    press(screen.getByText("Outside"), screen.getByText("Outside"));
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledWith("outside");
  });

  it("stays open for a press that starts inside and ends outside", () => {
    const onClose = vi.fn();
    render(<Page onClose={onClose} />);
    press(screen.getByText("Inside text"), screen.getByText("Outside"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("stays open for a press that starts outside and ends inside", () => {
    const onClose = vi.fn();
    render(<Page onClose={onClose} />);
    fireEvent.pointerDown(screen.getByText("Outside"));
    fireEvent.pointerUp(screen.getByText("Inside text"));
    fireEvent.click(screen.getByText("Inside text"), { detail: 1 });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("stays open for clicks inside it, and in a menu it opened", () => {
    const onClose = vi.fn();
    render(<Page onClose={onClose} />);
    press(screen.getByText("Inside text"), screen.getByText("Inside text"));
    press(screen.getByText("In a menu"), screen.getByText("In a menu"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("stays open when a button outside is pressed from the keyboard", () => {
    const onClose = vi.fn();
    render(<Page onClose={onClose} />);
    fireEvent.click(screen.getByText("Outside"), { detail: 0 }); // Enter or Space: no pointer
    expect(onClose).not.toHaveBeenCalled();
  });

  it("still closes on Escape", () => {
    const onClose = vi.fn();
    render(<Page onClose={onClose} />);
    fireEvent.keyDown(screen.getByText("Inside text"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledWith();
  });
});
