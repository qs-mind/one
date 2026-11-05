// The Backup panel: the folder backups go to, the last backup and "Back up now", where the Backup key is kept, and
// restoring from a backup folder. Without an account it offers the Backup key's recovery code, the only way to
// restore on another computer then. Also the one-time question, after the first project, of where to keep backups.
import { useCallback, useEffect, useId, useState } from "react";
import { isTauri } from "@tauri-apps/api/core";
import { api } from "../api";
import { coreLine, send } from "../core";
import { primary, quiet, secondary } from "../firstlaunch/parts";
import { fill, pick, t, type Text, texts, useLanguage } from "../i18n";
import { when } from "../review/place";
import { stopAsking } from "./ask";
import { FolderPicker, pickFolder } from "./folder";
import { RecoveryCode } from "./RecoveryCode";
import { Restore } from "./Restore";

type Status = {
  folder: string | null;
  reachable: boolean;
  last_run: string | null;
  note: Text | null;
  backup_key: { local: boolean; in_account: boolean; code_saved: boolean };
  projects: { id: string; last_backup: string | null; confidential: boolean }[];
};

/** The newest copy of any project in the folder. */
function lastBackup(status: Status): string | null {
  const times = status.projects.map((p) => p.last_backup).filter((at): at is string => !!at);
  return times.length ? times.sort().at(-1)! : null;
}

async function setFolder(path: string): Promise<{ status?: Status; line?: Text }> {
  const response = await send("/backup/folder", "PUT", { path });
  if (response?.ok) return { status: (await response.json()) as Status };
  return { line: await coreLine(response, texts.backupNotSaved) };
}

