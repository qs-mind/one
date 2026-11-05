// A tender folder, as the engineer drops or chooses it: every file with its place inside the folder, then sent to
// the project one file at a time, so a 2 GB folder never sits in memory. The place goes up as `?folder=`, display
// text only: the core never reads a path from the page (decision 14). The report counts what the core made of each.
import { api } from "../api";

/** One file and the path of its folder inside what was dropped ("" for a file dropped on its own). */
export type Picked = { file: File; folder: string };

/** What came in: added and duplicates are counted; files kept but not read yet are counted; the rest are named. */
export type Report = {
  added: number;
  duplicates: number;
  notRead: number;
  tooBig: string[];
  unreadable: string[];
  /** Locked with a password (core: FILE_LOCKED): an open copy is needed. */
  locked: string[];
  /** Read, but its sheets are empty (core: FILE_SHEETS_EMPTY). */
  empty: string[];
  zips: number;
  /** Not added because the core refused or could not be reached: worth trying again. */
  failed: string[];
};

/** The core's limit for one file (core/qsone/records/files.py MAX_FILE_BYTES): a bigger one is never read here. */
export const MAX_FILE_BYTES = 256 * 1024 * 1024;

type Entry = FileSystemEntry;

function readBatch(reader: FileSystemDirectoryReader): Promise<Entry[]> {
  return new Promise((resolve, reject) => reader.readEntries(resolve, reject));
}

function fileOf(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

async function walkEntry(entry: Entry, parent: string, out: Picked[]): Promise<void> {
  if (entry.isFile) {
    out.push({ file: await fileOf(entry as FileSystemFileEntry), folder: parent });
    return;
  }
  if (!entry.isDirectory) return;
  const folder = parent ? `${parent}/${entry.name}` : entry.name;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // WebKit gives 100 entries at a time: read until a batch comes back empty
  for (let batch = await readBatch(reader); batch.length; batch = await readBatch(reader)) {
    for (const child of batch) await walkEntry(child, folder, out);
  }
}

/** The entries of a drop. They must be taken during the drop event itself: the browser empties the list after it. */
export function entriesOf(items: DataTransferItemList | undefined): Entry[] {
  return Array.from(items ?? []) // a drop made by a script may carry files only
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry())
    .filter((entry): entry is Entry => entry !== null);
}

/** Whether a drop holds a folder (and not only loose files). */
export function holdsFolder(items: DataTransferItemList | undefined): boolean {
  return entriesOf(items).some((entry) => entry.isDirectory);
}

/** Every file of a drop, nested folders included, in the order the folder lists them. */
export function fromDrop(items: DataTransferItemList): Promise<Picked[]> {
  return fromEntries(entriesOf(items));
}

/** The same, from entries already taken out of a drop (see entriesOf). */
export async function fromEntries(entries: Entry[]): Promise<Picked[]> {
  const out: Picked[] = [];
  for (const entry of entries) await walkEntry(entry, "", out);
  return out;
}

/** The files of "Choose folder" (`<input webkitdirectory>`), each with its folder from its relative path. */
export function fromInput(files: FileList | File[]): Picked[] {
  return Array.from(files).map((file) => {
    const path = file.webkitRelativePath || file.name;
    const cut = path.lastIndexOf("/");
    return { file, folder: cut > 0 ? path.slice(0, cut) : "" };
  });
}

/** The dropped folders, each with its files: what was dropped at the top, by its name. A file dropped on its own
 * makes a group of one, named after the file. */
export function byTopFolder(picked: Picked[]): { name: string; picked: Picked[] }[] {
  const groups = new Map<string, Picked[]>();
  for (const one of picked) {
    const top = one.folder ? one.folder.split("/")[0]! : one.file.name.replace(/\.[^.]+$/, "");
    groups.set(top, [...(groups.get(top) ?? []), one]);
  }
  return [...groups].map(([name, files]) => ({ name, picked: files }));
}

/** Old work from "Choose folder", which gives one folder: the old projects are the folders inside it, each with its
 * files; files loose in it make one more, named after it. */
export function oldProjects(picked: Picked[]): { name: string; picked: Picked[] }[] {
  const groups = new Map<string, Picked[]>();
  for (const one of picked) {
    const [root = "", project, ...rest] = one.folder.split("/");
    const name = project ?? (root || one.file.name.replace(/\.[^.]+$/, ""));
    const inside = project ? { file: one.file, folder: [project, ...rest].join("/") } : one;
    groups.set(name, [...(groups.get(name) ?? []), inside]);
  }
  return [...groups].map(([name, files]) => ({ name, picked: files }));
}

type FileAnswer = { status?: string; duplicate?: boolean; note_key?: string | null };
type ZipAnswer = { zip: true; files: FileAnswer[]; skipped: { name: string; error?: { en?: string } }[] };

function count(report: Report, info: FileAnswer, name: string) {
  if (info.duplicate) return void (report.duplicates += 1);
  report.added += 1;
  if (info.note_key === "FILE_LOCKED") report.locked.push(name);
  else if (info.note_key === "FILE_SHEETS_EMPTY") report.empty.push(name);
  else if (info.status === "stored") report.notRead += 1;
  else if (info.status === "unreadable") report.unreadable.push(name);
}

/** Sends each file to the project, one at a time, and says how many are done after each. */
export async function upload(
  projectId: string,
  picked: Picked[],
  onProgress: (done: number, of: number) => void,
): Promise<Report> {
  const report: Report = { added: 0, duplicates: 0, notRead: 0, tooBig: [], unreadable: [], locked: [], empty: [], zips: 0, failed: [] };
  onProgress(0, picked.length);
  for (const [index, { file, folder }] of picked.entries()) {
    if (file.size > MAX_FILE_BYTES) {
      report.tooBig.push(file.name);
    } else {
      const query = `name=${encodeURIComponent(file.name)}${folder ? `&folder=${encodeURIComponent(folder)}` : ""}`;
      const response = await api(`/projects/${encodeURIComponent(projectId)}/files?${query}`, {
        method: "POST",
        body: file,
      }).catch(() => undefined);
      const body = response?.ok ? ((await response.json().catch(() => undefined)) as FileAnswer | ZipAnswer | undefined) : undefined;
      if (body && "zip" in body && body.zip) {
        report.zips += 1;
        for (const member of body.files) count(report, member, file.name);
        // a zip skips a member for one of two reasons (core/qsone/projects.py add_upload): over 256 MB, or empty
        for (const skipped of body.skipped) {
          if (/empty/i.test(skipped.error?.en ?? "")) report.unreadable.push(skipped.name);
          else report.tooBig.push(skipped.name);
        }
      } else if (body) {
        count(report, body as FileAnswer, file.name);
      } else if (response?.status === 413) {
        report.tooBig.push(file.name);
      } else if (response?.status === 422) {
        report.unreadable.push(file.name); // empty, or not a file the core can take
      } else {
        report.failed.push(file.name);
      }
    }
    onProgress(index + 1, picked.length);
  }
  return report;
}
