import { beforeEach, describe, expect, it } from "vitest";
import { workspaceApi } from "./api";

const exists = () => true;

describe("workspaceApi", () => {
  beforeEach(() => workspaceApi.reset(null, exists));

  it("open then back returns to the first document with its anchor", () => {
    workspaceApi.reset({ key: "file:a", anchor: { page: 3 } }, exists);
    workspaceApi.open("deliverable:x", { row: "7" });
    expect(workspaceApi.current()).toEqual({ key: "deliverable:x", anchor: { row: "7" } });
    expect(workspaceApi.back()).toBe(true);
    expect(workspaceApi.current()).toEqual({ key: "file:a", anchor: { page: 3 } });
  });

  it("back on an empty history returns false", () => {
    expect(workspaceApi.back()).toBe(false);
    expect(workspaceApi.current()).toEqual({ key: "files:all", anchor: null });
  });

  it("reset(null) opens Project files", () => {
    expect(workspaceApi.current()).toEqual({ key: "files:all", anchor: null });
  });

  it("restores Project files when the saved document is gone", () => {
    workspaceApi.reset({ key: "deliverable:x", anchor: null }, () => false);
    expect(workspaceApi.current()).toEqual({ key: "files:all", anchor: null });
  });

  it("forget of the open document opens Project files and drops it from the history", () => {
    workspaceApi.open("file:a");
    workspaceApi.open("deliverable:x");
    workspaceApi.forget("deliverable:x");
    expect(workspaceApi.current()).toEqual({ key: "files:all", anchor: null });
    workspaceApi.forget("file:a");
    workspaceApi.back();
    expect(workspaceApi.current()?.key).toBe("files:all");
  });
});
