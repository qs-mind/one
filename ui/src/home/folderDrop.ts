// A tender folder dropped on Home becomes a tender (contract S32): a project named after the folder, then each of its
// files with its place inside the folder (`?folder=`, display text only), then ONE's own report of what came in and
// the Lead's first reading of the tender. When a tender of that name is here already, the files go into it instead:
// two tenders never share a name (the core answers 409 with the one there).
import { api } from "@/api";
import type { Schemas } from "@/api/client";
import { home } from "@/texts/home";

type Text = Schemas["Text"];
type Entry = FileSystemEntry;
type Picked = { file: File; folder: string };

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
  if (entry.isFile) return void out.push({ file: await fileOf(entry as FileSystemFileEntry), folder: parent });
  if (!entry.isDirectory) return;
  const folder = parent ? `${parent}/${entry.name}` : entry.name;
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  // A folder gives its entries in batches (WebKit: 100): read until one comes back empty.
  for (let batch = await readBatch(reader); batch.length; batch = await readBatch(reader)) {
    for (const child of batch) await walk(child, folder, out);
  }
}

const post = (path: string, body?: unknown) =>
  api(path, {
    method: "POST",
    ...(body === undefined ? {} : { headers: { "content-type": "application/json" }, body: JSON.stringify(body) }),
  }).catch(() => undefined);

const json = async (response: Response | undefined) => (await response?.json().catch(() => undefined)) as Record<string, unknown> | undefined;
const isText = (value: unknown): value is Text =>
  typeof value === "object" && value !== null && typeof (value as Text).en === "string" && typeof (value as Text).ar === "string";
const idOf = (value: unknown) => (typeof value === "object" && value !== null && "id" in value ? String(value.id) : undefined);

/** The tender for the folder: a new one, or the one of that name already here (opened); the core's words if neither. */
async function tenderFor(name: string): Promise<{ id: string; made: boolean } | { refused: Text }> {
  const created = await post("/projects", { folder: name.slice(0, 200) });
  const body = await json(created);
  const id = idOf(body);
  if (created?.ok && id) return { id, made: true };
  const taken = created?.status === 409 ? idOf(body?.project) : undefined;
  if (taken && (await post(`/projects/${encodeURIComponent(taken)}/open`))?.ok) return { id: taken, made: false };
  return { refused: isText(body?.error) ? body.error : home.notMade };
}

/** Makes the tender of a dropped folder. `onTender` gets its id as soon as it exists (the screen opens it); the
 * files follow. Answers null, or the words to show when no tender could be made. */
export async function dropTender(entries: Entry[], onTender: (id: string) => void): Promise<Text | null> {
  const picked: Picked[] = [];
  for (const entry of entries) await walk(entry, "", picked).catch(() => undefined);
  const tender = await tenderFor(entries.find((entry) => entry.isDirectory)!.name);
  if ("refused" in tender) return tender.refused;
  onTender(tender.id);
  const at = `/projects/${encodeURIComponent(tender.id)}`;
  const ids: string[] = [];
  for (const { file, folder } of picked) {
    const query = `name=${encodeURIComponent(file.name)}${folder ? `&folder=${encodeURIComponent(folder)}` : ""}`;
    const answer = await api(`${at}/files?${query}`, { method: "POST", body: file }).catch(() => undefined);
    const body = answer?.ok ? await json(answer) : undefined;
    // A zip answers each file it held.
    const files = Array.isArray(body?.files) ? (body.files as unknown[]) : [body];
    for (const one of files) if (one && !(one as { duplicate?: boolean }).duplicate && idOf(one)) ids.push(idOf(one)!);
  }
  if (ids.length) await post(`${at}/files/report`, { file_ids: ids });
  if (tender.made) await post(`${at}/understand`);
  return null;
}
