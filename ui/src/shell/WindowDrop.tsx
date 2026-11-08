// Files dropped anywhere in the window (the chat, the top bar, the gutters, the document): one highlight over the whole
// window while files are dragged, and one place that takes them. With a project open, a folder (a tender's) goes into
// it with its folders and loose files go to Project Records, Project files opening to show them come, as the document
// area always did. In the General chat a folder becomes a new project (as before) and loose files ask which project
// they are for, or a new one: the projects list opens with that question, and they go into the project picked there.
// Browser drops stay with the page; desktop drops use OS paths enumerated and authorised by Rust.
import { isTauri } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { receiveDesktopDrop, type DesktopDrop } from "../import/desktopDrop";
import { nativeFiles } from "../import/native";
import { useEffect, useState } from "react";
import { t, useLanguage } from "../i18n";
import { importFolders, importInto } from "../import/importer";
import { holdsFolder } from "../import/walk";
import { currentProject } from "../records/project";
import { addToRecords } from "../records/RecordsPanel";
import { workspaceApi } from "../workspace/api";

// loose files dropped in the General chat, waiting for the engineer to pick their project
let waiting: File[] = [];
const askers = new Set<(n: number) => void>();

/** Asks which project `files` are for: the projects list opens with the question (App.tsx). */
function askForProject(files: File[]) {
  waiting = files;
  for (const ask of [...askers]) ask(files.length);
}

/** The projects list should ask which project `n` dropped files are for. */
export function onAskForProject(ask: (n: number) => void): () => void {
  askers.add(ask);
  return () => void askers.delete(ask);
}

/** The files waiting for a project, taken: they go into the one just opened. */
export function takeWaitingFiles(): File[] {
  const files = waiting;
  waiting = [];
  return files;
}

/** Files for the open project's Records: Project files opens (Back returns) and adds them. */
export function filesToRecords(files: File[]) {
  if (!files.length) return;
  if (workspaceApi.current()?.key !== "files:all") workspaceApi.open("files:all");
  addToRecords(files);
}

/** What a drop of files does, wherever in the window it lands. */
export function takeDrop(transfer: DataTransfer) {
  const project = currentProject();
  const folder = holdsFolder(transfer.items);
  if (project) {
    if (folder) return void importInto(project.id, transfer);
    return filesToRecords(Array.from(transfer.files));
  }
  if (folder) return void importFolders(transfer, { old: false });
  const files = Array.from(transfer.files);
  if (files.length) askForProject(files);
}

const carriesFiles = (event: DragEvent) => event.dataTransfer?.types?.includes("Files") ?? false;

/** The window's drop: taken here unless a part of the screen took it first; the highlight while files are over it. */
export function WindowDrop() {
  useLanguage();
  const [over, setOver] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  useEffect(() => {
    if (!isTauri()) return;
    let live = true;
    const subscriptions = [
      listen<boolean>("one-drop-hover", ({ payload }) => live && setOver(payload)),
      listen<DesktopDrop>("one-files-dropped", ({ payload }) => {
        if (!live) return;
        setErrors(payload.errors.map((e) => `${e.name}: ${e.reason}`));
        const receive = async () => {
          if (!currentProject() && payload.files.length && payload.files.every((file) => !file.folder)) {
            askForProject(await Promise.all(nativeFiles(payload.files).map((file) => file.read!())));
          } else await receiveDesktopDrop(payload);
        };
        void receive().catch(() => setErrors([t("importFollowupFailed")]));
      }),
    ];
    return () => { live = false; for (const subscription of subscriptions) void subscription.then((off) => off()); };
  }, []);
  useEffect(() => {
    if (isTauri()) return;
    let depth = 0; // dragenter and dragleave come for every element crossed: counted, so it never blinks
    const enter = (event: DragEvent) => {
      if (!carriesFiles(event)) return;
      depth += 1;
      setOver(true);
    };
    const leave = (event: DragEvent) => {
      if (!carriesFiles(event) || depth === 0) return;
      depth -= 1;
      if (depth === 0) setOver(false);
    };
    const end = () => {
      depth = 0;
      setOver(false);
    };
    const overIt = (event: DragEvent) => {
      if (carriesFiles(event)) event.preventDefault(); // the files may drop anywhere
    };
    const drop = (event: DragEvent) => {
      if (!carriesFiles(event)) return;
      if (event.defaultPrevented) return; // a part of the screen took it
      event.preventDefault();
      takeDrop(event.dataTransfer!);
    };
    // the highlight ends on any drop, even one a part of the screen stopped on its way (capture comes first)
    window.addEventListener("drop", end, true);
    window.addEventListener("dragenter", enter);
    window.addEventListener("dragleave", leave);
    window.addEventListener("dragend", end);
    window.addEventListener("dragover", overIt);
    window.addEventListener("drop", drop);
    return () => {
      window.removeEventListener("drop", end, true);
      window.removeEventListener("dragenter", enter);
      window.removeEventListener("dragleave", leave);
      window.removeEventListener("dragend", end);
      window.removeEventListener("dragover", overIt);
      window.removeEventListener("drop", drop);
    };
  }, []);
  if (!over) return errors.length ? <div role="alert" className="text-copper">{errors.map((error, i) => <p key={i}>{error}</p>)}<button onClick={() => setErrors([])}>{t("close")}</button></div> : null;
  return (
    <div
      data-window-drop
      aria-hidden="true"
      className="pointer-events-none fixed inset-2 z-[90] flex items-center justify-center rounded-[14px] border-2 border-dashed border-ink/40 bg-stone/80"
    >
      <p className="rounded-lg bg-paper px-4 py-2 text-lg font-semibold text-ink">
        {t(currentProject() ? "windowDropProject" : "windowDropGeneral")}
      </p>
    </div>
  );
}
