import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { setLanguage } from "../i18n";
import { PasteKey } from "./PasteKey";

beforeEach(() => setLanguage("en"));
it.each([
  ["sk-ant-api03-sample", "anthropic", null],
  ["sk-ant-sample", "anthropic", null],
  ["AIzaSampleKey", "Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai"],
  ["sk-or-sample", "OpenRouter", "https://openrouter.ai/api/v1"],
  ["sk-sample", "example.com", "https://example.com/v1"],
])("pastes, detects and checks %s", async (key, name, url) => {
  const fetch = vi.fn(async (input: unknown, _init?: RequestInit) => {
    const path = String(input);
    if (path.endsWith("/standard")) return Response.json({ id: "standard:new" });
    if (path.endsWith("/settings/ai")) return Response.json({ cheapest: { [url ? "standard:new" : "anthropic"]: { connector: url ? "standard:new" : "anthropic", model: "sample-cheap" } } });
    return Response.json({ ok: true });
  });
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<PasteKey onSaved={() => {}} />);
  await user.click(screen.getByLabelText("Paste your AI key"));
  await user.paste(key);
  if (name === "example.com") {
    expect(fetch).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText("Provider base URL"), url!);
    await user.tab();
  }
  await screen.findByText(new RegExp(`${name}.*Works.*sample-cheap`, "i"));
  const requests = fetch.mock.calls.map(([path, init]) => [String(path), init?.body && JSON.parse(String(init.body))]);
  expect(fetch.mock.calls.filter(([path]) => String(path) === "/api/settings/model").map(([, init]) => [init?.method, JSON.parse(String(init?.body))])).toEqual([
    ["PUT", url ? { id: "sample-cheap", connector: "standard:new" } : { id: "sample-cheap" }],
  ]);
  expect(fetch.mock.calls.some(([path]) => String(path) === "/api/settings/ai/roles")).toBe(false);
  expect(requests).toContainEqual(["/api/settings/ai/check", url ? { via: "standard", connector: "standard:new" } : { via: "api_key" }]);
  if (url) expect(requests).toContainEqual(["/api/settings/ai/standard", { name, base_url: url, key }]);
  else expect(requests).toContainEqual(["/api/settings/ai-key", { provider: "anthropic", value: key }]);
  expect(screen.getByLabelText("Paste your AI key")).toHaveValue("");
});
it("shows a refused key's reason and never says it works", async () => {
  vi.stubGlobal("fetch", vi.fn(async (input) => String(input).endsWith("/check") ? Response.json({ error: { en: "Key expired.", ar: "المفتاح انتهى." } }, { status: 409 }) : String(input).endsWith("/settings/ai") ? Response.json({ cheapest: { anthropic: { connector: "anthropic", model: "sample" } } }) : Response.json({})));
  render(<PasteKey onSaved={() => {}} />);
  const user = userEvent.setup();
  await user.click(screen.getByLabelText("Paste your AI key"));
  await user.paste("sk-ant-sample");
  expect(await screen.findByRole("alert")).toHaveTextContent("Key expired.");
  await waitFor(() => expect(screen.queryByText(/Works/)).toBeNull());
});
it("refreshes Advanced settings when a new link has no known-price default", async () => {
  const onSaved = vi.fn();
  vi.stubGlobal("fetch", vi.fn(async (input) => String(input).endsWith("/standard") ? Response.json({ id: "standard:new" }) : Response.json({ cheapest: {} })));
  render(<PasteKey onSaved={onSaved} />);
  const user = userEvent.setup();
  await user.click(screen.getByLabelText("Paste your AI key"));
  await user.paste("AIzaSampleKey");
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose a model in Advanced settings.");
  expect(onSaved).toHaveBeenCalledOnce();
});
