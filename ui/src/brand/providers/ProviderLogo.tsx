// The AI company's own logo before a model or link's name (decision 16.4): one colour, the text's (Ink, or Slate in a
// secondary row), no tile, no shadow, never the company's colours, never mirrored in Arabic. The name beside it says
// the provider, so the logo is hidden from screen readers. An unknown provider has the one neutral mark.
import { type MarkId, type MarkPath, marks } from "./marks";

/** genai-prices' provider ids, as the core reads them off a link's address (standard.py provider_of). */
const byId: Record<string, MarkId> = {
  anthropic: "claude", // the Claude key and Claude Code alike: the name says which link
  openai: "openai",
  google: "gemini",
  "x-ai": "grok",
  meta: "meta",
  deepseek: "deepseek",
  mistral: "mistral",
  moonshotai: "kimi",
  cohere: "cohere",
  groq: "groq",
  openrouter: "openrouter",
};
/** A host genai-prices does not know comes as "host:port": a local server is told by its default port. */
const byPort: Record<string, MarkId> = { "11434": "ollama", "1234": "lmstudio" };
const byHost: [RegExp, MarkId][] = [
  [/(^|\.)aliyuncs\.com$/, "qwen"], // DashScope, Alibaba's Qwen
  [/(^|\.)ollama\.com$/, "ollama"],
  [/(^|\.)llama\.com$/, "meta"],
];

export function logoOf(provider: string): MarkId | undefined {
  if (Object.hasOwn(byId, provider)) return byId[provider];
  const [, host = "", port] = provider.match(/^(\[[^\]]*\]|[^:]*)(?::(\d+))?$/) ?? [];
  return (port && byPort[port]) || byHost.find(([pattern]) => pattern.test(host))?.[1];
}

/** A ring and its centre: no company's mark. */
const unknown: MarkPath[] = [
  { d: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 1.5a7.5 7.5 0 1 1 0 15 7.5 7.5 0 0 1 0-15z" },
  { d: "M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z" },
];

/** 14 px in chips and lists, 20 px in the first launch's choices. */
export function ProviderLogo({ provider, size = 14 }: { provider: string; size?: 14 | 20 }) {
  const id = logoOf(provider);
  const paths: MarkPath[] = id ? marks[id] : unknown;
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="currentColor"
      fillRule="evenodd"
      aria-hidden="true"
      style={{ width: `${size / 16}rem`, height: `${size / 16}rem` }} // follows the screen's scale
      data-logo={id ?? "unknown"}
      className="shrink-0"
    >
      {paths.map((path) => (
        <path key={path.d} d={path.d} fillOpacity={path.opacity} />
      ))}
    </svg>
  );
}
