import { fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DIRS, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
import { common } from "@/texts/common";
import { conversation } from "@/texts/conversation";
import { text } from "@/texts/useText";
import { Composer, type ComposerMessage } from "./Composer";

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
    renderIn(dir, <Composer onSend={send} onSteer={vi.fn()} />);
    await userEvent.type(field(), "{Enter}");
    expect(send).not.toHaveBeenCalled();
    await userEvent.type(field(), "one{Shift>}{Enter}{/Shift}two{Enter}");
    expect(send).toHaveBeenCalledWith({ text: "one\ntwo", attachments: [] });
    expect(field()).toHaveValue("");
  });

  it("takes dropped files and folders as chips, shows the drop state, and sends them", async () => {
    const send = vi.fn();
    const { container } = renderIn(dir, <Composer onSend={send} onSteer={vi.fn()} />);
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

  it("steers the running work at once, shows the message until /steer answers, and sends nothing to /chat", async () => {
    const send = vi.fn();
    const answers: Array<{ ok: () => void }> = [];
    const steer = vi.fn((_: ComposerMessage) => new Promise<void>((ok) => answers.push({ ok })));
    renderIn(dir, <Composer onSend={send} onSteer={steer} activity="working" />);
    expect(screen.getByText(text(conversation.whileWorking, lang))).toBeInTheDocument();
    await userEvent.type(field(), "first{Enter}");
    await userEvent.type(field(), "second{Enter}");
    expect(steer.mock.calls.map(([m]) => m.text)).toEqual(["first", "second"]);
    expect(send).not.toHaveBeenCalled();
    const region = () => screen.queryByRole("region", { name: text(conversation.steeringTitle, lang) });
    expect(region()).toHaveTextContent("first");
    answers[0]!.ok();
    await vi.waitFor(() => expect(region()).not.toHaveTextContent("first"));
    expect(region()).toHaveTextContent("second");
    answers[1]!.ok();
    await vi.waitFor(() => expect(region()).not.toBeInTheDocument());
  });

  it("keeps a steer that failed, and sends it again or drops it", async () => {
    const steer = vi.fn().mockRejectedValueOnce(new Error("409")).mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error("409"));
    renderIn(dir, <Composer onSend={vi.fn()} onSteer={steer} activity="working" />);
    await userEvent.type(field(), "first{Enter}");
    expect(await screen.findByText(text(conversation.steerFailed, lang))).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: text(conversation.steerAgain, lang) }));
    expect(steer).toHaveBeenCalledTimes(2);
    await vi.waitFor(() => expect(screen.queryByText("first")).not.toBeInTheDocument());
    await userEvent.type(field(), "second{Enter}");
    await userEvent.click(await screen.findByRole("button", { name: text(conversation.dropSteer, lang) }));
    expect(screen.queryByText("second")).not.toBeInTheDocument();
  });

  it("steers at once while a card holds the work, and says the Lead reads it after the choice", async () => {
    const send = vi.fn();
    const steer = vi.fn().mockResolvedValue(undefined);
    renderIn(dir, <Composer onSend={send} onSteer={steer} activity="held" />);
    expect(screen.getByText(text(conversation.whileHeld, lang))).toBeInTheDocument();
    await userEvent.type(field(), "now{Enter}");
    expect(steer).toHaveBeenCalledWith({ text: "now", attachments: [] });
    expect(send).not.toHaveBeenCalled();
  });
});
