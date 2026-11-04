import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Reply } from "./Reply";

describe("Reply", () => {
  it("shows bold, lists and code instead of raw marks", () => {
    const { container } = render(
      <Reply text={"The **total** is:\n\n- concrete\n- steel\n\n1. first\n\nUse `C30`.\n\n```\nqty = 12\n```"} />,
    );
    expect(screen.getByText("total").tagName).toBe("STRONG");
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(["concrete", "steel", "first"]);
    expect(screen.getByText("C30").tagName).toBe("CODE");
    expect(container.querySelector("pre")).toHaveTextContent("qty = 12");
    expect(container.textContent).not.toContain("**");
  });

  it("each block finds its own direction: English left to right, Arabic right to left", () => {
    render(<Reply text={"The price is from the supplier.\n\nالسعر من المورد.\n\n- بند\n\n| Item | Qty |\n|---|---|\n| Steel | 5 |"} />);
    for (const text of ["The price is from the supplier.", "السعر من المورد.", "بند", "Steel"]) {
      expect(screen.getByText(text)).toHaveAttribute("dir", "auto");
    }
    expect(screen.getByRole("list")).toHaveAttribute("dir", "auto");
  });

  it("never renders raw HTML", () => {
    const { container } = render(<Reply text={'<img src="x" onerror="alert(1)"><script>alert(2)</script>\n\nok'} />);
    expect(container.querySelector("img, script")).toBeNull();
    expect(screen.getByText("ok")).toBeInTheDocument();
  });

  it("links and images open nothing: their text and address show as plain text", () => {
    const { container } = render(
      <Reply text={"[the price list](https://example.com/prices) and [x](javascript:alert(1)) ![plan](https://example.com/p.png)"} />,
    );
    expect(container.querySelector("a, img")).toBeNull();
    expect(container).toHaveTextContent("the price list (https://example.com/prices)");
    expect(container).toHaveTextContent("plan");
    expect(container.innerHTML).not.toContain("javascript:");
  });
});
