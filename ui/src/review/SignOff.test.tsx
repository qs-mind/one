// Close-out, Sign-off, Compare, Versions, exports and the Fill preview against the core's contract (Plan 6 Task 7),
// with fetch mocked: no core, no network.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { base, bodies, calc, core, D, json, letter, n, sheet } from "../deliverables/fixtures";
import type { FillPreview as Preview } from "../deliverables/types";
import { fill, setLanguage, texts } from "../i18n";
import { ComparePanel } from "./ComparePanel";
import { ExportMenu } from "./ExportMenu";
import { FillPreview } from "./FillPreview";
import { SignOff } from "./SignOff";
import { VersionsPanel } from "./VersionsPanel";

const invoke = vi.hoisted(() => vi.fn());
vi.mock("@tauri-apps/api/core", () => ({ invoke }));

const d = `${base}/deliverables/${D}`;
const blocked = { pending: 1, open: [], blocking: [], check: null, can_sign_off: false, reasons: [{ en: "1 change is pending.", ar: "فيه تغيير واحد مستني." }, { en: "No check on this version.", ar: "مفيش مراجعة للنسخة دي." }] };
const clear = { ...blocked, pending: 0, reasons: [], can_sign_off: true };

const file = (bytes: number[], name: string, type: string) =>
  new Response(new Uint8Array(bytes), {
    headers: { "content-type": type, "content-disposition": `attachment; filename*=UTF-8''${encodeURIComponent(name)}` },
  });

beforeEach(() => {
  setLanguage("ar");
  invoke.mockReset();
});
afterEach(() => {
  delete (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;
});

describe("SignOff", () => {
  it("is disabled with the core's reasons, then enabled, and after Sign-off offers the Review report", async () => {
    const answers = [json(blocked), json(clear)];
    const fetch = core({ [`GET ${d}/closeout`]: () => answers.shift() ?? json(clear), [`POST ${d}/signoff`]: () => json({ revision: 1 }) });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<SignOff projectId="p1" view={sheet({ pending: 1 })} onChanged={onChanged} />);
    expect(await screen.findByText("فيه تغيير واحد مستني.")).toBeInTheDocument();
    expect(screen.getByText("مفيش مراجعة للنسخة دي.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.reviewSignOff.ar })).toBeDisabled();

    rerender(<SignOff projectId="p1" view={sheet({ pending: 0 })} onChanged={onChanged} />);
    expect(await screen.findByText(texts.reviewCanSignOff.ar)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.reviewSignOff.ar }));
    expect(bodies(fetch, "POST", `${d}/signoff`)).toHaveLength(1);
    expect(onChanged).toHaveBeenCalled();

    rerender(<SignOff projectId="p1" view={sheet({ status: "signed_off", revision: { no: 1, signed_off: true } as never })} onChanged={onChanged} />);
    expect(screen.getByText(fill(texts.reviewSignedOff.ar, { n: 1 }))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: new RegExp(texts.reviewReport.ar) })).toBeInTheDocument();
  });
});

describe("ComparePanel", () => {
  it("shows each changed cell from → to, added rows in Ink and removed rows struck", async () => {
    const older = sheet({ version: 2 });
    const newer = sheet({ version: 3, rows: sheet().rows.filter((r) => r.id !== "p4") });
    core({
      [`GET ${d}/compare`]: () =>
        json({
          rows: [
            { id: "p2", change: "same", cells: {} },
            { id: "p3", change: "changed", cells: { rate: { from: n("39850.50", "a"), to: n("41000.00", "b") } } },
            { id: "p4", change: "removed", cells: {} },
          ],
          total: { from: calc("4859830.00", "t1"), to: calc("4997770.00", "t2") },
        }),
      [`GET ${d}`]: (url) => json(url.includes("version=2") ? older : newer),
    });
    render(<ComparePanel projectId="p1" deliverableId={D} from="v:2" to="v:3" />);
    expect(await screen.findByText("39,850.50")).toBeInTheDocument();
    expect(screen.getByText("39,850.50").closest("del")).not.toBeNull();
    expect(screen.getByText("41,000.00").closest("ins")).not.toBeNull();
    expect(screen.getByText("03/04").closest("del")).not.toBeNull(); // only in the older one
    expect(screen.getByText(texts.reviewRemoved.ar)).toBeInTheDocument();
    expect(screen.queryByText("03/01")).toBeNull(); // unchanged rows are left out
    expect(screen.getByText("4,997,770.00 EGP")).toBeInTheDocument();
  });

  it("in a Document, the words struck and inserted", async () => {
    core({
      [`GET ${base}/deliverables/${"c".repeat(32)}/compare`]: () =>
        json({ blocks: [{ id: "b2", change: "changed", segments: [{ op: "same", text: "سارية " }, { op: "del", text: "٣٠" }, { op: "ins", text: "٦٠" }, { op: "same", text: " يوماً" }] }] }),
      [`GET ${base}/deliverables/${"c".repeat(32)}`]: () => json(letter()),
    });
    render(<ComparePanel projectId="p1" deliverableId={"c".repeat(32)} from="r:1" to="v:2" />);
    expect((await screen.findByText("٣٠")).tagName).toBe("DEL");
    expect(screen.getByText("٦٠").tagName).toBe("INS");
  });
});

