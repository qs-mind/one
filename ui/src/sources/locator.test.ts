import { expect, it } from "vitest";
import type { FilePiece, SourceLocator } from "../project/types";
import { fileKey } from "./targets";

it("keeps a fractional PDF box on a file piece and targets its page", () => {
  const locator: SourceLocator = { page: 2, box: [10.25, 20.5, 60.75, 80] };
  const piece: FilePiece = { locator, text: "12.50" };
  expect(piece.locator.box).toEqual([10.25, 20.5, 60.75, 80]);
  expect(fileKey("sample", piece.locator)).toBe("file:sample#page=2");
});
