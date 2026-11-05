import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalCard } from "../chat/parts/ApprovalCard";
import { cardKinds } from "../chat/parts/cardKinds";
import { ConnectorCard } from "../chat/parts/ConnectorCard";
import type { CardData } from "../chat/parts/types";
import { count, fill, setLanguage, texts } from "../i18n";
import { Connectors } from "./Connectors";

type Route = (init: RequestInit) => Response | Promise<Response>;

function core(routes: Record<string, Route>) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const route = routes[`${init.method ?? "GET"} ${String(input)}`];
    return route ? route(init) : new Response("not found", { status: 404 });
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

const bodies = (fetch: ReturnType<typeof core>, method: string, url: string) =>
  fetch.mock.calls
    .filter(([u, init]) => String(u) === url && (init?.method ?? "GET") === method)
    .map(([, init]) => (init?.body === undefined ? undefined : (JSON.parse(String(init.body)) as unknown)));

// GET /connectors, as the core sends it (core/qsone/connectors/routes.py). Sample data.
const mail = {
  name: "mail-sample",
  transport: "stdio",
  runs: "mail-server --sample",
  enabled: true,
  tools: 3,
  read_without_asking: false,
  search_tool: null,
  token: true,
};

// The connector card POST /connectors answers with (core/qsone/connectors/hub.py).
const card: CardData & { id: string } = {
  id: "card-sample",
  kind: "connector",
  title: { en: "Add the mail-sample Connector? It can:", ar: "أضيف موصّل mail-sample؟ يقدر:" },
  detail: { en: "It runs on this computer: mail-server --sample", ar: "بيشتغل على الجهاز ده: mail-server --sample" },
  options: ["yes", "no"],
  status: "pending",
  payload: {
    connector: { name: "mail-sample", transport: "stdio", runs: "mail-server --sample" },
    tools: [
      { name: "read_inbox", purpose: "Read the inbox - sample.", read_only: true, destructive: false, open_world: false },
      { name: "send_email", purpose: "Send an email - sample.", read_only: false, destructive: false, open_world: false },
      { name: "delete_mail", purpose: "Delete a mail - sample.", read_only: false, destructive: true, open_world: false },
    ],
    questions: [
      { id: "read_without_asking", text: "Use its reading tools without asking?", options: ["yes", "no"] },
      { id: "search", text: "Use one of its reading tools for web search?", options: ["none", "read_inbox"] },
    ],
  },
};

beforeEach(() => setLanguage("ar"));

