// A folder for backups, or the backup folder to restore from. In One's window it comes from the system's folder
// dialog (folders only: the screens never ask for a file this way); in a plain browser, where there is no such
// dialog, the engineer types its path. Either way the core checks it before using it.
import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { type FormEvent, useId, useState } from "react";
import { field, secondary } from "../firstlaunch/parts";
import { t, useLanguage } from "../i18n";

/** The folder the engineer picked in the system dialog; null when they closed it. */
export async function pickFolder(): Promise<string | null> {
  const picked = await open({ directory: true, multiple: false });
  return typeof picked === "string" ? picked : null;
}

/** "Pick a folder": the dialog in One's window, a path field in a plain browser. */
export function FolderPicker({ label, onPicked, busy = false }: { label: string; onPicked: (path: string) => void; busy?: boolean }) {
  useLanguage();
  const id = useId();
  const [path, setPath] = useState("");

  if (isTauri())
    return (
      <button
        type="button"
        disabled={busy}
        className={`${secondary} self-start`}
        onClick={() => void pickFolder().then((picked) => picked && onPicked(picked))}
      >
        {label}
      </button>
    );

  function submit(event: FormEvent) {
    event.preventDefault();
    if (path.trim()) onPicked(path.trim());
  }
  return (
    <form onSubmit={submit} className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm text-slate">
        {t("backupFolderPath")}
      </label>
      <div className="flex gap-2">
        <input id={id} dir="ltr" value={path} onChange={(event) => setPath(event.target.value)} className={`${field} min-w-0 flex-1`} />
        <button type="submit" disabled={busy || !path.trim()} className={secondary}>
          {label}
        </button>
      </div>
    </form>
  );
}