export function BackupPanel({ onClose }: { onClose: () => void }) {
  useLanguage();
  const title = useId();
  const [status, setStatus] = useState<Status>();
  const [failed, setFailed] = useState<Text>();
  const [running, setRunning] = useState(false);
  const [done, setDone] = useState<number>();
  const [code, setCode] = useState<string>(); // shown once: dropped as soon as it is confirmed or the panel closes
  const [restoring, setRestoring] = useState(false);

  const load = useCallback(async () => {
    const response = await api("/backup").catch(() => undefined);
    if (response?.ok) setStatus((await response.json()) as Status);
    else setFailed(await coreLine(response, texts.backupNotSaved));
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function choose(path: string) {
    setFailed(undefined);
    const answer = await setFolder(path);
    if (answer.status) {
      setStatus(answer.status);
      stopAsking();
    } else setFailed(answer.line);
  }

  async function runNow() {
    setRunning(true);
    setFailed(undefined);
    setDone(undefined);
    const response = await send("/backup/run", "POST", {});
    setRunning(false);
    if (response?.ok) {
      setDone(((await response.json()) as { backed_up: number }).backed_up);
      void load();
    } else setFailed(await coreLine(response, texts.backupNotSaved));
  }

  async function makeCode() {
    setFailed(undefined);
    const response = await send("/backup/recovery-code", "POST");
    if (response?.ok) setCode(((await response.json()) as { code: string }).code);
    else setFailed(await coreLine(response, texts.backupNotSaved));
  }

  const last = status && lastBackup(status);
  const key = status?.backup_key;

  return (
    <section aria-labelledby={title} className="flex flex-col gap-6 px-5 py-5">
      <div className="flex items-center justify-between gap-4">
        <h2 id={title} className="text-lg font-semibold">
          {t("backupTitle")}
        </h2>
        <button type="button" onClick={onClose} className={`${quiet} -me-3`}>
          {t("close")}
        </button>
      </div>

      {status && (
        <>
          <div className="flex flex-col gap-3">
            <h3 className="font-semibold">{t("backupFolder")}</h3>
            {status.folder ? (
              <p dir="ltr" className="truncate rounded-md bg-stone px-3 py-2 text-start text-sm">
                {status.folder}
              </p>
            ) : (
              <p className="text-slate">{t("backupNoFolder")}</p>
            )}
            {status.note && (
              <p role="alert" className="text-copper">
                {pick(status.note)}
              </p>
            )}
            <FolderPicker label={t("backupPickFolder")} onPicked={(path) => void choose(path)} />
          </div>

          <div className="flex flex-col gap-3">
            <p>{last ? fill(t("backupLast"), { date: when(last) }) : t("backupNever")}</p>
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" disabled={running || !status.folder} onClick={() => void runNow()} className={primary}>
                {running ? t("backupRunning") : t("backupNow")}
              </button>
              {done !== undefined && <span role="status">{fill(t("backupDone"), { n: done })}</span>}
            </div>
          </div>

          {key && (
            <div className="flex flex-col gap-3">
              <h3 className="font-semibold">{t("backupKeyTitle")}</h3>
              <ul className="flex flex-col gap-1">
                {(
                  [
                    ["backupKeyLocal", key.local],
                    ["backupKeyInAccount", key.in_account],
                    ["backupKeyCodeSaved", key.code_saved],
                  ] as const
                ).map(([label, yes]) => (
                  <li key={label} className={`flex items-center gap-2 ${yes ? "" : "text-slate"}`}>
                    <span aria-hidden="true" className="w-4 text-center">
                      {yes ? "✓" : "–"}
                    </span>
                    <span>{t(label)}</span>
                    <span className="sr-only">{yes ? t("yes") : t("no")}</span>
                  </li>
                ))}
              </ul>
              {!key.in_account && !code && (
                <>
                  <p className="text-slate">{t("backupKeyNoAccount")}</p>
                  <button type="button" onClick={() => void makeCode()} className={`${secondary} self-start`}>
                    {t("backupKeyMakeCode")}
                  </button>
                </>
              )}
              {code && (
                <RecoveryCode
                  code={code}
                  confirmPath="/backup/recovery-code/confirm"
                  onDone={() => {
                    setCode(undefined);
                    void load();
                  }}
                />
              )}
            </div>
          )}
        </>
      )}

      <div className="flex flex-col gap-3 border-t border-stone pt-5">
        {restoring ? (
          <Restore onChanged={() => void load()} />
        ) : (
          <button type="button" onClick={() => setRestoring(true)} className={`${secondary} self-start`}>
            {t("restoreTitle")}
          </button>
        )}
      </div>

      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}

/** The one-time question, after the first project: one quiet line at the chat's foot, so the chat keeps its room.
 * Its action picks a folder (the system dialog in ONE's window; a path field, opened in place, in a plain browser);
 * Later puts it away until the Backup panel. */
export function BackupAsk() {
  useLanguage();
  const [failed, setFailed] = useState<Text>();
  const [typing, setTyping] = useState(false);
  const use = (path: string) =>
    void setFolder(path).then((answer) => (answer.status ? stopAsking() : setFailed(answer.line)));
  return (
    <section
      aria-label={t("backupTitle")}
      className="flex w-full flex-wrap items-center gap-x-3 gap-y-1 rounded-[14px] border border-ink/[0.08] bg-paper px-4 py-1.5"
    >
      {/* its own line before the buttons squeeze it to a word a line: they wrap under it in a narrow chat */}
      <p dir="auto" className="min-w-0 flex-[1_1_12rem] break-words">
        {t("backupAskFolder")}
      </p>
      {!typing && (
        <button
          type="button"
          className={`${quiet} -my-1 text-ink`}
          onClick={() => (isTauri() ? void pickFolder().then((picked) => picked && use(picked)) : setTyping(true))}
        >
          {t("backupPickFolder")}
        </button>
      )}
      <button type="button" onClick={stopAsking} className={`${quiet} -my-1 -me-3`}>
        {t("backupLater")}
      </button>
      {typing && (
        <div className="w-full pb-2">
          <FolderPicker label={t("backupPickFolder")} onPicked={use} />
        </div>
      )}
      {failed && (
        <p role="alert" className="w-full text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}
