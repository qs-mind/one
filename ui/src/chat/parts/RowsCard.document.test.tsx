import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { fakeSources } from "../../project/fake";
import { setCurrentProject } from "../../records/project";
import { DocumentView } from "../../workspace/DocumentView";
import { DocumentHead } from "../../workspace/Workspace";
import { useOpened, workspaceApi } from "../../workspace/api";
import { ApprovalCard } from "./ApprovalCard";
import type { CardData } from "./types";

const card: CardData = {
  kind: "rows", status: "pending", title: {en: "Sample BOQ columns", ar: "أعمدة مقايسة عينة"},
  detail: {en: "Review sample column meanings", ar: "راجع أعمدة العينة"}, options: ["keep", "no"],
  payload: { columns: [{key: "column", label: {en: "Column", ar: "العمود"}}, {key: "meaning", label: {en: "Meaning", ar: "المعنى"}}],
    rows: [{column: "F", meaning: "quantity"}], meaning_column: "meaning",
    meanings: [{key: "quantity", label: {en: "Quantity", ar: "الكمية"}}, {key: "amount", label: {en: "Amount", ar: "الإجمالي"}}] },
};
const docs = {deliverables: [], clientBoqs: [], files: [], desks: []};
function Document() {
  const opened = useOpened();
  return <div data-testid="document"><DocumentHead documents={docs} />{opened?.key.startsWith("view:") &&
    <DocumentView projectId="rows-sample" sources={fakeSources({})} opened={opened} />}</div>;
}
it("opens BOQ columns wide, keeps edits when chat folds, and submits the edited meanings", async () => {
  setLanguage("en");
  setCurrentProject({id:"rows-sample", name:"Sample", created_at:"2026-11-06"});
  workspaceApi.reset(null, () => true);
  const fetch = vi.fn(async () => new Response(null, {status: 204}));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const answered = vi.fn();
  const { rerender } = render(<><ApprovalCard id="rows-wide-sample" card={card} onAnswered={answered} /><Document /></>);
  await user.selectOptions(screen.getByRole("combobox"), "amount");
  await user.click(screen.getByRole("button", {name: texts.openAsDocument.en}));
  const doc = screen.getByTestId("document");
  expect(within(doc).getByRole("heading", {level: 1})).toHaveTextContent(card.title.en);
  expect(within(doc).getByRole("combobox")).toHaveValue("amount");
  rerender(<Document />); // the chat is folded: the document must still work
  expect(screen.getByRole("combobox")).toHaveValue("amount");
  await user.click(screen.getByRole("button", {name: texts.keepColumns.en}));
  expect(fetch.mock.calls).toHaveLength(1);
  expect(JSON.parse(String((fetch.mock.calls[0] as unknown as [string, RequestInit])[1].body)))
    .toEqual({choice:"keep", answers:{F:"amount"}});
  expect(answered).toHaveBeenCalledOnce();
  expect(await screen.findByText("Your answer: approved 1 column")).toBeInTheDocument();
  rerender(<></>);
  await act(async () => {});
  rerender(<Document />);
  expect(screen.queryByRole("button", {name: texts.keepColumns.en})).toBeNull();
  expect(screen.getByText("Your answer: approved 1 column")).toBeInTheDocument();
  setCurrentProject(undefined);
});

it("the chat and document share the pending request and its settled outcome", async () => {
  setLanguage("en");
  setCurrentProject({id:"rows-sample", name:"Sample", created_at:"2026-11-06"});
  workspaceApi.reset(null, () => true);
  let finish!: (response: Response) => void;
  const fetch = vi.fn(() => new Promise<Response>((resolve) => { finish = resolve; }));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<><ApprovalCard id="rows-both-sample" card={card} /><Document /></>);
  await user.click(screen.getByRole("button", {name: texts.openAsDocument.en}));
  const buttons = screen.getAllByRole("button", {name: texts.keepColumns.en});
  expect(buttons).toHaveLength(2);
  await user.click(buttons[1]!);
  for (const button of buttons) expect(button).toBeDisabled();
  await user.click(buttons[0]!);
  expect(fetch).toHaveBeenCalledOnce();
  await act(async () => finish(new Response(null, {status: 204})));
  expect(screen.getAllByText("Your answer: approved 1 column")).toHaveLength(2);
  expect(screen.queryByRole("button", {name: texts.keepColumns.en})).toBeNull();
  setCurrentProject(undefined);
});
