// Where a tender folder comes in: dropped on the General chat (a new project named after it) or on an open project's
// canvas (into that project), or picked with "Choose folder" (the browser's folder chooser, `<input webkitdirectory>`;
// One's window has it too). Only folders: loose files dropped here are left to the drop targets that take files.
import { type DragEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { t, useLanguage } from "../i18n";
import { importFolders } from "./importer";
import { holdsFolder } from "./walk";

/** The General chat's drop target: a dropped folder becomes a new project. */
export function FolderDrop({ children, className = "" }: { children: ReactNode; className?: string }) {
  useLanguage();
  const [over, setOver] = useState(false);
  const depth = useRef(0); // dragenter and dragleave come for every child: count them

  const carriesFiles = (event: DragEvent) => event.dataTransfer.types.includes("Files");
  return (
    <div
      className={`relative ${className}`}
      onDragEnter={(event) => {
        if (!carriesFiles(event)) return;
        depth.current += 1;
        setOver(true);
      }}
      onDragOver={(event) => {
        if (carriesFiles(event)) event.preventDefault();
      }}
      onDragLeave={() => {
        depth.current = Math.max(0, depth.current - 1);
        if (depth.current === 0) setOver(false);
      }}
      onDrop={(event) => {
        depth.current = 0;
        setOver(false);
        if (!carriesFiles(event)) return;
        event.preventDefault(); // the window must not open what was dropped
        if (holdsFolder(event.dataTransfer.items)) void importFolders(event.dataTransfer, { old: false });
      }}
    >
      {children}
      {over && (
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-3 z-20 flex items-center justify-center rounded-[14px] border-2 border-dashed border-ink/40 bg-stone/90"
        >
          <p className="text-lg font-semibold">{t("importDrop")}</p>
        </div>
      )}
    </div>
  );
}

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
