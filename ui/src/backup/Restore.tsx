// Restore from a backup folder: the projects found in it, each asking only for what it needs: nothing (this computer
// has the Backup key, or the account gave it), a sign-in, the Backup key's recovery code, or a Confidential
// project's own code. A typed code is sent once and cleared; after each restore the list is read again, since the
// first code also brings the Backup key to this computer and the others then need nothing.
import { type FormEvent, useEffect, useId, useRef, useState } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { field, openSetup, primary, secondary, useSetupRequest } from "../firstlaunch/parts";
import { fill, pick, t, type Text, texts, useLanguage } from "../i18n";
import { when } from "../review/place";
import { FolderPicker } from "./folder";

type Found = { id: string; name: string | null; last_backup: string; needs: null | "sign_in" | "backup_code" | "project_code" };

export function Restore() {
  useLanguage();
  const [path, setPath] = useState<string>();
  const [found, setFound] = useState<Found[]>();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [back, setBack] = useState<string[]>([]);
  const signingIn = useSetupRequest() !== null;
  const wasSigningIn = useRef(false);

  useEffect(() => {
    // back from signing in: the account may have brought the Backup key, so the folder is read again
    if (wasSigningIn.current && !signingIn && path) void look(path);
    wasSigningIn.current = signingIn;
  }, [signingIn]);

  async function look(at: string) {
    setPath(at);
    setBusy(true);
    setFailed(undefined);
    const response = await api(`/backup/found?path=${encodeURIComponent(at)}`).catch(() => undefined);
    setBusy(false);
    if (response?.ok) setFound(((await response.json()) as { projects: Found[] }).projects);
    else {
      setFound(undefined);
      setFailed(await coreLine(response, texts.restoreFailed));
    }
  }

  return (
    <section aria-label={t("restoreTitle")} className="flex flex-col gap-4">
      <h3 className="font-semibold">{t("restoreTitle")}</h3>
      <FolderPicker label={t("restorePickFolder")} busy={busy} onPicked={(picked) => void look(picked)} />
      {path && (
        <p dir="ltr" className="truncate text-start text-sm text-slate">
          {path}
        </p>
      )}
      {back.map((name) => (
        <p key={name} role="status">
          {fill(t("restoreDone"), { name })}
        </p>
      ))}
      {found && found.length === 0 && <p className="text-slate">{t("restoreNone")}</p>}
      {found && found.length > 0 && (
        <div className="flex flex-col gap-2">
          <h4 className="text-sm text-slate">{t("restoreFound")}</h4>
          <ul className="flex flex-col gap-2">
            {found.map((project) => (
              <FoundProject
                key={project.id}
                path={path!}
                project={project}
                onRestored={(name) => {
                  setBack((now) => [...now, name]);
                  void look(path!);
                }}
              />
            ))}
          </ul>
        </div>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}

function FoundProject({ path, project, onRestored }: { path: string; project: Found; onRestored: (name: string) => void }) {
  const id = useId();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const needsCode = project.needs === "backup_code" || project.needs === "project_code";

  async function restore(event?: FormEvent) {
    event?.preventDefault();
    setBusy(true);
    setFailed(undefined);
    const response = await send("/backup/restore", "POST", { path, project_id: project.id, ...(needsCode ? { code: code.trim() } : {}) });
    setBusy(false);
    if (response?.ok) {
      setCode(""); // the code has done its work: it is not kept
      onRestored(((await response.json()) as { name: string }).name);
    } else setFailed(await coreLine(response, texts.restoreFailed));
  }

  return (
    <li className="flex flex-col gap-3 rounded-lg bg-stone px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        {project.name ? (
          <span dir="auto" className="font-semibold">
            {project.name}
          </span>
        ) : (
          <span className="text-slate">{t("restoreHiddenName")}</span>
        )}
        <span className="text-sm text-slate">{fill(t("backupLast"), { date: when(project.last_backup) })}</span>
      </div>
      {project.needs === null && (
        <button type="button" disabled={busy} onClick={() => void restore()} className={`${primary} self-start`}>
          {t("restoreProject")}
        </button>
      )}
      {project.needs === "sign_in" && (
        <button type="button" onClick={() => openSetup("account", true)} className={`${secondary} self-start`}>
          {t("restoreNeedsSignIn")}
        </button>
      )}
      {needsCode && (
        <form onSubmit={(event) => void restore(event)} className="flex flex-col gap-2">
          <p>{t(project.needs === "project_code" ? "restoreNeedsProjectCode" : "restoreNeedsBackupCode")}</p>
          <label htmlFor={id} className="text-sm text-slate">
            {t("restoreCode")}
          </label>
          <div className="flex gap-2">
            <input
              id={id}
              dir="ltr"
              autoComplete="off"
              spellCheck={false}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="XXXXX-XXXXX-XXXXX-XXXXX-XXXXX"
              className={`${field} min-w-0 flex-1 font-mono uppercase`}
            />
            <button type="submit" disabled={busy || !code.trim()} className={primary}>
              {t("restoreProject")}
            </button>
          </div>
        </form>
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </li>
  );
}