describe("Connectors", () => {
  it("lists the Connectors in words, never the raw settings", async () => {
    core({ "GET /api/connectors": () => Response.json({ connectors: [mail] }) });
    render(<Connectors />);
    const item = (await screen.findByText("mail-sample")).closest("li")!;
    expect(within(item).getByText(texts.onThisComputer.ar)).toBeInTheDocument();
    expect(within(item).getByText(count("connectorTools", 3, {}, "ar"))).toBeInTheDocument();
    expect(within(item).getByText(texts.connectorTokenKept.ar)).toBeInTheDocument();
    expect(item.textContent).not.toContain("stdio");
    expect(screen.getByRole("heading", { name: texts.connectors.ar })).toBeInTheDocument();
  });

  it("adding one shows what it can do, then saves it with the engineer's choices", async () => {
    let added = false;
    const fetch = core({
      "GET /api/connectors": () => Response.json({ connectors: added ? [mail] : [] }),
      "POST /api/connectors": () => Response.json({ card }),
      "POST /api/connectors/cards/card-sample": () => {
        added = true;
        return Response.json({ connector: mail });
      },
    });
    const user = userEvent.setup();
    render(<Connectors />);
    expect(await screen.findByText(texts.noConnectors.ar)).toBeInTheDocument();
    await user.type(screen.getByLabelText(texts.connectorName.ar), "mail-sample");
    const command = screen.getByLabelText(texts.connectorCommand.ar);
    expect(command).toHaveAttribute("dir", "ltr");
    await user.type(command, "mail-server --sample");
    const token = screen.getByLabelText(texts.connectorToken.ar);
    expect(token).toHaveAttribute("type", "password");
    await user.type(token, "tok-sample-secret");
    await user.click(screen.getByRole("button", { name: texts.connectorAdd.ar }));

    expect(await screen.findByText("أضيف موصّل mail-sample؟ يقدر:")).toBeInTheDocument();
    expect(bodies(fetch, "POST", "/api/connectors")).toEqual([
      { name: "mail-sample", transport: "stdio", command: "mail-server --sample", token: "tok-sample-secret" },
    ]);
    expect(screen.queryByDisplayValue("tok-sample-secret")).not.toBeInTheDocument(); // sent once, never kept
    const send = screen.getByText("send_email").closest("li")!;
    expect(within(send).getByText(texts.toolActs.ar)).toBeInTheDocument();
    const read = screen.getByText("read_inbox", { selector: "span" }).closest("li")!;
    expect(within(read).getByText(texts.toolReadsOnly.ar)).toBeInTheDocument();
    const remove = screen.getByText("delete_mail").closest("li")!;
    expect(within(remove).getByText(texts.toolDeletes.ar)).toBeInTheDocument();

    await user.click(screen.getByRole("checkbox", { name: texts.readWithoutAsking.ar }));
    await user.selectOptions(screen.getByRole("combobox", { name: texts.useForSearch.ar }), "read_inbox");
    await user.click(screen.getByRole("button", { name: texts.addConnector.ar }));
    await waitFor(() =>
      expect(bodies(fetch, "POST", "/api/connectors/cards/card-sample")).toEqual([
        { choice: "yes", answers: { read_without_asking: "yes", search: "read_inbox" } },
      ]),
    );
    expect(await screen.findByText(texts.connectorAdded.ar)).toBeInTheDocument();
    expect(await screen.findByText("mail-sample", { selector: "li span" })).toBeInTheDocument();
    expect(screen.queryByText("أضيف موصّل mail-sample؟ يقدر:")).not.toBeInTheDocument();
    expect(screen.getByLabelText(texts.connectorToken.ar)).toHaveValue("");
  });

  it("Don't add sends no and saves nothing", async () => {
    const fetch = core({
      "GET /api/connectors": () => Response.json({ connectors: [] }),
      "POST /api/connectors": () => Response.json({ card }),
      "POST /api/connectors/cards/card-sample": () => Response.json({ connector: null }),
    });
    const user = userEvent.setup();
    render(<Connectors />);
    await user.type(await screen.findByLabelText(texts.connectorName.ar), "mail-sample");
    await user.type(screen.getByLabelText(texts.connectorCommand.ar), "mail-server --sample");
    await user.click(screen.getByRole("button", { name: texts.connectorAdd.ar }));
    await user.click(await screen.findByRole("button", { name: texts.dontAdd.ar }));
    await waitFor(() =>
      expect(bodies(fetch, "POST", "/api/connectors/cards/card-sample")).toEqual([{ choice: "no" }]),
    );
    await waitFor(() => expect(screen.queryByText("أضيف موصّل mail-sample؟ يقدر:")).not.toBeInTheDocument());
    expect(screen.getByText(texts.noConnectors.ar)).toBeInTheDocument();
  });

  it("an address over the internet is sent as a url, and a refusal is said in the core's words", async () => {
    const down = { en: "The Connector did not start or did not answer.", ar: "الموصّل ماشتغلش أو مارَدّش." };
    const fetch = core({
      "GET /api/connectors": () => Response.json({ connectors: [] }),
      "POST /api/connectors": () => Response.json({ error: down }, { status: 502 }),
    });
    const user = userEvent.setup();
    render(<Connectors />);
    await user.type(await screen.findByLabelText(texts.connectorName.ar), "remote-sample");
    await user.click(screen.getByRole("radio", { name: texts.overInternet.ar }));
    expect(screen.queryByLabelText(texts.connectorCommand.ar)).not.toBeInTheDocument();
    await user.type(screen.getByLabelText(texts.connectorAddress.ar), "https://mcp.sample.example/mcp");
    await user.click(screen.getByRole("button", { name: texts.connectorAdd.ar }));
    expect(await screen.findByText(down.ar)).toHaveAttribute("role", "alert");
    expect(bodies(fetch, "POST", "/api/connectors")).toEqual([
      { name: "remote-sample", transport: "http", url: "https://mcp.sample.example/mcp" },
    ]);
  });

  it("switches one off and removes one", async () => {
    let list = [mail];
    const fetch = core({
      "GET /api/connectors": () => Response.json({ connectors: list }),
      "PUT /api/connectors/mail-sample/enabled": (init) => {
        const { enabled } = JSON.parse(String(init.body)) as { enabled: boolean };
        list = [{ ...mail, enabled }];
        return Response.json({ connector: list[0] });
      },
      "DELETE /api/connectors/mail-sample": () => {
        list = [];
        return Response.json({ undo: "tok", window_ms: 6000 });
      },
      "POST /api/undo/tok": () => {
        list = [mail];
        return new Response(null, { status: 204 });
      },
    });
    const user = userEvent.setup();
    render(<Connectors />);
    const on = await screen.findByRole("checkbox", { name: texts.connectorSwitchedOn.ar });
    expect(on).toBeChecked();
    await user.click(on);
    await waitFor(() => expect(bodies(fetch, "PUT", "/api/connectors/mail-sample/enabled")).toEqual([{ enabled: false }]));
    await waitFor(() => expect(screen.getByRole("checkbox", { name: texts.connectorSwitchedOn.ar })).not.toBeChecked());
    await user.click(screen.getByRole("button", { name: texts.remove.ar }));
    // gone at once, with Undo in its place instead of "are you sure?"
    expect(await screen.findByRole("status")).toHaveTextContent("اتشال «mail-sample» · تراجع");
    expect(bodies(fetch, "DELETE", "/api/connectors/mail-sample")).toEqual([undefined]);
    await user.click(screen.getByRole("button", { name: texts.undo.ar }));
    expect(await screen.findByRole("button", { name: texts.remove.ar })).toBeInTheDocument();
  });

  it("a removed one is gone for good once its window ends", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let list = [mail];
    core({
      "GET /api/connectors": () => Response.json({ connectors: list }),
      "DELETE /api/connectors/mail-sample": () => {
        list = [];
        return Response.json({ undo: "tok", window_ms: 6000 });
      },
    });
    render(<Connectors />);
    fireEvent.click(await screen.findByRole("button", { name: texts.remove.ar }));
    expect(await screen.findByRole("status")).toBeInTheDocument();
    await act(async () => vi.advanceTimersByTime(6000));
    expect(await screen.findByText(texts.noConnectors.ar)).toBeInTheDocument();
    vi.useRealTimers();
  });

  it("speaks English left to right when the engineer picks English", async () => {
    setLanguage("en");
    core({ "GET /api/connectors": () => Response.json({ connectors: [] }) });
    render(<Connectors />);
    expect(await screen.findByRole("heading", { name: texts.connectors.en })).toBeInTheDocument();
    expect(document.documentElement.dir).toBe("ltr");
    setLanguage("ar");
    expect(await screen.findByRole("heading", { name: texts.connectors.ar })).toBeInTheDocument();
    expect(document.documentElement.dir).toBe("rtl");
  });
});

describe("ConnectorCard in the chat", () => {
  it("is the renderer for connector cards", () => {
    expect(cardKinds.connector).toBe(ConnectorCard);
  });

  it("sends the choices with the answer to the card", async () => {
    const fetch = core({ "POST /api/cards/c1": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={card} />);
    expect(screen.getByText("Read the inbox - sample.")).toHaveAttribute("dir", "auto");
    await user.click(screen.getByRole("button", { name: texts.addConnector.ar }));
    expect(bodies(fetch, "POST", "/api/cards/c1")).toEqual([
      { choice: "yes", answers: { read_without_asking: "no", search: "none" } },
    ]);
    expect(await screen.findByText(fill(texts.answered.ar, { choice: texts.addConnector.ar }))).toBeInTheDocument();
  });
});
