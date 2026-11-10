// Each ai-elements part as ONE keeps it, right to left and left to right: it renders on U1's parts, mirrors through
// logical sides only, and takes every word from the caller.
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { Confirmation, ConfirmationAction, ConfirmationActions, ConfirmationAnswered, ConfirmationRequest } from "./confirmation";
import { Conversation, ConversationContent, ConversationEmptyState } from "./conversation";
import { Message, MessageAction, MessageActions, MessageContent, MessageResponse } from "./message";
import { PromptInput, PromptInputSubmit, PromptInputTextarea } from "./prompt-input";
import { Source, Sources, SourcesContent, SourcesTrigger } from "./sources";
import { Task, TaskContent, TaskItem, TaskTrigger } from "./task";
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from "./tool";

beforeEach(stubBrowser);
afterEach(resetPage);

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const PHYSICAL = /(^|\s)(-?m[lr]-|-?p[lr]-|left-|right-|text-(left|right)|border-[lr](\s|-|$)|rounded-([tb])?[lr](\s|-|$))/;
const physical = (root: HTMLElement) =>
  [...root.querySelectorAll("[class]")].map((el) => el.getAttribute("class")!).filter((c) => PHYSICAL.test(c));

describe.each(DIRS)("ai-elements parts (%s)", (dir) => {
  it("conversation: a log with an empty state", () => {
    const { container } = renderIn(
      dir,
      <Conversation aria-label="log">
        <ConversationContent>
          <ConversationEmptyState title="Nothing yet" description="Write" />
        </ConversationContent>
      </Conversation>,
    );
    expect(screen.getByRole("log", { name: "log" })).toHaveTextContent("Nothing yet");
    expect(physical(container)).toEqual([]);
  });

  it("message: the engineer's bubble sits at the end side; the response follows the given direction", () => {
    const { container } = renderIn(
      dir,
      <>
        <Message from="user">
          <MessageContent>hello</MessageContent>
        </Message>
        <Message from="assistant">
          <MessageResponse dir={dir}>{"**bold** and a [link](#a)"}</MessageResponse>
          <MessageActions>
            <MessageAction label="Copy">c</MessageAction>
          </MessageActions>
        </Message>
      </>,
    );
    expect(container.querySelector('[data-from="user"]')!.className).toMatch(/self-end/);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("link").className).toMatch(/link/);
    expect(container.querySelector(`[dir="${dir}"]`)).not.toBeNull();
    expect(screen.getByRole("button", { name: "Copy" })).toHaveClass("size-11");
    expect(physical(container)).toEqual([]);
  });

  it("task and sources: closed and open, with a start-side rule", async () => {
    const { container } = renderIn(
      dir,
      <>
        <Task defaultOpen={false}>
          <TaskTrigger title="Reading" />
          <TaskContent>
            <TaskItem>step</TaskItem>
          </TaskContent>
        </Task>
        <Sources>
          <SourcesTrigger label="2 sources" />
          <SourcesContent>
            <Source title="Spec, page 48" />
          </SourcesContent>
        </Sources>
      </>,
    );
    const trigger = screen.getByRole("button", { name: "Reading" });
    expect(hasTarget44(trigger)).toBe(true);
    await userEvent.click(trigger);
    expect(screen.getByText("step").parentElement!.className).toMatch(/border-s-2/);
    await userEvent.click(screen.getByRole("button", { name: "2 sources" }));
    expect(screen.getByRole("button", { name: "Spec, page 48" })).toBeInTheDocument();
    expect(physical(container)).toEqual([]);
  });

  it("tool: its state as a word in a Pill, input and output as ltr text", async () => {
    renderIn(
      dir,
      <Tool>
        <ToolHeader title="read_file" state="output-available" stateLabel="Done" />
        <ToolContent>
          <ToolInput input={{ page: 12 }} label="Asked" />
          <ToolOutput output="ok" errorText={undefined} label="Answer" />
        </ToolContent>
      </Tool>,
    );
    await userEvent.click(screen.getByRole("button", { name: /read_file/ }));
    expect(screen.getByText("Done").closest('[data-slot="pill"]')).not.toBeNull();
    expect(screen.getByText(/"page": 12/)).toHaveAttribute("dir", "ltr");
  });

  it("confirmation: the request and its actions, then only the answer", () => {
    const { rerender } = renderIn(
      dir,
      <Confirmation state="requested">
        <ConfirmationRequest>asked</ConfirmationRequest>
        <ConfirmationAnswered>answered</ConfirmationAnswered>
        <ConfirmationActions>
          <ConfirmationAction>Yes</ConfirmationAction>
        </ConfirmationActions>
      </Confirmation>,
    );
    expect(screen.getByText("asked")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes" })).toHaveClass("whitespace-normal");
    rerender(
      <Confirmation state="answered">
        <ConfirmationRequest>asked</ConfirmationRequest>
        <ConfirmationAnswered>answered</ConfirmationAnswered>
        <ConfirmationActions>
          <ConfirmationAction>Yes</ConfirmationAction>
        </ConfirmationActions>
      </Confirmation>,
    );
    expect(screen.queryByText("asked")).not.toBeInTheDocument();
    expect(screen.getByText("answered")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("prompt-input: the message box, its padding on logical sides", async () => {
    const submit = vi.fn();
    const { container } = renderIn(
      dir,
      <PromptInput onSubmit={submit}>
        <PromptInputTextarea aria-label="message" placeholder="Write" />
        <PromptInputSubmit label="Send">s</PromptInputSubmit>
      </PromptInput>,
    );
    expect(container.querySelector("form")!.className).toMatch(/ps-5 pe-2/);
    await userEvent.type(screen.getByRole("textbox", { name: "message" }), "hi{Enter}");
    expect(submit).toHaveBeenCalledWith({ text: "hi", attachments: [] }, expect.anything());
    expect(physical(container)).toEqual([]);
  });
});
