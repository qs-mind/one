import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { setLanguage } from "../../i18n";
import { fakeSources } from "../../project/fake";
import { CompareDoc } from "./CompareDoc";
import { compareApi } from "./compareApi";

vi.mock("./compareApi", () => ({ compareApi: { files: vi.fn(), compare: vi.fn(), overlay: vi.fn() } }));
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it.each(["en", "ar"] as const)("selects cited pages and displays old, new and overlay in %s", async (lang) => {
  setLanguage(lang);
  vi.mocked(compareApi.files).mockResolvedValue([{ id: "old", name: "Sample old.pdf", added_at: "2026-11-06" }]);
  const old = { file_id: "old", name: "Sample old.pdf", date: "2026-11-06", page: 2 };
  const newer = { file_id: "new", name: "Sample new.pdf", date: "2026-11-06", page: 1 };
  vi.mocked(compareApi.compare).mockResolvedValue({ old, new: newer, compared_at: "2026-11-06", pairs: [], changed: [{ old, new: newer, method: "sheet", added: ["C40"], removed: ["C30"], pixels_changed: 10, overlay: true, summary: { en: "Words changed.", ar: "الكلمات اتغيّرت." } }, { old: { ...old, page: 3 }, new: { ...newer, page: 4 }, method: "order", added: [], removed: [], pixels_changed: 20, overlay: true, summary: { en: "Image changed.", ar: "الصورة اتغيّرت." } }], unchanged: 1, unpaired_old: [], unpaired_new: [] });
  vi.mocked(compareApi.overlay).mockResolvedValue("blob:overlay");
  vi.stubGlobal("URL", { ...URL, revokeObjectURL: vi.fn() });
  const sources = fakeSources({});
  const image = vi.spyOn(sources, "pageImage").mockResolvedValue("blob:page");
  render(<CompareDoc projectId="p" fileId="new" sources={sources} onClose={() => {}} />);
  await screen.findByRole("option", { name: /Sample old/ });
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "old" } });
  await screen.findByText("C40");
  expect(await screen.findAllByRole("img")).toHaveLength(3);
  expect(image).toHaveBeenCalledWith("old", 2, 600);
  expect(image).toHaveBeenCalledWith("new", 1, 600);
  expect(compareApi.overlay).toHaveBeenCalledWith("p", "old", "new", 2, 1, 600);
  fireEvent.click(screen.getByRole("button", { name: /Image changed|الصورة اتغيّرت/ }));
  await waitFor(() => expect(compareApi.overlay).toHaveBeenCalledWith("p", "old", "new", 3, 4, 600));
  expect(image).toHaveBeenCalledWith("old", 3, 600);
  expect(image).toHaveBeenCalledWith("new", 4, 600);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:overlay");
});

it("opens comparison from the PDF viewer and preselects the previous revision", async () => {
  const { FileDoc } = await import("./FileDoc");
  setLanguage("en");
  vi.mocked(compareApi.files).mockResolvedValue([
    { id: "old", name: "sample.pdf", added_at: "2026-11-05" },
    { id: "new", name: "sample.pdf", added_at: "2026-11-06", replaces: "old" },
  ]);
  vi.mocked(compareApi.compare).mockRejectedValue(new Error("failed"));
  const sources = fakeSources({ pages: { new: 1 } });
  render(<FileDoc projectId="p" fileId="new" sources={sources} />);
  fireEvent.click(await screen.findByRole("button", { name: "Compare revisions" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not compare these files.");
  expect(compareApi.compare).toHaveBeenCalledWith("p", "old", "new");
  fireEvent.click(screen.getByRole("button", { name: "Close" }));
  expect(await screen.findByRole("button", { name: "Compare revisions" })).toBeInTheDocument();
});
