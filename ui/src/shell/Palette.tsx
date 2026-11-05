// Search and commands (Ctrl/Cmd+K): the frames on the canvas by title (Enter focuses one), the shell's commands and
// the projects, and a search of Project Records (a hit opens its file's frame at its page). For now this is also the
// Project Index's quick way in: every Deliverable is a frame. Opened from the top bar's search field, it grows from
// the field in place (scaled and clipped from its rect, 220 ms) and closes back into it; from Ctrl K, it just opens.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { canvasApi } from "../canvas/api";
import type { FrameKey, ProjectSources } from "../canvas/types";
import { fill, language, pick, setLanguage, t, useLanguage } from "../i18n";
import { type Project, switchProject } from "../records/project";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { FileName } from "../ui/FileName";
import { DUR, play } from "../ui/motion";
import { withTransition } from "../ui/viewTransition";

type Hit = { file_id: string; file_name: string; locator: Record<string, string | number>; text: string };

const SEARCH_DELAY = 250;

/** Each frame's title in the page language, from the project's own lists. */
async function frameTitles(sources: ProjectSources): Promise<Map<FrameKey, string>> {
  const [files, deliverables, team, layout] = await Promise.all([
    sources.files().catch(() => []),
    sources.deliverables().catch(() => []),
    sources.team().catch(() => ({ desks: [], agents: [] })),
    sources.layout().catch(() => undefined),
  ]);
  const titles = new Map<FrameKey, string>([
    ["files:all", t("projectFiles")],
    ["team:core", t("projectTeam")],
  ]);
  for (const f of files) titles.set(`file:${f.id}`, f.name);
  for (const d of deliverables) titles.set(`deliverable:${d.id}`, d.title);
  for (const d of team.desks) titles.set(`desk:${d.id}`, pick(d.name));
  for (const b of layout?.client_boqs ?? []) titles.set(`clientboq:${b.file_id}`, fill(t("clientBoqTitle"), { name: b.name }));
  return titles;
}

/** The palette's box as if it stood in `field`: moved there and scaled to its width, showing only its top band. */
function atField(box: DOMRect, field: DOMRect): Keyframe {
  const scale = box.width ? field.width / box.width : 1;
  const hidden = Math.max(0, box.height - field.height / scale);
  return {
    transformOrigin: "0 0",
    transform: `translate(${field.left - box.left}px, ${field.top - box.top}px) scale(${scale})`,
    clipPath: `inset(0 0 ${hidden}px 0 round ${8 / scale}px)`,
    opacity: 0,
  };
}
const inPlace: Keyframe = { transformOrigin: "0 0", transform: "none", clipPath: "inset(0 0 0 0 round 14px)", opacity: 1 };

// The dialog's box and the dim behind it (ui/dialog.tsx renders the dim just before the box).
function parts(input: HTMLElement | null) {
  const box = input?.closest<HTMLElement>("[role='dialog']") ?? undefined;
  const dim = box?.previousElementSibling instanceof HTMLElement ? box.previousElementSibling : undefined;
  return { box, dim };
}