describe("VersionsPanel", () => {
  it("lists versions and revisions and compares the two chosen", async () => {
    const fetch = core({
      [`GET ${d}/versions`]: () =>
        json({
          versions: [
            { n: 1, at: "2026-11-05T08:00:00.000000+00:00", by: "lead_qs", changes: ["a"] },
            { n: 2, at: "2026-11-05T09:00:00.000000+00:00", by: "engineer", changes: ["b", "c"] },
          ],
          revisions: [{ no: 1, version_n: 1, issued_at: "2026-11-05T08:30:00.000000+00:00", signed_off: true }],
        }),
      [`GET ${d}/compare`]: () => json({ rows: [], total: { from: null, to: null } }),
      [`GET ${d}`]: () => json(sheet()),
    });
    const user = userEvent.setup();
    render(<VersionsPanel projectId="p1" view={sheet()} />);
    expect((await screen.findAllByText(fill(texts.reviewVersion.ar, { n: 2 }))).length).toBeGreaterThan(0);
    expect(screen.getByText(fill(texts.reviewBy.ar, { who: texts.roleLead.ar }))).toBeInTheDocument();
    expect(screen.getByText(texts.statusSignedOff.ar)).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: texts.reviewFrom.ar }), "r:1");
    await user.click(screen.getByRole("button", { name: texts.reviewCompare.ar }));
    expect(await screen.findByText(texts.reviewNoDifference.ar)).toBeInTheDocument();
    const compared = fetch.mock.calls.map(([u]) => String(u)).find((u) => u.includes("/compare"))!;
    expect(new URL(compared, "http://x").searchParams.get("from")).toBe("r:1");
    expect(new URL(compared, "http://x").searchParams.get("to")).toBe("v:2");
  });
});

describe("ExportMenu", () => {
  it("saves the core's bytes under the core's name (a download outside the desktop app), marked draft until signed off", async () => {
    const name = "جدول الكميات - عينة - مسودة.xlsx";
    core({ [`GET ${d}/export`]: () => file([1, 2, 3], name, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet") });
    const blob = vi.fn((_: Blob) => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: blob, revokeObjectURL: vi.fn() }));
    const clicked: string[] = [];
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push(this.download);
    });
    const announce = vi.fn();
    const user = userEvent.setup();
    render(<ExportMenu projectId="p1" view={sheet()} announce={announce} />);
    expect(screen.getByText(texts.exportDraftMark.ar)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: texts.exportWord.ar })).toBeNull();
    await user.click(screen.getByRole("button", { name: texts.exportExcel.ar }));
    await waitFor(() => expect(clicked).toEqual([name]));
    expect(new Uint8Array(await blob.mock.calls[0]![0].arrayBuffer())).toEqual(new Uint8Array([1, 2, 3]));
    expect(announce).toHaveBeenCalledWith(fill(texts.exportDownloaded.ar, { name }));
    click.mockRestore();
  });

  it("in the desktop app, saves through the native Save dialog; a document offers Word and PDF", async () => {
    (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    invoke.mockResolvedValue(true);
    const fetch = core({ [`GET ${base}/deliverables/${"c".repeat(32)}/export`]: () => file([9, 8], "خطاب العطاء.docx", "application/octet-stream") });
    const announce = vi.fn();
    const user = userEvent.setup();
    render(<ExportMenu projectId="p1" view={letter({ status: "signed_off" })} announce={announce} />);
    expect(screen.queryByText(texts.exportDraftMark.ar)).toBeNull();
    await user.click(screen.getByRole("button", { name: texts.exportWord.ar }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("save_export", { name: "خطاب العطاء.docx", bytes: [9, 8] }));
    expect(String(fetch.mock.calls[0]![0])).toContain("format=docx");
    expect(announce).toHaveBeenCalledWith(fill(texts.exportSaved.ar, { name: "خطاب العطاء.docx" }));
    // and it shows, quietly, under the buttons: the engineer sees the export worked without a screen reader
    expect(screen.getByText(fill(texts.exportSaved.ar, { name: "خطاب العطاء.docx" })).closest("p")).toHaveClass("text-slate");
    expect(screen.getByRole("button", { name: texts.exportPdf.ar })).toBeInTheDocument();
  });

  it("offers the client's file only when there is a Fill Plan", async () => {
    const onFill = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(<ExportMenu projectId="p1" view={sheet()} onFill={onFill} />);
    expect(screen.queryByRole("button", { name: texts.exportClientFile.ar })).toBeNull();
    rerender(<ExportMenu projectId="p1" view={sheet()} fillPlanId="f1" onFill={onFill} />);
    await user.click(screen.getByRole("button", { name: texts.exportClientFile.ar }));
    expect(onFill).toHaveBeenCalledWith("f1");
  });
});

