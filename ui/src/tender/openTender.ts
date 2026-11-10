// Opens the tender in the core before the place reads it (POST /projects/{id}/open, a route of today): every
// /projects/{id}/... route but the tender view answers 409 PROJECT_NOT_OPEN for a closed project, and the place is
// reached by Home, the Rail, a link or a reload alike (S43). The opened project becomes the kept engines' current one
// (records/project.ts: Project files and the viewers read it), which closes the one open before it.
import { api } from "@/api";
import type { Schemas } from "@/api/client";
import { type Project, switchProject } from "@/records/project";

const isText = (value: unknown): value is Schemas["Text"] =>
  typeof value === "object" && value !== null && typeof (value as Schemas["Text"]).en === "string" && typeof (value as Schemas["Text"]).ar === "string";

/** The core's words when it refuses to open the tender; null when it opened, or gave no answer (the reads that come
 * next say that). `still()` is false once the place has moved on, and nothing is made current then. */
export async function openTender(projectId: string, still: () => boolean): Promise<Schemas["Text"] | null> {
  const response = await api(`/projects/${encodeURIComponent(projectId)}/open`, { method: "POST" }).catch(() => undefined);
  if (!response) return null;
  const body: unknown = await response.json().catch(() => undefined);
  if (!response.ok) {
    const words = (body as { error?: unknown } | undefined)?.error;
    return isText(words) ? words : null;
  }
  if (still()) switchProject(body as Project);
  return null;
}
