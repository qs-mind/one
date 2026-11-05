import { afterEach, describe, expect, it, vi } from "vitest";
import { byTopFolder, fromDrop, fromInput, MAX_FILE_BYTES, oldProjects, upload } from "./walk";

/** A folder as the browser gives it: entries, read in batches of `batch` (WebKit gives 100). */
type Tree = { [name: string]: Tree | string };

function entry(name: string, node: Tree | string, batch: number): FileSystemEntry {
  if (typeof node === "string") {
    const file = new File([node], name);
    return { name, isFile: true, isDirectory: false, file: (ok: (f: File) => void) => ok(file) } as unknown as FileSystemEntry;
  }
  const children = Object.entries(node).map(([child, sub]) => entry(child, sub, batch));
  return {
    name,
    isFile: false,
    isDirectory: true,
    createReader: () => {
      let at = 0;
      return {
        readEntries: (ok: (entries: FileSystemEntry[]) => void) => {
          const next = children.slice(at, at + batch);
          at += batch;
          ok(next);
        },
      };
    },
  } as unknown as FileSystemEntry;
}

function itemsOf(tree: Tree, batch = 2): DataTransferItemList {
  const items = Object.entries(tree).map(([name, node]) => ({ kind: "file", webkitGetAsEntry: () => entry(name, node, batch) }));
  return items as unknown as DataTransferItemList;
}

afterEach(() => vi.unstubAllGlobals());

describe("walking a folder", () => {
  it("walks a dropped folder with nested folders and keeps each path", async () => {
    const items = itemsOf({ مناقصة: { "عقد.pdf": "a", "02 جداول": { "BOQ - عينة.xlsx": "b" }, "رسومات.zip": "c" } });
    expect((await fromDrop(items)).map((p) => [p.folder, p.file.name])).toEqual([
      ["مناقصة", "عقد.pdf"],
      ["مناقصة/02 جداول", "BOQ - عينة.xlsx"],
      ["مناقصة", "رسومات.zip"],
    ]);
  });

  it("reads every batch, however many there are", async () => {
    const many: Tree = {};
    for (let i = 0; i < 250; i++) many[`ملف ${i}.pdf`] = "x";
    expect(await fromDrop(itemsOf({ كبير: many }, 100))).toHaveLength(250);
  });

  it("Choose folder: each file's folder from its relative path", () => {
    const file = new File(["x"], "BOQ.xlsx");
    Object.defineProperty(file, "webkitRelativePath", { value: "مناقصة/02 جداول/BOQ.xlsx" });
    expect(fromInput([file]).map((p) => p.folder)).toEqual(["مناقصة/02 جداول"]);
  });

  it("groups old work by the folder dropped", () => {
    const picked = [
      { file: new File(["a"], "a.pdf"), folder: "برج/عقود" },
      { file: new File(["b"], "b.pdf"), folder: "مدرسة" },
      { file: new File(["c"], "c.pdf"), folder: "برج" },
    ];
    expect(byTopFolder(picked).map((g) => [g.name, g.picked.length])).toEqual([
      ["برج", 2],
      ["مدرسة", 1],
    ]);
  });
});

describe("old work from Choose folder", () => {
  it("each folder inside the one chosen is a project; loose files make one more", () => {
    const picked = fromInput(
      ["شغل قديم/برج/عقود/عقد.pdf", "شغل قديم/برج/BOQ.xlsx", "شغل قديم/مدرسة/مواصفات.docx", "شغل قديم/ملاحظات.txt"].map((path) => {
        const f = new File(["x"], path.split("/").at(-1)!);
        Object.defineProperty(f, "webkitRelativePath", { value: path });
        return f;
      }),
    );
    expect(oldProjects(picked).map((g) => [g.name, g.picked.map((p) => p.folder)])).toEqual([
      ["برج", ["برج/عقود", "برج"]],
      ["مدرسة", ["مدرسة"]],
      ["شغل قديم", ["شغل قديم"]],
    ]);
  });
});

describe("uploading", () => {
  it("uploads one at a time with name and folder in the URL", async () => {
    let open = 0;
    const fetch = vi.fn(async (_url: string) => {
      open += 1;
      expect(open).toBe(1); // never two at once
      await new Promise((r) => setTimeout(r, 1));
      open -= 1;
      return Response.json({ status: "read" }, { status: 201 });
    });
    vi.stubGlobal("fetch", fetch);
    const progress: [number, number][] = [];
    await upload("p1", [
      { file: new File(["a"], "عقد.pdf"), folder: "مناقصة" },
      { file: new File(["b"], "BOQ.xlsx"), folder: "" },
    ], (done, of) => progress.push([done, of]));
    expect(fetch.mock.calls.map(([url]) => url)).toEqual([
      `/api/projects/p1/files?name=${encodeURIComponent("عقد.pdf")}&folder=${encodeURIComponent("مناقصة")}`,
      "/api/projects/p1/files?name=BOQ.xlsx",
    ]);
    expect(progress).toEqual([[0, 2], [1, 2], [2, 2]]);
  });

  it("the report counts duplicates, too big, not read and zips", async () => {
    const answers: Record<string, Response> = {
      "a.pdf": Response.json({ status: "read" }, { status: 201 }),
      "again.pdf": Response.json({ status: "read", duplicate: true }),
      "x.rar": Response.json({ status: "stored" }, { status: 201 }),
      "scan.pdf": Response.json({ status: "unreadable" }, { status: 201 }),
      "big.dwg": Response.json({ error: { en: "big", ar: "كبير" } }, { status: 413 }),
      "empty.txt": Response.json({ error: { en: "The file is empty.", ar: "فاضي" } }, { status: 422 }),
      "away.pdf": new Response(null, { status: 503 }),
      "drawings.zip": Response.json(
        {
          zip: true,
          files: [{ status: "read" }, { status: "read", duplicate: true }],
          skipped: [
            { name: "huge.tif", folder: "z", error: { en: "The file is larger than 256 MB, so it was not added." } },
            { name: "blank.txt", folder: "z", error: { en: "The file is empty." } },
          ],
        },
        { status: 201 },
      ),
    };
    vi.stubGlobal("fetch", vi.fn(async (url: string) => answers[decodeURIComponent(/name=([^&]+)/.exec(url)![1]!)]!));
    const files = Object.keys(answers).map((name) => ({ file: new File(["x"], name), folder: "" }));
    const huge = new File(["x"], "model.ifc");
    Object.defineProperty(huge, "size", { value: MAX_FILE_BYTES + 1 });
    const report = await upload("p1", [...files, { file: huge, folder: "" }], () => undefined);
    expect(report).toEqual({
      added: 4,
      duplicates: 2,
      notRead: 1,
      tooBig: ["big.dwg", "huge.tif", "model.ifc"],
      unreadable: ["scan.pdf", "empty.txt", "blank.txt"],
      zips: 1,
      failed: ["away.pdf"],
    });
  });
});
