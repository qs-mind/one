import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AppProviders } from "@/design/AppProviders";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { conversation } from "@/texts/conversation";
import { text } from "@/texts/useText";
import { Composer, type LeadActivity } from "./Composer";

beforeEach(stubBrowser);
afterEach(resetPage);

/** A drop as the browser hands it: one file and one folder (the entry API says which). */
function dropOf(file: File, folder: string) {
  const entry = (isDirectory: boolean, name: string) => ({ isDirectory, name });
  return {
    types: ["Files"],
    files: [file],
    items: [
      { kind: "file", getAsFile: () => file, webkitGetAsEntry: () => entry(false, file.name) },
      { kind: "file", getAsFile: () => null, webkitGetAsEntry: () => entry(true, folder) },
    ],
  };
}

describe.each(DIRS)("Composer (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const field = () => screen.getByRole("textbox", { name: text(conversation.messageLabel, lang) });

  it("sends on Enter, breaks a line on Shift+Enter, and sends nothing empty", async () => {
    const send = vi.fn();
    renderIn(dir, <Composer onSend={send} />);
    await userEvent.type(field(), "{Enter}");
    expect(send).not.toHaveBeenCalled();
    await userEvent.type(field(), "one{Shift>}{Enter}{/Shift}two{Enter}");
    expect(send).toHaveBeenCalledWith({ text: "one\ntwo", attachments: [] });
    expect(field()).toHaveValue("");
  });

  it("takes dropped files and folders as chips, shows the drop state, and sends them", async () => {
    const send = vi.fn();
    const { container } = renderIn(dir, <Composer onSend={send} />);
    const form = container.querySelector("form")!;
    const file = new File(["x"], "04 BOQ.xlsx");
    fireEvent.dragOver(form, { dataTransfer: { types: ["Files"] } });
    expect(form).toHaveAttribute("data-drop-target");
    expect(field()).toHaveAttribute("placeholder", text(common.dropHere, lang));
    fireEvent.drop(form, { dataTransfer: dropOf(file, "Drawings") });
    expect(form).not.toHaveAttribute("data-drop-target");
    expect(screen.getByText("04 BOQ.xlsx")).toBeInTheDocument();
    expect(screen.getByText(text(conversation.folder, lang, { name: "Drawings" }))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: text(conversation.remove, lang, { name: "Drawings" }) }));
    await userEvent.click(screen.getByRole("button", { name: text(common.send, lang) }));
    expect(send).toHaveBeenCalledWith({ text: "", attachments: [expect.objectContaining({ name: "04 BOQ.xlsx", kind: "file", file })] });
  });

  it("queues while the Lead works and sends the queue, in order, when the work stops", async () => {
    const send = vi.fn();
    const ui = (activity: LeadActivity) => (
      <AppProviders>
        <Composer onSend={send} activity={activity} />
      </AppProviders>
    );
    const { rerender } = renderIn(dir, <Composer onSend={send} activity="working" />);
    expect(screen.getByText(text(conversation.whileWorking, lang))).toBeInTheDocument();
    await userEvent.type(field(), "first{Enter}");
    await userEvent.type(field(), "second{Enter}");
    await userEvent.type(field(), "third{Enter}");
    expect(send).not.toHaveBeenCalled();
    const queue = screen.getByRole("region", { name: text(conversation.queuedTitle, lang) });
    expect(queue).toHaveTextContent("first");
    await userEvent.click(screen.getAllByRole("button", { name: text(conversation.removeQueued, lang) })[1]!);
    act(() => rerender(ui("idle")));
    expect(send.mock.calls.map(([m]) => m.text)).toEqual(["first", "third"]);
    expect(screen.queryByRole("region", { name: text(conversation.queuedTitle, lang) })).not.toBeInTheDocument();
  });

  it("sends at once while a card holds the work, and says the Lead reads it after the choice", async () => {
    const send = vi.fn();
    renderIn(dir, <Composer onSend={send} activity="held" />);
    expect(screen.getByText(text(conversation.whileHeld, lang))).toBeInTheDocument();
    await userEvent.type(field(), "now{Enter}");
    expect(send).toHaveBeenCalledWith({ text: "now", attachments: [] });
  });
});