describe("FillPreview", () => {
  const preview = (more: Partial<Preview> = {}): Preview => ({
    plan_id: "f1", deliverable_id: D, file_id: "file1", revision: 1, sheet: "BOQ",
    writes: [{ cell: "F12", row: 12, column: "rate", before: null, after: "39850.50", code_ours: "03/02", code_theirs: "3.2", client_text: "خرسانة مسلحة للأساسات" }],
    skipped: [{ cell: "G12", reason: "formula" }, { cell: "F20", reason: "merged" }],
    mismatches: [{ row: 12, code_ours: "03/02", code_theirs: "3.2", accepted: false, text: { en: "Row 12: their code 3.2, ours 03/02.", ar: "صف 12: كودهم 3.2، كودنا 03/02." } }],
    unmapped_rows: [], unmapped_items: [], accepted_mismatches: [],
    ...more,
  });

  it("lists the cells left alone and each differing code before the file can be made", async () => {
    const accepted = preview({ mismatches: [{ ...preview().mismatches[0]!, accepted: true }], accepted_mismatches: [12] });
    const fetch = core({
      [`GET ${base}/fill-plans/f1/preview`]: () => json(preview()),
      [`POST ${base}/fill-plans/f1/accept-mismatches`]: () => json(accepted),
      [`GET ${base}/fill-plans/f1/file`]: () => file([7], "BOQ العميل - معبأ.xlsx", "application/octet-stream"),
    });
    (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ = {};
    invoke.mockResolvedValue(true);
    const user = userEvent.setup();
    render(<FillPreview projectId="p1" planId="f1" />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("39,850.50")).toBeInTheDocument();
    expect(within(table).getByText("خرسانة مسلحة للأساسات")).toBeInTheDocument();
    expect(screen.getByText(new RegExp(texts.fillSkippedFormula.ar))).toBeInTheDocument();
    expect(screen.getByText(new RegExp(texts.fillSkippedMerged.ar))).toBeInTheDocument();
    expect(screen.getByText("صف 12: كودهم 3.2، كودنا 03/02.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: texts.fillMake.ar })).toBeDisabled();
    expect(screen.getByText(texts.fillMismatchesFirst.ar)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: texts.fillItIsRight.ar }));
    expect(bodies(fetch, "POST", `${base}/fill-plans/f1/accept-mismatches`)).toEqual([{ rows: [12] }]);
    expect(await screen.findByText(texts.fillMarkedRight.ar)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.fillMake.ar }));
    await waitFor(() => expect(invoke).toHaveBeenCalledWith("save_export", { name: "BOQ العميل - معبأ.xlsx", bytes: [7] }));
  });

  it("says the core's refusal when no Revision is signed off", async () => {
    core({ [`GET ${base}/fill-plans/f1/preview`]: () => json({ error: { en: "Sign off a Revision first.", ar: "اعتمد إصدار الأول." }, field: null }, 409) });
    render(<FillPreview projectId="p1" planId="f1" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("اعتمد إصدار الأول.");
  });
});
