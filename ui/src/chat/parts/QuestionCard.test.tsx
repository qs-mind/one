import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { ApprovalCard } from "./ApprovalCard";
import { cardKinds } from "./cardKinds";
import { QuestionCard } from "./QuestionCard";
import type { CardData } from "./types";

type Route = (init: RequestInit) => Response | Promise<Response>;

function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const route = routes[`${init.method ?? "GET"} ${String(input)}`];
    return route ? route(init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const bodyOf = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls
    .filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method)
    .map(([, init]) => JSON.parse(String(init!.body)) as unknown);

beforeEach(() => setLanguage("ar"));

// What ask_engineer sends (core/qsone/tools/engineer.py): one card, every question, one option "sent".
const questions: CardData = {
  kind: "question",
  title: { en: "Lead QS asks", ar: "كبير مهندسي الكميات بيسأل" },
  detail: { en: "Answer every question, then press Send.", ar: "جاوب على كل سؤال، وبعدين دوس إرسال." },
  options: ["sent"],
  status: "pending",
  payload: {
    questions: [
      { id: "q1", text: "الخرسانة جاهزة ولا موقع؟ - عينة", options: ["جاهزة", "موقع"] },
      { id: "q2", text: "سعر الأسمنت عندك كام؟ - عينة", free_text: true },
    ],
  },
};

describe("QuestionCard", () => {
  it("is the renderer for question cards", () => {
    expect(cardKinds.question).toBe(QuestionCard);
  });

  it("shows every question and sends all answers together", async () => {
    const fetch = core({ "POST /api/cards/c1": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={questions} />);
    expect(screen.getByText("الخرسانة جاهزة ولا موقع؟ - عينة")).toBeInTheDocument();
    expect(screen.getByText("سعر الأسمنت عندك كام؟ - عينة")).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "موقع" }));
    const reply = screen.getByRole("textbox", { name: "سعر الأسمنت عندك كام؟ - عينة" });
    expect(reply).toHaveAttribute("dir", "auto");
    await user.type(reply, "3950 جنيه");
    await user.click(screen.getByRole("button", { name: texts.send.ar }));
    expect(bodyOf(fetch, "POST", "/api/cards/c1")).toEqual([
      { choice: "sent", answers: { q1: "موقع", q2: "3950 جنيه" } },
    ]);
    expect(await screen.findByText("3950 جنيه")).toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"); // only its folded line
    expect(screen.queryByText("q1")).not.toBeInTheDocument(); // never the raw id
  });

  it("Send waits until every question has an answer", async () => {
    core({});
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={questions} />);
    const send = screen.getByRole("button", { name: texts.send.ar });
    expect(screen.getAllByRole("button")).toHaveLength(1); // one Send for every question
    expect(send).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: "جاهزة" }));
    expect(send).toBeDisabled(); // q2 still has no answer
    const reply = screen.getByRole("textbox", { name: "سعر الأسمنت عندك كام؟ - عينة" });
    await user.type(reply, "   ");
    expect(send).toBeDisabled(); // spaces are not an answer
    await user.type(reply, "4100");
    expect(send).toBeEnabled();
  });

  it("a settled card in the stream shows each answer", () => {
    render(
      <ApprovalCard
        id="c1"
        card={{ ...questions, status: "settled", choice: "sent", answers: { q1: "جاهزة", q2: "4100" } }}
      />,
    );
    expect(screen.getByText("الخرسانة جاهزة ولا موقع؟ - عينة")).toBeInTheDocument();
    expect(screen.getByText("جاهزة")).toBeInTheDocument();
    expect(screen.getByText("4100")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"); // only its folded line
  });

  it("a refused answer says so and keeps the answers", async () => {
    const line = { en: "Answer every question.", ar: "جاوب على كل الأسئلة." };
    core({ "POST /api/cards/c1": () => Response.json({ error: line, field: "answers" }, { status: 422 }) });
    const user = userEvent.setup();
    const one: CardData = { ...questions, payload: { questions: questions.payload!.questions!.slice(0, 1) } };
    render(<ApprovalCard id="c1" card={one} />);
    await user.click(screen.getByRole("radio", { name: "جاهزة" }));
    await user.click(screen.getByRole("button", { name: texts.send.ar }));
    expect(await screen.findByRole("alert")).toHaveTextContent(line.ar);
    expect(screen.getByRole("radio", { name: "جاهزة" })).toBeChecked();
    expect(screen.getByRole("button", { name: texts.send.ar })).toBeEnabled();
  });

  it("a withdrawn card shows its questions with no way to answer", () => {
    render(<ApprovalCard id="c1" card={{ ...questions, status: "withdrawn" }} />);
    expect(screen.getByText(texts.withdrawn.ar)).toBeInTheDocument();
    expect(screen.getByText("الخرسانة جاهزة ولا موقع؟ - عينة")).toBeInTheDocument();
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(screen.getByRole("button")).toHaveAttribute("aria-expanded", "false"); // only its folded line
  });

  it("an unknown card kind falls back to the plain approval buttons", async () => {
    const fetch = core({ "POST /api/cards/c3": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    const unknown = {
      ...questions,
      kind: "understood", // a kind this screen has no renderer for yet (Plan 8)
      options: ["yes", "no"],
    } as unknown as CardData;
    render(<ApprovalCard id="c3" card={unknown} />);
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: texts.yes.ar }));
    expect(bodyOf(fetch, "POST", "/api/cards/c3")).toEqual([{ choice: "yes" }]);
  });
});
