import { act, render, screen, waitFor } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { WindowDrop } from "./WindowDrop";
const mocks = vi.hoisted(() => ({ handlers: new Map<string, (event: {payload: unknown}) => void>(), imported: vi.fn(), off: vi.fn() }));
vi.mock("@tauri-apps/api/core", () => ({ isTauri: () => true, invoke: vi.fn() }));
vi.mock("@tauri-apps/api/event", () => ({ listen: vi.fn(async (name, handler) => { mocks.handlers.set(name, handler); return mocks.off; }) }));
vi.mock("../records/project", () => ({ currentProject: () => ({ id: "sample" }) }));
vi.mock("../records/RecordsPanel", () => ({ addToRecords: vi.fn() }));
vi.mock("../workspace/api", () => ({ workspaceApi: {} }));
vi.mock("../import/importer", () => ({ importFolders: mocks.imported, importInto: vi.fn() }));
it("takes native events without HTML File objects, highlights, imports and unsubscribes", async () => {
  const { container, unmount } = render(<WindowDrop />);
  await waitFor(() => expect(mocks.handlers.has("one-files-dropped")).toBe(true));
  act(() => mocks.handlers.get("one-drop-hover")!({ payload: true }));
  expect(container.querySelector("[data-window-drop]")).not.toBeNull();
  await act(async () => {
    mocks.handlers.get("one-drop-hover")!({ payload: false });
    mocks.handlers.get("one-files-dropped")!({ payload: { files: [{path:"/sample/tender/sub/a.pdf",name:"a.pdf",folder:"tender/sub",size:1}], errors: [{name:"blocked.pdf",reason:"Permission denied"}] } });
  });
  expect(mocks.imported.mock.calls[0]![0][0].folder).toBe("tender/sub");
  expect(screen.getByRole("alert").textContent).toContain("blocked.pdf: Permission denied");
  await act(async () => mocks.handlers.get("one-files-dropped")!({payload:{files:[],errors:[]}}));
  expect(screen.queryByRole("alert")).toBeNull();
  unmount();
  await Promise.resolve();
  expect(mocks.off).toHaveBeenCalledTimes(2);
});
