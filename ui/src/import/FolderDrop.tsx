// Where a tender folder comes in when it is picked with "Choose folder" (the browser's folder chooser,
// `<input webkitdirectory>`; One's window has it too). A dropped folder is the window's (shell/WindowDrop.tsx).
import { useEffect, useRef } from "react";
import { importFolders } from "./importer";

let chooser: ((old: boolean) => void) | null = null;

/** "Choose folder" from anywhere (the top bar's More, say): a tender (old: false) or old work (old: true). */
export function chooseFolder(old: boolean) {
  chooser?.(old);
}

/** The one folder chooser, kept mounted, so a menu that closes when the system dialog opens does not lose it. */
export function FolderChooser() {
  const input = useRef<HTMLInputElement>(null);
  const old = useRef(false);
  useEffect(() => {
    chooser = (asOld) => {
      old.current = asOld;
      if (!input.current) return;
      input.current.value = "";
      input.current.click();
    };
    return () => {
      chooser = null;
    };
  }, []);
  return (
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
        if (files?.length) void importFolders(Array.from(files), { old: old.current });
      }}
    />
  );
}
