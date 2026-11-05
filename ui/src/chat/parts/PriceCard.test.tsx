import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { setLanguage, texts } from "../../i18n";
import { ApprovalCard } from "./ApprovalCard";
import { cardKinds } from "./cardKinds";
import { PriceCard } from "./PriceCard";
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

// What Spending asks the first time a model with no known price is used (core: costs._ask_unknown_price).
const price: CardData = {
  kind: "price",
  title: { en: "A model with no known price", ar: "نموذج سعره مش معروف" },
  detail: { en: "ONE does not know the price of lab-model.", ar: "ONE مش عارف سعر lab-model." },
  options: ["price", "nocap", "no"],
  status: "pending",
  payload: { model: { connector: "standard:lab", model: "lab-model", name: "lab-model" } },
};

describe("PriceCard", () => {
  it("is the renderer for a model with no known price, with no press-and-hold", () => {
    expect(cardKinds.price).toBe(PriceCard);
    render(<ApprovalCard id="c1" card={price} />);
    expect(screen.queryByText(texts.holdHintPaid.ar)).toBeNull();
    expect(screen.getByRole("button", { name: texts.useWithoutPrice.ar })).toBeInTheDocument();
  });

  it("saves the price typed for the model, then goes on with it", async () => {
    const fetch = core({
      "PUT /api/settings/ai/prices": () => Response.json({ entered: "2026-11-05" }),
      "POST /api/cards/c1": () => new Response(null, { status: 204 }),
    });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={price} />);
    await user.click(screen.getByRole("button", { name: texts.enterItsPrice.ar }));
    await user.type(screen.getByRole("textbox", { name: texts.priceIn.ar }), "0.25");
    await user.type(screen.getByRole("textbox", { name: texts.priceOut.ar }), "1.50");
    await user.click(screen.getByRole("button", { name: texts.useThisPrice.ar }));
    expect(bodyOf(fetch, "PUT", "/api/settings/ai/prices")).toEqual([
      { connector: "standard:lab", model: "lab-model", in: "0.25", out: "1.50" },
    ]);
    expect(bodyOf(fetch, "POST", "/api/cards/c1")).toEqual([{ choice: "price" }]);
  });

  it("use without a price answers at once", async () => {
    const fetch = core({ "POST /api/cards/c1": () => new Response(null, { status: 204 }) });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={price} />);
    await user.click(screen.getByRole("button", { name: texts.useWithoutPrice.ar }));
    expect(bodyOf(fetch, "POST", "/api/cards/c1")).toEqual([{ choice: "nocap" }]);
  });

  it("a price the core refuses is said, and nothing is answered", async () => {
    const fetch = core({
      "PUT /api/settings/ai/prices": () => Response.json({ error: { en: "No.", ar: "لأ." } }, { status: 422 }),
    });
    const user = userEvent.setup();
    render(<ApprovalCard id="c1" card={price} />);
    await user.click(screen.getByRole("button", { name: texts.enterItsPrice.ar }));
    await user.type(screen.getByRole("textbox", { name: texts.priceIn.ar }), "0.25");
    await user.type(screen.getByRole("textbox", { name: texts.priceOut.ar }), "1,50");
    await user.click(screen.getByRole("button", { name: texts.useThisPrice.ar }));
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(bodyOf(fetch, "POST", "/api/cards/c1")).toEqual([]);
  });
});
