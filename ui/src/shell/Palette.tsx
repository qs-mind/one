// Search and commands (Ctrl/Cmd+K): the frames on the canvas by title (Enter focuses one), the shell's commands and
// the projects, and a search of Project Records (a hit opens its file's frame at its page). For now this is also the
// Project Index's quick way in: every Deliverable is a frame.
import { useEffect, useState } from "react";
import { canvasApi } from "../canvas/api";
import type { FrameKey, ProjectSources } from "../canvas/types";
import { fill, language, pick, setLanguage, t, useLanguage } from "../i18n";
import { type Project, switchProject } from "../records/project";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "../ui/command";
import { FileName } from "../ui/FileName";

type Hit = { file_id: string; file_name: string; locator: Record<string, string | number>; text: string };

const SEARCH_DELAY = 250;

/** Each frame's title in the page language, from the project's own lists. */
async function frameTitles(sources: ProjectSources): Promise<Map<FrameKey, string>> {
  const [files, deliverables, team] = await Promise.all([
    sources.files().catch(() => []),
    sources.deliverables().catch(() => []),
    sources.team().catch(() => ({ desks: [], agents: [] })),
  ]);
  const titles = new Map<FrameKey, string>([
    ["files:all", t("projectFiles")],
    ["team:core", t("projectTeam")],
  ]);
  for (const f of files) titles.set(`file:${f.id}`, f.name);
  for (const d of deliverables) titles.set(`deliverable:${d.id}`, d.title);
  for (const d of team.desks) titles.set(`desk:${d.id}`, pick(d.name));
  return titles;
}

export function Palette({
  open,
  onOpenChange,
  project,
  sources,
  chatOpen,
  onToggleChat,
  onGeneralChat,
  onNewProject,
}: {
  open: boolean;
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

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setHits([]);
    let live = true;
    void fetch("/api/projects")
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
      void fetch(`/api/projects/${encodeURIComponent(projectId)}/search?q=${encodeURIComponent(q)}&k=10`, {
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
    const response = await fetch(`/api/projects/${encodeURIComponent(id)}/open`, { method: "POST" }).catch(() => undefined);
    if (response?.ok) switchProject((await response.json()) as Project);
  }

  const command = (label: string, action: () => void) => (
    <CommandItem key={label} value={label} onSelect={() => run(action)}>
      {label}
    </CommandItem>
  );

  return (
    <CommandDialog title={t("palette")} open={open} onOpenChange={onOpenChange}>
      <CommandInput value={query} onValueChange={setQuery} placeholder={t("paletteSearch")} />
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
          {command(t("otherLanguage"), () => setLanguage(language() === "ar" ? "en" : "ar"))}
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
