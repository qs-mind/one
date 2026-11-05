// An archived project is read-only until it is unarchived. Where the engineer would work in it (the message box at
// the chat's foot, the projects list), one line says so and Unarchive is right there.
import { useState } from "react";
import { coreLine, send } from "../core";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { currentProject, setCurrentProject } from "./project";

/** Unarchives the project in the core; the project on the screen, if it is this one, is no longer read-only. Answers
 * the core's reason when it did not. */
export async function unarchive(projectId: string): Promise<Text | undefined> {
  const response = await send(`/projects/${encodeURIComponent(projectId)}/unarchive`, "POST");
  if (!response?.ok) return coreLine(response, texts.unarchiveFailed);
  const now = currentProject();
  if (now?.id === projectId) setCurrentProject({ ...now, archived_at: null });
  return undefined;
}

/** In place of the message box in an archived project's chat. */
export function ArchivedLine({ projectId }: { projectId: string }) {
  useLanguage();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  return (
    <div
      data-archived-line
      className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-[18px] border border-ink/[0.08] bg-paper px-4 py-2"
    >
      <p className="min-w-0 flex-1 text-slate">{t("archivedChatLine")}</p>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setFailed(undefined);
          setFailed(await unarchive(projectId));
          setBusy(false);
        }}
        className="shrink-0 rounded-lg bg-ink px-3 py-1.5 text-paper focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink disabled:opacity-40"
      >
        {t("unarchiveProject")}
      </button>
      {failed && (
        <p role="alert" className="w-full text-copper">
          {pick(failed)}
        </p>
      )}
    </div>
  );
}
