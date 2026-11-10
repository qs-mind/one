// Settings, Backup: the folder backups go to (saved when the engineer leaves the box, or chosen with the system's
// folder picker in the installed app), when the last backup was made, and "Back up now".
import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { useCallback, useEffect, useState } from "react";
import { type BackupState, getBackup, runBackup, setBackupFolder } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { Button } from "@/design/ui/button";
import { Input } from "@/design/ui/input";
import { formatDate } from "@/texts/format";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

type Line = { words: TextPair; strong?: boolean } | undefined;

/** The newest copy of any tender in the folder, or the core's last run. */
function lastBackup(state: BackupState): string | null {
  const times = state.projects.map((p) => p.last_backup).filter((at): at is string => Boolean(at));
  return times.sort().at(-1) ?? state.last_run;
}

export function Backup() {
  const t = useText();
  const [state, setState] = useState<BackupState | "failed">();
  const [typed, setTyped] = useState("");
  const [folderLine, setFolderLine] = useState<Line>();
  const [running, setRunning] = useState(false);
  const [runLine, setRunLine] = useState<Line>();

  const load = useCallback(async () => {
    const answer = await getBackup();
    setState(answer.data ?? "failed");
    if (answer.data) setTyped(answer.data.folder ?? "");
  }, []);
  useEffect(() => void load(), [load]);

  async function keep(path: string) {
    if (state === "failed" || state === undefined || path === "" || path === state.folder) return;
    setFolderLine({ words: texts.saving });
    const answer = await setBackupFolder(path);
    if (answer.data) {
      setState(answer.data);
      setFolderLine({ words: texts.saved });
    } else setFolderLine({ words: answer.error ?? texts.notSaved, strong: true });
  }

  async function choose() {
    const picked = await open({ directory: true }).catch(() => null);
    if (typeof picked !== "string") return;
    setTyped(picked);
    await keep(picked);
  }

  async function backUp() {
    setRunning(true);
    setRunLine(undefined);
    const answer = await runBackup();
    setRunning(false);
    setRunLine(answer.data ? { words: texts.backedUp } : { words: answer.error ?? texts.notBackedUp, strong: true });
    if (answer.data) void load();
  }

  if (state === undefined) return <div aria-busy="true" className="min-h-14" />;
  if (state === "failed") return <p className="text-xs font-bold">{t(texts.notLoaded)}</p>;
  const last = lastBackup(state);
  const folderHelp = folderLine && !folderLine.strong ? t(folderLine.words) : state.folder && !state.reachable ? t(texts.unreachable) : t(texts.folderHelp);
  return (
    <>
      <div className="flex flex-col gap-3">
        <Field label={t(texts.folder)} labelSize="lg" help={folderHelp} error={folderLine?.strong ? t(folderLine.words) : undefined}>
          <Input
            dir="ltr"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value);
              setFolderLine(undefined);
            }}
            onBlur={() => void keep(typed.trim())}
            onKeyDown={(event) => event.key === "Enter" && void keep(typed.trim())}
          />
        </Field>
        {isTauri() ? (
          <Button variant="outline" className="self-start" onClick={() => void choose()}>
            {t(texts.chooseFolder)}
          </Button>
        ) : null}
      </div>
      <section aria-labelledby="last-backup" className="flex flex-col gap-3">
        <p id="last-backup">{last ? t(texts.lastRun, { when: formatDate(new Date(last), t.lang) }) : t(texts.never)}</p>
        {state.note ? <p className="text-xs font-bold">{t(state.note)}</p> : null}
        <div className="flex flex-wrap items-center gap-4">
          <Button loading={running} disabled={!state.folder} onClick={() => void backUp()}>
            {t(texts.backUpNow)}
          </Button>
          <p aria-live="polite" className={runLine?.strong ? "text-xs font-bold" : "text-xs text-muted-foreground"}>
            {runLine ? t(runLine.words) : null}
          </p>
        </div>
      </section>
    </>
  );
}
