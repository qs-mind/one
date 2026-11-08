import { importFolders } from "./importer";
import { nativeFiles, type NativeFile } from "./native";
export type DesktopDrop = { files: NativeFile[]; errors: { name: string; reason: string }[] };
export async function receiveDesktopDrop(drop: DesktopDrop) {
  if (drop.files.length) await importFolders(nativeFiles(drop.files), { old: false });
}
