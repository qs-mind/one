// An archived project is read-only: its cards and its message box take nothing, one line says why and offers
// Unarchive right there; the projects list and the top bar offer it too.
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { App } from "../shell/App";
import { calls, core, P1, P2 } from "../shell/testing";
import { currentProject, setCurrentProject } from "./project";

vi.mock("../workspace/Workspace", async () => ({ Workspace: (await import("../shell/testing")).WorkspaceStandIn, DocumentHead: () => null }));

const archived = { ...P1, archived_at: "2026-11-05T09:00:00+00:00" };

const waitingCard = {
  kind: "outside",
  title: { en: "Send the sample email?", ar: "أبعت الإيميل - عينة؟" },
  detail: { en: "It goes outside ONE.", ar: "ده هيخرج برّه ONE." },
  options: ["yes", "no"],
  status: "pending",
};
const stored = [
  { id: "q-b1", role: "user", parts: [{ type: "text", text: "ابعت - عينة" }] },
  { id: "r-b1", role: "assistant", parts: [{ type: "data-card", id: "c1", data: waitingCard }] },
];

beforeEach(() => {
  setLanguage("ar");
  setCurrentProject(undefined);
});

describe("an archived project's chat", () => {
  it("its cards and message box take nothing; one line offers Unarchive, which brings the box back", async () => {
    setCurrentProject(archived);
    const fetch = core({
      routes: {
        "POST /api/projects/p1/open": () => Response.json(archived),
        "GET /api/chat/p1/messages": () => Response.json({ messages: stored }),
        "POST /api/projects/p1/unarchive": () => Response.json({ archived_at: null }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    const card = (await screen.findByText(waitingCard.detail.ar)).closest("section")!;
    expect(within(card).getByRole("button", { name: texts.allowOnce.ar })).toBeDisabled();
    expect(within(card).getByRole("button", { name: texts.dontAllow.ar })).toBeDisabled();
    expect(screen.queryByRole("textbox", { name: texts.message.ar })).toBeNull();
    const line = screen.getByText(texts.archivedChatLine.ar).parentElement!;

    await user.click(within(line).getByRole("button", { name: texts.unarchiveProject.ar }));
    await waitFor(() => expect(calls(fetch, "POST", "/api/projects/p1/unarchive")).toHaveLength(1));
    expect(await screen.findByRole("textbox", { name: texts.message.ar })).toBeInTheDocument();
    expect(currentProject()?.archived_at).toBeNull();
    expect(within(card).getByRole("button", { name: texts.allowOnce.ar })).toBeEnabled();
  });

  it("the top bar's chip is a button that looks like one", async () => {
    setCurrentProject(archived);
    core();
    render(<App />);
    const chip = await screen.findByRole("button", { name: new RegExp(texts.archivedReadOnly.ar) });
    expect(chip).toHaveAttribute("aria-expanded", "false");
    expect(chip).toHaveClass("border");
  });
});

describe("the projects list", () => {
  it("an archived row offers Unarchive beside Open", async () => {
    const fetch = core({
      routes: {
        "GET /api/projects": () => Response.json({ projects: [{ ...P2, open: false }, { ...archived, open: false }] }),
        "POST /api/projects/p1/unarchive": () => Response.json({ archived_at: null }),
      },
    });
    const user = userEvent.setup();
    render(<App />);
    await user.click(within(screen.getByRole("banner")).getByRole("button", { name: new RegExp(texts.generalChat.ar) }));
    const button = await screen.findByRole("button", { name: `${texts.unarchiveProject.ar}: ${P1.name}` });
    await user.click(button);
    await waitFor(() => expect(calls(fetch, "POST", "/api/projects/p1/unarchive")).toHaveLength(1));
  });
});