export function Palette({
  open,
  origin,
  onOpenChange,
  project,
  sources,
  chatOpen,
  onToggleChat,
  onGeneralChat,
  onNewProject,
}: {
  open: boolean;
  /** The search field's place, when it opened the palette. */
  origin?: DOMRect;
  onOpenChange(open: boolean): void;
  project: Project | undefined;
  sources: ProjectSources | undefined;
  chatOpen: boolean;
  onToggleChat(): void;
  onGeneralChat(): void;
  onNewProject(): void;
}) {
  useLanguage();
  const [query, setQuery] = useState("");
  const [frames, setFrames] = useState<{ key: FrameKey; title: string }[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [hits, setHits] = useState<Hit[]>([]);
  const projectId = project?.id;
  const input = useRef<HTMLInputElement | null>(null);
  const closing = useRef(false);
  const refocus = useRef(false);

  useEffect(() => {
    // Radix gives the focus back only to a DialogTrigger, and the field is not one: back to the field, once the
    // dialog (and its focus trap) is gone
    if (open || !refocus.current) return;
    refocus.current = false;
    document.querySelector<HTMLElement>("[data-search-field]")?.focus();
  }, [open]);

  // Opened from the field: grow from it as the box appears, once for each box (never again on a re-render).
  const grown = useRef<HTMLElement>(undefined);
  const grow = useCallback(
    (node: HTMLInputElement | null) => {
      input.current = node;
      const { box, dim } = parts(node);
      if (!box || !origin || grown.current === box) return;
      grown.current = box;
      void play(box, [atField(box.getBoundingClientRect(), origin), inPlace], DUR.base);
      if (dim) void play(dim, [{ opacity: 0 }, { opacity: 1 }], DUR.base);
    },
    [origin],
  );

  // Escape or a click outside: back into the field (where it is now), then close. Choosing an item closes at once.
  async function change(next: boolean) {
    const { box, dim } = parts(input.current);
    if (next || !origin || !box) return onOpenChange(next);
    if (closing.current) return;
    closing.current = true;
    const field = document.querySelector("[data-search-field]")?.getBoundingClientRect() ?? origin;
    await Promise.all([
      play(box, [inPlace, atField(box.getBoundingClientRect(), field)], DUR.base),
      dim && play(dim, [{ opacity: 1 }, { opacity: 0 }], DUR.base),
    ]);
    for (const el of [box, dim]) el?.style.setProperty("opacity", "0"); // its end state until it is gone
    closing.current = false;
    refocus.current = true;
    onOpenChange(false);
  }

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setHits([]);
    let live = true;
    void api("/projects")
      .then((r) => (r.ok ? (r.json() as Promise<{ projects: (Project | { id: string; error: unknown })[] }>) : undefined))
      .then((body) => live && body && setProjects(body.projects.filter((p): p is Project => "name" in p)))
      .catch(() => undefined);
    if (sources) {
      const keys = canvasApi.frames().map((f) => f.key);
      void frameTitles(sources).then(
        (titles) => live && setFrames(keys.flatMap((key) => (titles.has(key) ? [{ key, title: titles.get(key)! }] : []))),
      );
    }
    return () => {
      live = false;
    };
  }, [open, sources]);

  useEffect(() => {
    // Project Records search, once the engineer stops typing
    const q = query.trim();
    if (!open || !projectId || !q) {
      setHits([]);
      return;
    }
    const controller = new AbortController();
    const timer = setTimeout(() => {
      void api(`/projects/${encodeURIComponent(projectId)}/search?q=${encodeURIComponent(q)}&k=10`, {
        signal: controller.signal,
      })
        .then((r) => (r.ok ? (r.json() as Promise<{ results: Hit[] }>) : undefined))
        .then((body) => !controller.signal.aborted && setHits(body?.results ?? []))
        .catch(() => undefined);
    }, SEARCH_DELAY);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [open, projectId, query]);

  function run(action: () => void) {
    onOpenChange(false);
    action();
  }

  async function openProject(id: string) {
    const response = await api(`/projects/${encodeURIComponent(id)}/open`, { method: "POST" }).catch(() => undefined);
    if (response?.ok) switchProject((await response.json()) as Project);
  }

  const command = (label: string, action: () => void) => (
    <CommandItem key={label} value={label} onSelect={() => run(action)}>
      {label}
    </CommandItem>
  );

  return (
    <CommandDialog title={t("palette")} open={open} onOpenChange={(next) => void change(next)}>
      <CommandInput ref={grow} value={query} onValueChange={setQuery} placeholder={t("paletteSearch")} />
      <CommandList>
        <CommandEmpty>{t("noResults")}</CommandEmpty>
        {project && frames.length > 0 && (
          <CommandGroup heading={t("paletteFrames")}>
            {frames.map((frame) => (
              <CommandItem key={frame.key} value={`${frame.title} ${frame.key}`} onSelect={() => run(() => canvasApi.focusFrame(frame.key))}>
                <span dir="auto">{frame.title}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandGroup heading={t("paletteCommands")}>
          {project && command(t("fitAll"), () => canvasApi.fitAll())}
          {project && command(t("arrangeByStage"), () => canvasApi.arrange("stage"))}
          {project && command(t("tidy"), () => canvasApi.arrange("tidy"))}
          {project && command(t(chatOpen ? "closeChat" : "openChat"), onToggleChat)}
          {command(t("otherLanguage"), () => void withTransition(() => setLanguage(language() === "ar" ? "en" : "ar")))}
          {project && command(t("generalChat"), onGeneralChat)}
          {command(t("newProject"), onNewProject)}
        </CommandGroup>
        {projects.length > 0 && (
          <CommandGroup heading={t("projects")}>
            {projects
              .filter((p) => p.id !== projectId)
              .map((p) => (
                <CommandItem key={p.id} value={`${p.name} ${p.id}`} onSelect={() => run(() => void openProject(p.id))}>
                  <span dir="auto">{p.name}</span>
                </CommandItem>
              ))}
          </CommandGroup>
        )}
        {hits.length > 0 && (
          <CommandGroup heading={t("paletteRecords")} forceMount>
            {hits.map((hit, index) => {
              const page = typeof hit.locator.page === "number" ? hit.locator.page : undefined;
              return (
                <CommandItem
                  key={index}
                  forceMount
                  value={`hit ${index} ${hit.file_id}`}
                  onSelect={() => run(() => canvasApi.openFile(hit.file_id, page))}
                  className="flex-col items-start"
                >
                  <span className="text-slate">
                    <FileName name={hit.file_name} />
                    {page !== undefined && <> · {fill(t("page"), { page })}</>}
                  </span>
                  <span dir="auto" className="line-clamp-2">
                    {hit.text}
                  </span>
                </CommandItem>
              );
            })}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
