import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { setLanguage, texts } from "../i18n";
import { DocumentsContext } from "../workspace/documents";
import { Reply } from "./Reply";

beforeEach(() => setLanguage("ar"));

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
      expect(screen.getByText(text)).toHaveAttribute("dir", /[ا-ي]/.test(text) ? (text === "بند" ? "auto" : "rtl") : "ltr");
    }
    expect(screen.getByRole("list")).toHaveAttribute("dir", "auto");
  });

  it("marks each number with no source, as a whole number only, and says so", () => {
    const { container } = render(
      <Reply
        text={"Rate 39,850.50 EGP for 120 m3, total **7,500 EGP**; 17,500 elsewhere.\n\n| Total |\n|---|\n| 7,500 |"}
        unsourced={["7,500"]}
      />,
    );
    const marks = [...container.querySelectorAll("mark")];
    expect(marks.map((mark) => mark.textContent)).toEqual(["7,500", "7,500"]);
    expect(marks[0]).toHaveAttribute("title", texts.noSource.ar);
    expect(marks[0]!.closest("strong")).not.toBeNull(); // inside the bold, which stays bold
    expect(container).toHaveTextContent("17,500 elsewhere"); // not marked inside a longer number
    expect(screen.getByText(texts.noSourceNote.ar)).toBeInTheDocument();
  });

  it("marks both ends of a range the guard counted (audit C7: «6,500–8,500 EGP/m³» showed no mark)", () => {
    const { container } = render(<Reply text={"الفئة 6,500–8,500 EGP/m³ تقريبًا، و 6,500-8,500 كمان"} unsourced={["6,500", "8,500"]} />);
    expect([...container.querySelectorAll("mark")].map((mark) => mark.textContent)).toEqual(["6,500", "8,500", "6,500", "8,500"]);
  });

  it("marks nothing and adds no note when every number has a source", () => {
    const { container } = render(<Reply text={"Total 7,500 EGP"} unsourced={[]} />);
    expect(container.querySelector("mark")).toBeNull();
    expect(screen.queryByText(texts.noSourceNote.ar)).not.toBeInTheDocument();
  });

  it("an Arabic paragraph isolates its English runs, so the colon and numbers stay on the Arabic side", () => {
    const line = "إجمالي البنود في ملف boq-priced.xls: 100,912,880.78 جنيه، من الخلية H18 في Project Records.";
    const { container } = render(<Reply text={`**${line}**`} />);
    const p = container.querySelector("p")!;
    expect(p).toHaveAttribute("dir", "rtl");
    expect(p.textContent).toBe(line); // nothing lost or moved in the text itself
    expect([...p.querySelectorAll("bdi")].map((b) => b.textContent)).toEqual(["boq-priced.xls", "H18", "Project Records"]);
    // the colon and the number are outside every isolate, so they take the Arabic paragraph's direction
    expect([...p.querySelectorAll("bdi")].some((b) => /:|100/.test(b.textContent ?? ""))).toBe(false);
  });

  it("an English paragraph isolates its Arabic runs; Arabic words are never cut", () => {
    const { container } = render(<Reply text={"Total of «المبنى الرئيسي»: 5 items, `boq.xls` read."} />);
    const p = container.querySelector("p")!;
    expect([...p.querySelectorAll("bdi")].map((b) => b.textContent)).toEqual(["المبنى الرئيسي", "boq.xls"]);
    const harakat = "مُقَايَسَةُ الْأَعْمَالِ";
    const { container: arabic } = render(<Reply text={`${harakat} في boq.xls`} />);
    expect(arabic.querySelector("p")!.textContent).toBe(`${harakat} في boq.xls`);
    expect(arabic.querySelector("p")!.firstChild!.textContent).toBe(`${harakat} في `); // one piece, letters joined
  });

  it("each list item has its marker room on its own start side", () => {
    const { container } = render(<Reply text={"- بند الخرسانة\n- Steel item\n\n1. أول"} />);
    for (const list of container.querySelectorAll("ul, ol")) expect(list.className).not.toMatch(/\bps-/);
    const items = [...container.querySelectorAll("li")];
    expect(items).toHaveLength(3);
    for (const item of items) {
      expect(item).toHaveAttribute("dir", "auto");
      expect(item).toHaveClass("ms-5");
    }
  });

  it("never shows ONE's ids: a document's reads as its name, any other goes", () => {
    const docs = {
      deliverables: [],
      clientBoqs: [],
      desks: [],
      files: [{ id: "1b2746c511134ef18d8b1c38e591d9a0", name: "مقايسة - عينة.xlsx", status: "read" as const, note: null, replaces: null }],
    };
    render(
      <DocumentsContext.Provider value={docs}>
        <Reply text={"المستند (المعرف): 1b2746c511134ef18d8b1c38e591d9a0\n\nImported 53 items (Import ID: 8ec3c3de5f2a4b0c9d1e2f3a4b5c6d7e)."} />
      </DocumentsContext.Provider>,
    );
    expect(screen.getByText(/المستند/)).toHaveTextContent("المستند مقايسة - عينة.xlsx");
    expect(screen.getByText(/Imported/)).toHaveTextContent(/^Imported 53 items\.$/);
    expect(document.body.textContent).not.toMatch(/[0-9a-f]{8}/);
  });

  it("a number written in Arabic-Indic digits reads in Western digits, its decimal a point, still marked", () => {
    render(<Reply text="الإجمالي ٦٤٠٬٩٨٣٫٣٥ جنيه" unsourced={["٦٤٠٬٩٨٣٫٣٥"]} />);
    expect(screen.getByText("640,983.35").tagName).toBe("MARK");
    expect(document.body.textContent).not.toMatch(/[٠-٩٫٬]/);
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
