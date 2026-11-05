// The Changes panel against the core's contract (Plan 6 Task 7), with fetch mocked: no core, no network.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { base, bodies, calc, change, core, D, json, n, sheet } from "../deliverables/fixtures";
import type { Change } from "../deliverables/types";
import { fill, setLanguage, texts } from "../i18n";
import { ChangesPanel } from "./ChangesPanel";

const accept = `${base}/deliverables/${D}/changes/accept`;

const records = (more: Partial<Change> = {}) =>
  change("u1", {
    author: "calc_engine",
    op: {
      op: "update_from_records",
      cells: [
        { row: "p3", column: "rate", before: n("39850.50", "r-p3"), after: n("41000.00", "r2-p3"), why: { corrected: "عرض المورد الجديد - عينة" } },
        { row: "p3", column: "amount", before: calc("4782060.00", "a-p3"), after: calc("4920000.00", "a2-p3"), why: { recalculated: true } },
        { row: "p2", column: "description", before: { text: "قديم" }, after: { text: "جديد" }, why: { corrected: null } },
      ],
    },
    before: null,
    after: null,
    follows: [],
    ...more,
  });

beforeEach(() => setLanguage("ar"));

describe("ChangesPanel", () => {
  it("“Accept all mine” posts {mine: true} and says which version it saved", async () => {
    const fetch = core({ [`POST ${accept}`]: () => json({ version: 4, accepted: ["c1"], stale: [] }) });
    const onChanged = vi.fn();
    const announce = vi.fn();
    const user = userEvent.setup();
    render(
      <ChangesPanel
        projectId="p1"
        view={sheet()}
        changes={[change("c1"), change("c2", { author: "Estimator" })]}
        stale={[]}
        onChanged={onChanged}
        announce={announce}
      />,
    );
    await user.click(screen.getByRole("button", { name: texts.reviewAcceptMine.ar }));
    expect(bodies(fetch, "POST", accept)).toEqual([{ mine: true }]);
    expect(announce).toHaveBeenCalledWith(fill(texts.reviewAccepted.ar, { n: 4 }));
    expect(onChanged).toHaveBeenCalled();
  });

  it("shows each change's place, old → new, its author and what it recalculates, by name, not by id", () => {
    render(<ChangesPanel projectId="p1" view={sheet()} changes={[change("c1", { author: "Estimator", reason: "سعر أحدث - عينة" })]} stale={[]} onChanged={() => {}} />);
    const item = screen.getAllByRole("listitem")[0]!;
    expect(within(item).getByText("Estimator")).toBeInTheDocument();
    expect(within(item).getByText("سعر أحدث - عينة")).toBeInTheDocument();
    expect(within(item).getByText("البند 03/02، الفئة")).toBeInTheDocument();
    expect(within(item).getByText("39,850.50 EGP")).toBeInTheDocument();
    expect(within(item).getByText(texts.reviewFollows.ar)).toBeInTheDocument();
    expect(within(item).getByText("البند 03/02، الإجمالي")).toBeInTheDocument();
    expect(item.textContent).not.toMatch(/p3|r-p3|c1/);
  });

  it("a stale change says so in plain words", () => {
    render(<ChangesPanel projectId="p1" view={sheet()} changes={[]} stale={[change("s1", { status: "stale" })]} onChanged={() => {}} />);
    expect(screen.getByText(new RegExp(texts.reviewStale.ar))).toBeInTheDocument();
    expect(screen.getByText(texts.reviewStaleWhy.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.reviewNoChanges.ar)).toBeInTheDocument();
  });

  it("an Update from Project Records comes first and says why each cell moved", () => {
    render(<ChangesPanel projectId="p1" view={sheet()} changes={[change("c1"), records()]} stale={[]} onChanged={() => {}} />);
    const first = screen.getAllByRole("listitem")[0]!;
    expect(within(first).getByText(texts.reviewRecordsMoved.ar)).toBeInTheDocument();
    expect(within(first).getByText(fill(texts.reviewCorrected.ar, { reason: "عرض المورد الجديد - عينة" }))).toBeInTheDocument();
    expect(within(first).getByText(texts.sheetRecalculated.ar)).toBeInTheDocument();
    expect(within(first).getByText(texts.reviewFieldChanged.ar)).toBeInTheDocument();
    expect(within(first).getByText("41,000.00")).toBeInTheDocument();
  });

  it("UPDATE_FIRST: the core's line, then “Accept with the update” sends the update with the refused change", async () => {
    const refusal = { error: { en: "Accept the update from Project Records first.", ar: "اقبل التحديث من سجلات المشروع الأول." }, field: "ids" };
    const answers = [json(refusal, 409), json({ version: 5, accepted: ["u1", "c1"], stale: [] })];
    const fetch = core({ [`POST ${accept}`]: () => answers.shift()! });
    const user = userEvent.setup();
    render(<ChangesPanel projectId="p1" view={sheet()} changes={[change("c1"), records()]} stale={[]} onChanged={() => {}} />);
    await user.click(screen.getAllByRole("button", { name: texts.sheetAccept.ar })[1]!); // the update is first
    expect(await screen.findByRole("alert")).toHaveTextContent(refusal.error.ar);
    await user.click(screen.getByRole("button", { name: texts.reviewAcceptWithUpdate.ar }));
    expect(bodies(fetch, "POST", accept)).toEqual([{ ids: ["c1"] }, { ids: ["u1", "c1"] }]);
  });

  it("a long list of recalculated cells is folded", () => {
    const follows = Array.from({ length: 7 }, (_, i) => ({ row: "p3", column: "amount", before: calc(`${i}.00`, null), after: calc(`${i + 1}.00`, null) }));
    render(<ChangesPanel projectId="p1" view={sheet()} changes={[change("c1", { follows })]} stale={[]} onChanged={() => {}} />);
    expect(screen.getByText(fill(texts.reviewMore.ar, { n: 2 }))).toBeInTheDocument();
  });

  it("clicking a change's place finds it in the viewer", async () => {
    const onLocate = vi.fn();
    const user = userEvent.setup();
    render(<ChangesPanel projectId="p1" view={sheet()} changes={[change("c1")]} stale={[]} onChanged={() => {}} onLocate={onLocate} />);
    await user.click(screen.getByRole("button", { name: "البند 03/02، الفئة" }));
    expect(onLocate).toHaveBeenCalledWith({ row: "p3", column: "rate" });
  });
});
