// What the engineer drops on a tender's message box goes into the tender, as a folder dropped on Home does
// (folderDrop.ts): each file with its place inside a dropped folder, then ONE's own report of what came in, which
// starts its reading. Answers how many new files went in (0: all were here already), or null when none could.
import { addFile, reportFiles } from "@/api/existing";
import type { PromptInputAttachment } from "@/conversation/ai/prompt-input";
import { walk } from "@/home/folderDrop";

type Picked = { folder: string; read: () => Promise<File> };

export async function addDropped(projectId: string, dropped: readonly PromptInputAttachment[]): Promise<number | null> {
  const picked: Picked[] = [];
  for (const item of dropped) {
    const file = item.file;
    if (file) picked.push({ folder: "", read: async () => file });
    else if (item.entry) await walk(item.entry, "", picked).catch(() => undefined);
  }
  return addPicked(projectId, picked);
}

/** Files already picked (a drop on the box, or the shell's drop on the window in the installed app) go in. */
export async function addPicked(projectId: string, picked: readonly Picked[]): Promise<number | null> {
  const ids: string[] = [];
  let took = false;
  for (const { read, folder } of picked) {
    const file = await read().catch(() => null);
    if (!file) continue;
    const { data } = await addFile(projectId, file, folder);
    if (data) took = true;
    for (const one of data && "files" in data ? data.files : data ? [data] : []) if (!one.duplicate && one.id) ids.push(one.id);
  }
  if (!took) return null;
  if (ids.length && (await reportFiles(projectId, ids)).error !== undefined) return null;
  return ids.length;
}
