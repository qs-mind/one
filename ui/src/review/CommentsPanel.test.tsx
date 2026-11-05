// The Comments panel against the core's contract (Plan 6 Task 7), with fetch mocked: no core, no network.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { base, bodies, core, D, json, sheet, thread } from "../deliverables/fixtures";
import { fill, setLanguage, texts } from "../i18n";
import { CommentsPanel } from "./CommentsPanel";

beforeEach(() => setLanguage("ar"));

const note = thread("n1", { kind: "note", author: "Estimator", body: "الفئة أعلى من السوق - عينة", anchor: { type: "row", row: "p2" }, anchor_now: { type: "row", row: "p2" } });
const review = thread("r1", { code: "C", body: "صحح الكمية - عينة", author: "checking_qs" });

describe("CommentsPanel", () => {
  it("One's note and a Review comment look different and each has its text label", () => {
    render(<CommentsPanel projectId="p1" view={sheet()} comments={[note, review]} selection={null} onChanged={() => {}} />);
    const [first, second] = screen.getAllByRole("listitem").filter((li) => li.parentElement?.tagName === "OL");
    expect(within(first!).getByText(texts.reviewNote.ar)).toBeInTheDocument();
    expect(within(second!).getByText(texts.reviewComment.ar)).toBeInTheDocument();
    expect(within(second!).getByText(texts.reviewMustFix.ar)).toBeInTheDocument();
    expect(first!.className).not.toBe(second!.className);
    expect(within(first!).getByText(fill(texts.reviewCommentOn.ar, { place: "البند 03/01" }))).toBeInTheDocument();
    expect(within(second!).getByText(texts.roleChecker.ar)).toBeInTheDocument();
  });

  it("“Fix it” sends the core's own message to the chat", async () => {
    const fetch = core({ [`POST ${base}/comments/r1/fix`]: () => json({ text: "صحح الكمية في البند 03/02 كما طلب المراجع." }) });
    const onSend = vi.fn();
    const user = userEvent.setup();
    render(<CommentsPanel projectId="p1" view={sheet()} comments={[review]} selection={null} onChanged={() => {}} onSend={onSend} />);
    await user.click(screen.getByRole("button", { name: texts.reviewFixIt.ar }));
    expect(onSend).toHaveBeenCalledWith("صحح الكمية في البند 03/02 كما طلب المراجع.");
    expect(String(fetch.mock.calls[0]![0])).toContain("lang=ar");
  });

  it("adds a must-fix comment on the selected cells", async () => {
    const fetch = core({ [`POST ${base}/deliverables/${D}/comments`]: () => json(review, 201) });
    const onChanged = vi.fn();
    const user = userEvent.setup();
    const selection = { type: "range" as const, from: { row: "p2", column: "rate" }, to: { row: "p4", column: "rate" } };
    render(<CommentsPanel projectId="p1" view={sheet()} comments={[]} selection={selection} onChanged={onChanged} />);
    expect(screen.getByText(fill(texts.reviewCommentOn.ar, { place: "البنود 03/01–03/04" }))).toBeInTheDocument();
    await user.type(screen.getByRole("textbox", { name: texts.reviewCommentText.ar }), "راجع الفئات");
    await user.click(screen.getByRole("checkbox", { name: texts.reviewMustFix.ar }));
    await user.click(screen.getByRole("button", { name: texts.reviewAddComment.ar }));
    expect(bodies(fetch, "POST", `${base}/deliverables/${D}/comments`)).toEqual([{ anchor: selection, body: "راجع الفئات", code: "C" }]);
    expect(onChanged).toHaveBeenCalled();
  });

  it("filters open, blocking and all; replies and closes", async () => {
    const closed = thread("x1", { status: "closed", body: "اتقفلت - عينة" });
    const fetch = core({
      [`POST ${base}/comments/r1/replies`]: () => json(review, 201),
      [`POST ${base}/comments/r1/close`]: () => json({ ...review, status: "closed" }),
    });
    const user = userEvent.setup();
    render(<CommentsPanel projectId="p1" view={sheet()} comments={[note, review, closed]} selection={null} onChanged={() => {}} />);
    expect(screen.queryByText("اتقفلت - عينة")).toBeNull();
    await user.click(screen.getByRole("radio", { name: texts.reviewBlocking.ar }));
    expect(screen.queryByText(note.body)).toBeNull();
    expect(screen.getByText(review.body)).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: texts.reviewAll.ar }));
    expect(screen.getByText("اتقفلت - عينة")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: texts.reviewBlocking.ar }));
    await user.type(screen.getByRole("textbox", { name: texts.reviewReplyText.ar }), "تمام");
    await user.click(screen.getByRole("button", { name: texts.reviewReply.ar }));
    await user.click(screen.getByRole("button", { name: texts.reviewClose.ar }));
    expect(bodies(fetch, "POST", `${base}/comments/r1/replies`)).toEqual([{ body: "تمام" }]);
    expect(bodies(fetch, "POST", `${base}/comments/r1/close`)).toHaveLength(1);
  });
});
