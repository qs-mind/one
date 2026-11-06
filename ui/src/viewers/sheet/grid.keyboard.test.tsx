import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Grid } from "./grid";

it("a read-only sample sheet is reachable by Tab and arrow keys", async () => {
  const user = userEvent.setup();
  render(<><button>Before sheet</button><Grid
    label="Sample BOQ" columns={[{ key: "code", label: "Item", kind: "text", edit: false, frozen: false, wrap: true, width: 100 }]}
    rows={[{ id: "sample-1", kind: "item" }]} direction="rtl" rowHeight={() => 32}
    renderCell={() => "Sample item"} onCommit={vi.fn()} selection={null} onSelection={vi.fn()}
    onCopy={() => ({text: "", html: ""})} onPaste={vi.fn()} canEdit={() => false} editText={() => ""} virtualize={false}
  /><button>After sheet</button></>);
  screen.getByRole("button", {name: "Before sheet"}).focus();
  await user.tab();
  expect(screen.getByRole("grid", {name: "Sample BOQ"}).contains(document.activeElement)).toBe(true);
  await user.keyboard("{ArrowDown}");
  expect(document.activeElement?.closest('[role="row"]')).toHaveAttribute("aria-rowindex", "2");
});
