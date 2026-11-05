// A drop target's highlight while files are dragged over it. dragenter and dragleave come for every child the pointer
// crosses, so the target counts them: the highlight comes on with the first enter and goes only when the count is
// back to zero, never blinking off and on over a child.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useDragDepth } from "./useDragDepth";

const files = { dataTransfer: { types: ["Files"] } };

function Target({ seen }: { seen: boolean[] }) {
  const { over, handlers } = useDragDepth();
  if (seen.at(-1) !== over) seen.push(over);
  return (
    <div data-testid="target" data-over={over || undefined} {...handlers}>
      <p data-testid="child">
        Drop here <button type="button">Choose</button>
      </p>
    </div>
  );
}

describe("useDragDepth", () => {
  it("never flickers while the drag crosses children", () => {
    const seen: boolean[] = [];
    render(<Target seen={seen} />);
    const target = screen.getByTestId("target");
    const child = screen.getByTestId("child");
    const button = screen.getByRole("button");

    fireEvent.dragEnter(target, files);
    fireEvent.dragEnter(child, files); // the browser enters the child, then leaves the parent
    fireEvent.dragLeave(target, files);
    fireEvent.dragEnter(button, files);
    fireEvent.dragLeave(child, files);
    fireEvent.dragEnter(child, files);
    fireEvent.dragLeave(button, files);
    expect(target).toHaveAttribute("data-over");
    fireEvent.dragLeave(child, files); // out of the target altogether
    expect(target).not.toHaveAttribute("data-over");
    expect(seen).toEqual([false, true, false]); // on once, off once: no blink in between
  });

  it("goes off on a drop, and starts counting afresh", () => {
    const seen: boolean[] = [];
    render(<Target seen={seen} />);
    const target = screen.getByTestId("target");
    fireEvent.dragEnter(target, files);
    fireEvent.dragEnter(screen.getByTestId("child"), files);
    fireEvent.drop(screen.getByTestId("child"), files);
    expect(target).not.toHaveAttribute("data-over");
    fireEvent.dragEnter(target, files);
    expect(target).toHaveAttribute("data-over");
    fireEvent.dragLeave(target, files);
    expect(target).not.toHaveAttribute("data-over");
  });

  it("lets a drop happen only for files, and ignores other drags (text, a frame)", () => {
    render(<Target seen={[]} />);
    const target = screen.getByTestId("target");
    fireEvent.dragEnter(target, { dataTransfer: { types: ["text/plain"] } });
    expect(target).not.toHaveAttribute("data-over");
    fireEvent.dragLeave(target, { dataTransfer: { types: ["text/plain"] } }); // a stray leave never goes below zero
    fireEvent.dragEnter(target, files);
    expect(target).toHaveAttribute("data-over");
    expect(fireEvent.dragOver(target, files)).toBe(false); // prevented: the webview lets the files drop here
  });
});
