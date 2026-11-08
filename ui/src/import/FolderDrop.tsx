// Choose a tender folder: the native directory dialog in ONE, webkitdirectory in a browser.
// Files enter the same importer as a dropped folder (shell/WindowDrop.tsx).
import { isTauri } from "@tauri-apps/api/core";
import { nativeFolder } from "./native";
import { pick, texts, useLanguage } from "../i18n";
import { useEffect, useRef, useState } from "react";
import { importFolders } from "./importer";

let chooser: ((old: boolean, newProject?: boolean) => void) | null = null;

/** "Choose folder" from anywhere (the top bar's More, say): a tender (old: false) or old work (old: true). */
export function chooseFolder(old: boolean, newProject = false) {
  chooser?.(old, newProject);
}

/** The one folder chooser, kept mounted, so a menu that closes when the system dialog opens does not lose it. */
export function FolderChooser() {
  const lang = useLanguage();
  const [failed, setFailed] = useState<"selection" | "followup" | false>(false);
  const input = useRef<HTMLInputElement>(null);
  const old = useRef(false);
  const newProject = useRef(false);
  useEffect(() => {
    const clear = () => setFailed(false);
    window.addEventListener("one-files-added", clear);
    chooser = (asOld, asNew = false) => {
      old.current = asOld;
      newProject.current = asNew;
      setFailed(false);
      if (isTauri()) {
        void nativeFolder().then(async (files) => {
          if (!files) return;
          try { await importFolders(files, { old: asOld, chosen: true, ...(asNew ? { newProject: true } : {}) }); }
          catch { setFailed("followup"); }
        }, () => setFailed("selection"));
        return;
      }
      if (!input.current) return;
      input.current.value = "";
      input.current.click();
    };
    return () => {
      window.removeEventListener("one-files-added", clear);
      chooser = null;
    };
  }, []);
  return (
    <>
      {failed && <p role="alert" className="text-copper">{pick(texts[failed === "selection" ? "folderSelectionFailed" : "importFollowupFailed"], lang)} <button onClick={() => setFailed(false)}>{pick(texts.close, lang)}</button></p>}
      <input
        ref={input}
        type="file"
        hidden
        multiple
        data-folder-chooser
        // folder picking: not in React's input types
        {...{ webkitdirectory: "", directory: "" }}
        onChange={(event) => {
          const files = event.target.files;
          if (files?.length) void importFolders(Array.from(files), { old: old.current, ...(newProject.current ? { newProject: true } : {}) });
        }}
      />
    </>
  );
}
