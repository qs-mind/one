import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { setLanguage } from "../../i18n";
import { letter } from "../../deliverables/fixtures";
import { deliverablesApi } from "../../deliverables/api";
import { PackViewer } from "./PackViewer";
import type { PackView } from "../../deliverables/types";

const view = (): PackView => ({ ...letter(), kind: "pack", steps: [
  { kind: "cover", text: { en: "Sample tender", ar: "مناقصة تجريبية" } },
  { kind: "file", file_id: "f", ranges: [[2, 4]], title: { en: "Sample BOQ", ar: "مقايسة تجريبية" } },
  { kind: "seal" },
] });
beforeEach(() => setLanguage("en"));
it("shows the ordered steps and the honest seal explanation", () => {
  render(<PackViewer projectId="p" view={view()} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(3);
  expect(screen.getByText("Sample tender")).toBeInTheDocument();
  expect(screen.getByText(/not a licensed e-signature/)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
});
it("builds a version-bound page image and clears it when the version changes", async () => {
  const build = vi.spyOn(deliverablesApi, "buildPack").mockResolvedValue({ ok: true, data: { pages: 4, page: 1, image: "data:image/png;base64,AA==" } });
  const v = view();
  const { rerender } = render(<PackViewer projectId="p" view={v} />);
  fireEvent.click(screen.getByRole("button", { name: "Build pack" }));
  expect(await screen.findByRole("img")).toHaveAttribute("src", "data:image/png;base64,AA==");
  expect(build).toHaveBeenCalledWith("p", v.id, v.version, 1);
  rerender(<PackViewer projectId="p" view={{ ...v, version: v.version + 1 }} />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
it("shows Arabic steps without splitting words", () => {
  setLanguage("ar");
  render(<PackViewer projectId="p" view={view()} />);
  expect(screen.getByText("مناقصة تجريبية")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "كوّن حزمة المناقصة" })).toBeInTheDocument();
});

it("uses the workspace Deliverable viewer and gates PDF export", async () => {
  const { viewerFor } = await import("../registry");
  const { DeliverableViewer } = await import("../../deliverables/DeliverableViewer");
  const { ExportMenu } = await import("../../review/ExportMenu");
  expect(viewerFor("pack")).toBe(DeliverableViewer);
  const v = view();
  const { rerender } = render(<ExportMenu projectId="p" view={v} />);
  expect(screen.getByRole("button", { name: "PDF" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Word" })).not.toBeInTheDocument();
  rerender(<ExportMenu projectId="p" view={{ ...v, status: "signed_off" }} />);
  expect(screen.getByRole("button", { name: "PDF" })).toBeEnabled();
});
