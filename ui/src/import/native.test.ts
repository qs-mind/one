import { afterEach, expect, it, vi } from "vitest";
import { nativeFolder } from "./native";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));
afterEach(() => vi.restoreAllMocks());

it("passes the raw IPC ArrayBuffer directly to File without an array conversion", async () => {
  const buffer = new Uint8Array([0, 37, 80, 68, 70, 128, 255]).buffer;
  invoke.mockImplementation(async (command: string) => command === "folder_pick"
    ? [{ path: "/sample/tender/sample.pdf", name: "sample.pdf", folder: "tender", size: buffer.byteLength }]
    : buffer);
  const OriginalFile = globalThis.File;
  const fileConstructor = vi.spyOn(globalThis, "File").mockImplementation(function (parts, name, options) {
    return new OriginalFile(parts, name, options);
  });
  const files = await nativeFolder();
  expect(invoke).toHaveBeenCalledTimes(1); // reading stays lazy
  const file = await files![0]!.read!();
  expect(fileConstructor.mock.calls[0]![0][0]).toBe(buffer);
  expect(file.name).toBe("sample.pdf");
  expect(file.size).toBe(buffer.byteLength);
  const read = new FileReader();
  const contents = new Promise<ArrayBuffer>((resolve, reject) => {
    read.onload = () => resolve(read.result as ArrayBuffer);
    read.onerror = () => reject(read.error);
  });
  read.readAsArrayBuffer(file);
  expect(new Uint8Array(await contents)).toEqual(new Uint8Array(buffer));
  expect(invoke).toHaveBeenLastCalledWith("folder_read", { path: "/sample/tender/sample.pdf" });
});
