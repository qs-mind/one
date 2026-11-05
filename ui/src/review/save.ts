// Saving a file the core made (an export, the Review report, the client's filled file). In the desktop app it goes
// through the `save_export` command, which opens the native Save dialog; in a browser (the dev preview, tests) it is
// a download. This is the only way project content reaches the disk in plain form, and only when the engineer asks.
import { invoke } from "@tauri-apps/api/core";

export type Saved = "saved" | "cancelled" | "downloaded";

const inTauri = () => typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

/** Saves `bytes` under `name` (the core's name, suggested in the dialog). Throws when the file could not be written. */
export async function saveBytes(name: string, bytes: Uint8Array, type = "application/octet-stream"): Promise<Saved> {
  if (inTauri()) {
    const saved = await invoke<boolean>("save_export", { name, bytes: Array.from(bytes) });
    return saved ? "saved" : "cancelled";
  }
  const url = URL.createObjectURL(new Blob([bytes as BlobPart], { type }));
  try {
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.rel = "noopener";
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  return "downloaded";
}
