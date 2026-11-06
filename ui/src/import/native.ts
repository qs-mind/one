// Native selections keep paths in the desktop bridge; upload reads one file at a time.
import { invoke } from "@tauri-apps/api/core";
import type { Picked } from "./walk";

type NativeFile = { path: string; name: string; folder: string; size: number };
export async function nativeFolder(): Promise<Picked[] | null> {
  // Rust uses the existing dialog plugin's folder-only picker and records the allowed files.
  const files = await invoke<NativeFile[] | null>("folder_pick");
  if (!files) return null;
  return files.map(({ name, size, folder, path }) => ({
    file: { name, size }, folder,
    read: async () => {
      const buffer = await invoke<ArrayBuffer>("folder_read", { path });
      return new File([buffer], name);
    },
  }));
}
