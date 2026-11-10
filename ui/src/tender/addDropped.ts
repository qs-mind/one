// What the engineer drops on a tender's message box goes into the tender, as a folder dropped on Home does
// (folderDrop.ts): each file with its place inside a dropped folder, then ONE's own report of what came in, which
// starts its reading. Answers how many new files went in (0: all were here already), or null when none could.
import { addFile, reportFiles } from "@/api/existing";
import type { PromptInputAttachment } from "@/conversation/ai/prompt-input";
import { walk } from "@/home/folderDrop";

export async function addDropped(projectId: string, dropped: readonly PromptInputAttachment[]): Promise<number | null> {
  const picked: { file: File; folder: string }[] = [];
  for (const item of dropped) {
    if (item.file) picked.push({ file: item.file, folder: "" });
    else if (item.entry) await walk(item.entry, "", picked).catch(() => undefined);
  }
  const ids: string[] = [];
  let took = false;
  for (const { file, folder } of picked) {
    const { data } = await addFile(projectId, file, folder);
    if (data) took = true;
    for (const one of data && "files" in data ? data.files : data ? [data] : []) if (!one.duplicate && one.id) ids.push(one.id);
  }
  if (!took) return null;
  if (ids.length && (await reportFiles(projectId, ids)).error !== undefined) return null;
  return ids.length;
}
