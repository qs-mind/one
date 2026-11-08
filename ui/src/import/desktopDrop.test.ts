import { expect, it, vi } from "vitest";
import { receiveDesktopDrop } from "./desktopDrop";
const mocks = vi.hoisted(() => ({ imported: vi.fn() }));
vi.mock("./importer", () => ({ importFolders: mocks.imported }));
it("routes native loose and recursively enumerated folder files through the existing importer, lazily", async () => {
  await receiveDesktopDrop({ files: [
    { path: "/sample/a.pdf", name: "a.pdf", folder: "", size: 1 },
    { path: "/sample/tender/sub/b.jpeg", name: "b.jpeg", folder: "tender/sub", size: 2 },
  ], errors: [] });
  const files = mocks.imported.mock.calls[0]![0];
  expect(files.map((f: {folder: string}) => f.folder)).toEqual(["", "tender/sub"]);
  expect(files[1].file.name).toBe("b.jpeg");
  expect(files[1].read).toBeTypeOf("function");
});
