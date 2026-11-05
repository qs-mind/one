import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../i18n";
import { App } from "../shell/App";
import { calls, core } from "../shell/testing";
import { SearchKey } from "./SearchKey";

vi.mock("../canvas/Canvas", async () => ({ Canvas: (await import("../shell/testing")).CanvasStandIn }));

const KEY = "BSA-sample-key-0000"; // not a real key
type Status = { provider: "brave" | "native" | "connector" | "none"; own_key: boolean };

// GET /settings/search answers `now` (changed by a saved key); PUT /settings/search-key answers `put`.
function searchCore(start: Status, put: () => Response = () => Response.json({ set: true })) {
  let now = start;
  return core({
    routes: {
      "GET /api/settings/search": () => Response.json(now),
      "PUT /api/settings/search-key": () => {
        const answer = put();
        if (answer.ok) now = { provider: "brave", own_key: true };
        return answer;
      },
      "GET /api/connectors": () => Response.json({ connectors: [] }),
    },
  });
}

beforeEach(() => setLanguage("ar"));

describe("SearchKey", () => {
  it("search key is a password field and never shown again", async () => {
    const fetch = searchCore({ provider: "none", own_key: false });
    const user = userEvent.setup();
    render(<SearchKey />);
    const field = await screen.findByLabelText(texts.searchKey.ar);
    expect(field).toHaveAttribute("type", "password");
    expect(field).toHaveAttribute("autocomplete", "off");
    await user.type(field, `  ${KEY}  `);
    await user.click(screen.getByRole("button", { name: texts.save.ar }));

    expect(await screen.findByRole("status")).toHaveTextContent(texts.keyAdded.ar);
    const [, init] = calls(fetch, "PUT", "/api/settings/search-key")[0]!;
    expect(JSON.parse(String(init!.body))).toEqual({ value: KEY });
    expect(screen.getByLabelText(texts.searchKey.ar)).toHaveValue("");
    expect(document.body.textContent).not.toContain(KEY);
    // the screen asks again which search is in use, and says a key is kept, without showing it
    expect(await screen.findByText(texts.searchKeyKept.ar)).toBeInTheDocument();
    expect(screen.getByText(texts.searchByBrave.ar)).toBeInTheDocument();
    expect(calls(fetch, "GET", "/api/settings/search")).toHaveLength(2);
  });

  it("shows which search is in use", async () => {
    for (const [provider, label] of [
      ["brave", texts.searchByBrave],
      ["native", texts.searchByNative],
      ["connector", texts.searchByConnector],
      ["none", texts.searchByNone],
    ] as const) {
      searchCore({ provider, own_key: provider === "brave" });
      const { unmount } = render(<SearchKey />);
      expect(await screen.findByText(texts.searchProvider.ar)).toBeInTheDocument();
      expect(screen.getByText(label.ar)).toBeInTheDocument();
      setLanguage("en");
      expect(await screen.findByText(label.en)).toBeInTheDocument();
      setLanguage("ar");
      unmount();
    }
  });

  it("a key that was not saved says why, in the page language", async () => {
    const down = { en: "The key store is not answering.", ar: "مخزن المفاتيح مش بيرد." };
    searchCore({ provider: "none", own_key: false }, () => Response.json({ error: down }, { status: 503 }));
    const user = userEvent.setup();
    render(<SearchKey />);
    await user.type(await screen.findByLabelText(texts.searchKey.ar), KEY);
    await user.click(screen.getByRole("button", { name: texts.save.ar }));
    expect(await screen.findByRole("alert")).toHaveTextContent(down.ar);
    expect(screen.queryByText(texts.searchKeyKept.ar)).toBeNull();
  });

  it("says plainly when the search in use cannot be loaded", async () => {
    core({ routes: { "GET /api/settings/search": () => new Response("down", { status: 500 }) } });
    render(<SearchKey />);
    expect(await screen.findByText(texts.searchFailedToLoad.ar)).toBeInTheDocument();
    expect(screen.getByLabelText(texts.searchKey.ar)).toBeInTheDocument(); // a key can still be added
  });

  it("sits with the Connectors in the AI settings panel", async () => {
    searchCore({ provider: "native", own_key: false });
    const user = userEvent.setup();
    render(<App />);
    await user.click(within(screen.getByRole("banner")).getByRole("button", { name: new RegExp(texts.ai.ar) }));
    const panel = (await screen.findByRole("region", { name: texts.aiTitle.ar })).parentElement!;
    expect(within(panel).getByRole("region", { name: texts.searchTitle.ar })).toBeInTheDocument();
    expect(within(panel).getByRole("region", { name: texts.connectors.ar })).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByText(texts.searchByNative.ar)).toBeInTheDocument());
  });

  it("every new label exists in both languages", () => {
    for (const key of [
      "searchTitle",
      "searchKey",
      "searchKeyHelp",
      "searchKeyKept",
      "searchProvider",
      "searchByBrave",
      "searchByNative",
      "searchByConnector",
      "searchByNone",
      "searchFailedToLoad",
    ] as const) {
      expect(texts[key].en.trim(), key).not.toBe("");
      expect(texts[key].ar.trim(), key).not.toBe("");
      expect(texts[key].en, key).not.toBe(texts[key].ar);
    }
  });
});
