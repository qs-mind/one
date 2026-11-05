// The General chat's hand-off (Plan 7 Task 3): the Lead QS says a request belongs to a project, or that no project
// fits yet. The core sends each as a `data-hand-off` part. Nothing moves and nothing is created until the engineer
// clicks; then the project opens (or is created) and the request goes to its chat.
import { useState } from "react";
import { api } from "../api";
import type { OnePart } from "../chat/parts/types";
import { coreLine } from "../core";
import { fill, pick, t, type Text, texts, useLanguage } from "../i18n";
import { type Project, switchProject } from "../records/project";
import { sendWhenOpen } from "./useChats";

type HandOff =
  | { kind: "project"; project_id: string; name: string; request: string }
  | { kind: "new_project"; name: string; request: string };

function handOffOf(part: OnePart): HandOff | undefined {
  const any = part as unknown as { type: string; data?: Record<string, unknown> };
  const data = any.type === "data-hand-off" ? any.data : undefined;
  if (!data || typeof data.name !== "string" || typeof data.request !== "string") return undefined;
  if (data.kind === "project" && typeof data.project_id === "string") return data as HandOff;
  return data.kind === "new_project" ? (data as HandOff) : undefined;
}

export function HandOffCards({ parts }: { parts: OnePart[] }) {
  const cards = parts.flatMap((part, index) => {
    const handOff = handOffOf(part);
    return handOff ? [<HandOffCard key={index} handOff={handOff} />] : [];
  });
  return cards.length ? <>{cards}</> : null;
}

function HandOffCard({ handOff }: { handOff: HandOff }) {
  useLanguage();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const { name, request } = handOff;
  const existing = handOff.kind === "project";

  async function go() {
    setBusy(true);
    setFailed(undefined);
    const response = await (handOff.kind === "project"
      ? api(`/projects/${encodeURIComponent(handOff.project_id)}/open`, { method: "POST" })
      : api("/projects", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ name }),
        })
    ).catch(() => undefined);
    setBusy(false);
    if (!response?.ok) {
      setFailed(await coreLine(response, existing ? texts.projectNotOpened : texts.projectNotCreated));
      return;
    }
    const project = (await response.json()) as Project;
    sendWhenOpen(project.id, request);
    switchProject(project);
  }

  return (
    <article className="flex flex-col gap-3 rounded-[14px] bg-stone/70 px-5 py-4">
      <p>{existing ? fill(t("handOffAbout"), { name }) : t("noProjectYet")}</p>
      <p dir="auto" className="text-slate">
        {request}
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={() => void go()}
        className="self-start rounded-lg bg-ink px-4 py-2 text-paper disabled:opacity-40"
      >
        {fill(t(existing ? "continueInProject" : "createProjectNamed"), { name })}
      </button>
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </article>
  );
}
