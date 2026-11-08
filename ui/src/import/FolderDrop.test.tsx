import { act, fireEvent, render, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { FolderChooser, chooseFolder } from "./FolderDrop";
const mocks = vi.hoisted(() => ({ native: true, open: vi.fn(), invoke: vi.fn(), imported: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => mocks.native, invoke: mocks.invoke }));
vi.mock("@tauri-apps/plugin-dialog", () => ({ open: mocks.open }));
vi.mock("./importer", () => ({ importFolders: mocks.imported }));
beforeEach(() => { vi.clearAllMocks(); mocks.native = true; });
it("picks a native directory and sends nested sample files through folder import", async () => {
  mocks.open.mockResolvedValue("/sample/Tender");
  mocks.invoke.mockImplementation(async (command: string) => command === "folder_pick" ? [{ path: "/sample/Tender/sub/a.txt", name: "a.txt", folder: "Tender/sub", size: 3 }] : new Uint8Array([97, 98, 99]).buffer);
  render(<FolderChooser />);
  act(() => chooseFolder(false));
  await waitFor(() => expect(mocks.imported).toHaveBeenCalled());
  expect(mocks.invoke).toHaveBeenCalledWith("folder_pick");
  expect(mocks.open).not.toHaveBeenCalled();
  const [files, options] = mocks.imported.mock.calls[0]!;
  expect(files[0].folder).toBe("Tender/sub");
  expect(files[0].file.name).toBe("a.txt");
  expect(files[0].file.size).toBe(3);
  expect(options).toEqual({ old: false, chosen: true });
  expect(mocks.invoke).not.toHaveBeenCalledWith("folder_read", expect.anything());
  expect((await files[0].read()).size).toBe(3);
  expect(mocks.invoke).toHaveBeenCalledWith("folder_read", {path:"/sample/Tender/sub/a.txt"});
});
it("cancelled folder selection imports nothing", async () => {
  mocks.open.mockResolvedValue(null);
  mocks.invoke.mockResolvedValue(null);
  render(<FolderChooser />);
  await act(async () => chooseFolder(true));
  expect(mocks.invoke).toHaveBeenCalledWith("folder_pick");
  expect(mocks.imported).not.toHaveBeenCalled();
});
it("keeps the folder input in a browser", () => {
  mocks.native = false;
  const { container } = render(<FolderChooser />);
  const file = new File(["sample"], "a.txt");
  fireEvent.change(container.querySelector("input")!, { target: { files: [file] } });
  expect(mocks.imported).toHaveBeenCalledWith([file], { old: false });
});
it("does not call a post-selection failure a file-add failure and lets it be dismissed", async () => {
  mocks.invoke.mockResolvedValue([{ path: "/sample/a.pdf", name: "a.pdf", folder: "sample", size: 1 }]);
  mocks.imported.mockRejectedValue(new Error("follow-up"));
  const { getByRole, queryByRole } = render(<FolderChooser />);
  await act(async () => chooseFolder(false));
  expect(getByRole("alert").textContent).not.toContain("Some files were not added");
  fireEvent.click(getByRole("button"));
  expect(queryByRole("alert")).toBeNull();
});
it("clears a selection error when the next file add succeeds", async () => {
  mocks.invoke.mockRejectedValue(new Error("permission"));
  const { queryByRole } = render(<FolderChooser />);
  await act(async () => chooseFolder(false));
  expect(queryByRole("alert")).not.toBeNull();
  act(() => window.dispatchEvent(new Event("one-files-added")));
  expect(queryByRole("alert")).toBeNull();
});
