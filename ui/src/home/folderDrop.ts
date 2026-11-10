// A tender folder dropped on Home becomes a tender (contract S32): a project named after the folder, then each of its
// files with its place inside the folder (`?folder=`, display text only), then ONE's own report of what came in and
// the Lead's first reading of the tender. When a tender of that name is here already, the files go into it instead:
// two tenders never share a name (the core answers 409 with the one there). In the browser the drop comes as the
// page's entries; in the installed app the shell takes it and sends the files it found (`one-files-dropped`), each
// read through the shell, one at a time (decision 14: the core never reads a path from the page).
import type { Schemas } from "@/api/client";
import { addFile, createProject, openProject, reportFiles, understand } from "@/api/existing";
import { nativeFiles, type NativeFile } from "@/import/native";
import { home } from "@/texts/home";

type Text = Schemas["Text"];
type Entry = FileSystemEntry;
type Picked = { folder: string; read: () => Promise<File> };
/** A dropped tender folder: its name and its files. */
export type DroppedFolder = { name: string; picked: Picked[] };
/** What the shell sends for a drop on the window (desktop/src/main.rs). */
export type DesktopDrop = { files: NativeFile[]; errors: { name: string; reason: string }[] };

/** The entries of a drop when it holds a folder; null for loose files only. Taken during the drop event itself:
 * the browser empties the list after it. */
export function folderOf(transfer: DataTransfer): Entry[] | null {
  const entries = [...(transfer.items ?? [])]
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry?.() ?? null)
    .filter((entry): entry is Entry => entry !== null);
  return entries.some((entry) => entry.isDirectory) ? entries : null;
}

const readBatch = (reader: FileSystemDirectoryReader) => new Promise<Entry[]>((resolve, reject) => reader.readEntries(resolve, reject));
const fileOf = (entry: FileSystemFileEntry) => new Promise<File>((resolve, reject) => entry.file(resolve, reject));

async function walk(entry: Entry, parent: string, out: Picked[]): Promise<void> {
  if (entry.isFile) {
    const file = await fileOf(entry as FileSystemFileEntry);
    return void out.push({ folder: parent, read: async () => file });
  }
  if (!entry.isDirectory) return;
  const folder = parent ? `${parent}/${entry.name}` : entry.name;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // A folder gives its entries in batches (WebKit: 100): read until one comes back empty.
  for (let batch = await readBatch(reader); batch.length; batch = await readBatch(reader)) {
    for (const child of batch) await walk(child, folder, out);
  }
}

/** The folder of a browser drop (from folderOf), its files walked. */
export async function walkedFolder(entries: Entry[]): Promise<DroppedFolder> {
  const picked: Picked[] = [];
  for (const entry of entries) await walk(entry, "", picked).catch(() => undefined);
  return { name: entries.find((entry) => entry.isDirectory)!.name, picked };
}

/** The folder of a drop the shell took; null when it held loose files only. The name is the first folder's. */
export function desktopFolder(drop: DesktopDrop): DroppedFolder | null {
  const first = drop.files.find((file) => file.folder);
  if (!first) return null;
  return { name: first.folder.split("/")[0]!, picked: nativeFiles(drop.files).map(({ folder, read }) => ({ folder, read: read! })) };
}

/** The tender for the folder: a new one, or the one of that name already here (opened); the core's words if neither. */
async function tenderFor(name: string): Promise<{ id: string; made: boolean } | { refused: Text }> {
  const created = await createProject(name.slice(0, 200));
  if ("id" in created) return { id: created.id, made: true };
  if ("taken" in created && (await openProject(created.taken)).error === undefined) return { id: created.taken, made: false };
  return { refused: ("error" in created && created.error) || home.notMade };
}

/** Makes the tender of a dropped folder. `onTender` gets its id as soon as it exists (the screen opens it); the
 * files follow. Answers null, or the words to show when no tender could be made. */
export async function dropTender(dropped: DroppedFolder, onTender: (id: string) => void): Promise<Text | null> {
  const tender = await tenderFor(dropped.name);
  if ("refused" in tender) return tender.refused;
  onTender(tender.id);
  const ids: string[] = [];
  for (const { read, folder } of dropped.picked) {
    const file = await read().catch(() => null);
    if (!file) continue;
    const { data } = await addFile(tender.id, file, folder);
    for (const one of data && "files" in data ? data.files : data ? [data] : []) if (!one.duplicate && one.id) ids.push(one.id);
  }
  if (ids.length) await reportFiles(tender.id, ids);
  if (tender.made) await understand(tender.id);
  return null;
}
