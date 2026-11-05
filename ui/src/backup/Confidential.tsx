// Confidential, for the open project. On: its key is wrapped by its own recovery code instead of the Backup key, and
// the code is shown once. Off: a plain confirm first, since its key then goes with the Backup key again.
import { useId, useState } from "react";
import { coreLine, send } from "../core";
import { primary, quiet, secondary } from "../firstlaunch/parts";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { type Project, setCurrentProject } from "../records/project";
import { RecoveryCode } from "./RecoveryCode";

export function Confidential({ project, onClose }: { project: Project; onClose: () => void }) {
  useLanguage();
  const title = useId();
  const [busy, setBusy] = useState(false);
  const [asking, setAsking] = useState(false);
  const [code, setCode] = useState<string>(); // shown once, dropped once confirmed or when the panel closes
  const [failed, setFailed] = useState<Text>();
  const on = project.confidential === true;

  async function turn(next: boolean) {
    setBusy(true);
    setFailed(undefined);
    const response = await send(`/projects/${encodeURIComponent(project.id)}/confidential`, "PUT", { on: next });
    setBusy(false);
    setAsking(false);
    if (!response?.ok) return setFailed(await coreLine(response, texts.confidentialFailed));
    const answer = (await response.json()) as { confidential: boolean; code?: string };
    setCurrentProject({ ...project, confidential: answer.confidential });
    if (answer.code) setCode(answer.code);
  }

  return (
    <section aria-labelledby={title} className="flex flex-col gap-5 px-5 py-5">
      <div className="flex items-center justify-between gap-4">
        <h2 id={title} className="text-lg font-semibold">
          {t("confidential")}
        </h2>
        <button type="button" onClick={onClose} className={`${quiet} -me-3`}>
          {t("close")}
        </button>
      </div>
      <p className="text-slate">{t("confidentialHelp")}</p>
      {code ? (
        <RecoveryCode
          code={code}
          confirmPath={`/projects/${encodeURIComponent(project.id)}/confidential/confirm`}
          onDone={() => setCode(undefined)}
        />
      ) : asking ? (
        <div className="flex flex-col gap-3 rounded-lg bg-stone px-4 py-4">
          <p>{t("confidentialOffConfirm")}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" disabled={busy} onClick={() => void turn(false)} className={primary}>
              {t("confidentialTurnOff")}
            </button>
            <button type="button" onClick={() => setAsking(false)} className={quiet}>
              {t("accountCancel")}
            </button>
          </div>
        </div>
      ) : on ? (
        <button type="button" onClick={() => setAsking(true)} className={`${secondary} self-start`}>
          {t("confidentialTurnOff")}
        </button>
      ) : (
        <button type="button" disabled={busy} onClick={() => void turn(true)} className={`${primary} self-start`}>
          {t("confidentialTurnOn")}
        </button>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}
