// The Coordination Room: the agents' messages to each other, folded until the engineer opens it.
import { count, fill, pick, t, useLanguage } from "../../i18n";
import type { TeamData } from "./types";

export function CoordinationRoom({ messages }: { messages: { id: string; data: TeamData }[] }) {
  useLanguage();
  if (messages.length === 0) return null;
  return (
    <details className="rounded-md border border-stone px-3 py-2">
      <summary className="text-slate hover:text-ink">{count("coordinationRoom", messages.length)}</summary>
      <ol className="mt-2 flex flex-col gap-2">
        {messages.map(({ id, data }) => (
          <li key={id}>
            <p className="text-slate">
              {fill(t("fromTo"), { sender: pick(data.sender), recipient: pick(data.recipient) })}
            </p>
            <p dir="auto" className="whitespace-pre-wrap">
              {data.text}
            </p>
          </li>
        ))}
      </ol>
    </details>
  );
}
