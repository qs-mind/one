// The model chip shows each model's company logo (decision 16.4): the chip, and every row of its card.
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { fill, setLanguage, texts } from "../i18n";
import type { ModelCard } from "../settings/AiSettings";
import { ModelChip } from "./ComposerChips";

const card = (connector: string, model: string, name: string, provider: string): ModelCard => ({
  connector,
  model,
  name,
  provider,
  images: false,
  tools: true,
  context: null,
  price_in: null,
  price_out: null,
  price_source: null,
  on_device: false,
  subscription: false,
});

const sheet = [
  card("anthropic", "claude-opus-5-5", "Claude Opus 5.5", "anthropic"),
  card("claude-code", "sonnet", "Claude Sonnet (Claude Code)", "anthropic"),
  card("standard:ds", "deepseek-chat", "deepseek-chat", "deepseek"),
  card("standard:local", "qwen3:8b", "qwen3:8b", "localhost:11434"),
  card("standard:x", "some-model", "some-model", "example.com"),
];

describe("ModelChip", () => {
  it("shows the company's logo before each model: the Claude logo for Claude models", async () => {
    setLanguage("en");
    const user = userEvent.setup();
    render(<ModelChip sheet={sheet} current={sheet[0]} onPick={vi.fn()} onOpenChange={vi.fn()} above={createRef()} />);
    const chip = screen.getByRole("button", { name: fill(texts.modelChip.en, { name: "Claude Opus 5.5" }) });
    expect(chip.querySelector("svg")).toHaveAttribute("data-logo", "claude");

    await user.click(chip);
    const menu = await screen.findByRole("menu", { name: texts.models.en });
    const logos = within(menu)
      .getAllByRole("menuitemradio")
      .map((item) => item.querySelector("svg[data-logo]")?.getAttribute("data-logo"));
    expect(logos).toEqual(["claude", "claude", "deepseek", "ollama", "unknown"]);
  });
});
