// Each AI company's own logo, decided from the provider the core reads off a link (decision 16.4).
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { marks } from "./marks";
import { logoOf, ProviderLogo } from "./ProviderLogo";

describe("logoOf", () => {
  it("names the company from the core's provider: genai-prices' id, or a host and port it does not know", () => {
    const cases: [string, string | undefined][] = [
      ["anthropic", "claude"], // the Claude key and Claude Code alike
      ["deepseek", "deepseek"], // api.deepseek.com
      ["mistral", "mistral"], // api.mistral.ai
      ["dashscope.aliyuncs.com", "qwen"],
      ["dashscope-intl.aliyuncs.com", "qwen"],
      ["localhost:11434", "ollama"],
      ["127.0.0.1:11434", "ollama"],
      ["[::1]:11434", "ollama"],
      ["ollama.com", "ollama"],
      ["localhost:1234", "lmstudio"],
      ["openrouter", "openrouter"], // openrouter.ai
      ["openai", "openai"],
      ["google", "gemini"],
      ["x-ai", "grok"],
      ["meta", "meta"],
      ["api.llama.com", "meta"],
      ["groq", "groq"],
      ["moonshotai", "kimi"],
      ["cohere", "cohere"],
      ["example.com", undefined],
      ["localhost:8080", undefined], // llama.cpp, or anything: no logo of its own
      ["localhost", undefined],
      ["", undefined],
    ];
    expect(cases.map(([provider]) => [provider, logoOf(provider)])).toEqual(cases);
  });
});

describe("ProviderLogo", () => {
  it("draws the company's logo in the text colour, hidden from screen readers, never mirrored", () => {
    const { container } = render(<ProviderLogo provider="deepseek" />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("data-logo", "deepseek");
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg).toHaveAttribute("fill", "currentColor");
    expect(svg).toHaveAttribute("width", "14");
    expect(svg.getAttribute("class")).not.toMatch(/rtl:|scale-x/);
    expect([...svg.querySelectorAll("path")].map((p) => p.getAttribute("d"))).toEqual(marks.deepseek.map((p) => p.d));
  });

  it("an unknown provider has the one neutral mark; 20 px where asked", () => {
    const { container } = render(<ProviderLogo provider="example.com" size={20} />);
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("data-logo", "unknown");
    expect(svg).toHaveAttribute("width", "20");
  });

  it("every logo is reached, and keeps only path data: no colour, style, id or script of the companies' own", () => {
    const providers = ["anthropic", "openai", "google", "x-ai", "meta", "deepseek", "mistral", "dashscope.aliyuncs.com"];
    providers.push("moonshotai", "cohere", "groq", "openrouter", "localhost:11434", "localhost:1234");
    const drawn = providers.map((provider) => {
      const { container, unmount } = render(<ProviderLogo provider={provider} />);
      const svg = container.querySelector("svg")!;
      expect(svg.querySelectorAll(":not(path)")).toHaveLength(0);
      for (const path of svg.querySelectorAll("path")) {
        expect(path.getAttributeNames().filter((n) => !["d", "fill-opacity"].includes(n))).toEqual([]);
        expect(path.getAttribute("d")).toMatch(/^[MmLlHhVvCcSsQqTtAaZz0-9.,\-\s]+$/);
      }
      const logo = svg.getAttribute("data-logo");
      unmount();
      return logo;
    });
    expect(drawn.sort()).toEqual(Object.keys(marks).sort());
  });

  it("no generic block glyph is left before a model anywhere in the app", () => {
    const sources = import.meta.glob("../../**/*.tsx", { query: "?raw", import: "default", eager: true });
    const cube = Object.keys(sources).filter((file) => /M8 1\.75 13\.5 4\.9|ModelGlyph/.test(sources[file] as string));
    expect(cube.filter((file) => !file.endsWith(".test.tsx"))).toEqual([]);
  });
});
