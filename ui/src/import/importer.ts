// The folder imports under way and their reports, one value for the page like records/project.ts, so an import
// started on the first launch's Ready screen carries on in the app. Three ways in:
// - a tender folder, with no project open: a new project named after the folder, its files, then the
//   "I understood this" Brief (POST /understand), whose card comes in the project chat. With a project open, the
//   folder goes into it; when a project of that name is here already, into that one: two projects never share a
//   name (the core refuses it, 409 with the one there);
// - old work: each folder its own project, archived without the AI step; "Understand it" later unarchives it first.
//   A name taken already gets "(2)", "(3)"…;
// - a folder dropped on an open project's canvas: its files go into that project, with their folders.
import { useSyncExternalStore } from "react";
import { api } from "../api";
import { askForBackupFolder } from "../backup/ask";
import { coreLine, type Fix, fixOf, send } from "../core";
import { type Text, texts } from "../i18n";
import { currentProject, type Project, switchProject } from "../records/project";
import { byTopFolder, entriesOf, fromEntries, fromInput, oldProjects, type Picked, type Report, upload } from "./walk";

export type Job = {
  key: number;
  name: string;
  projectId?: string;
  old: boolean;
  /** A folder dropped on an open project: its files went into that project. */
  into?: boolean;
  /** Adding files: how many are done of how many. */
  done: number;
  total: number;
  report?: Report;
  /** The "I understood this" Brief: started, or not started with the core's reason. */
  understanding?: "started" | Text;
  /** The "I understood this" Brief, once started: the summary follows it (reading, waiting on its card, ended). */
  briefId?: string;
  /** What fixes the reason it did not start, as the core says (no AI connected: AI settings). */
  understandingFix?: Fix;
  /** Old work: archived. */
  archived?: boolean;
  /** The project was not made, or the files not sent: nothing more happens. */
  failed?: Text;
};

let jobs: Job[] = [];
let next = 1;
const listeners = new Set<() => void>();
const briefListeners = new Set<(projectId: string) => void>();

function changed(list: Job[]) {
  jobs = list;
  for (const listener of listeners) listener();
}

function update(key: number, change: Partial<Job>) {
  changed(jobs.map((job) => (job.key === key ? { ...job, ...change } : job)));
}

/** The imports, newest last. */
export function useImports(): Job[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => jobs,
  );
}

/** The report is read: it goes. */
export function dismiss(key: number) {
  changed(jobs.filter((job) => job.key !== key));
}

/** Tells the shell a Brief started in a project from here, so its chat shows it (the chat joins it). */
export function onBriefStarted(listener: (projectId: string) => void): () => void {
  briefListeners.add(listener);
  return () => void briefListeners.delete(listener);
}

export function briefStarted(projectId: string) {
  for (const listener of briefListeners) listener(projectId);
}

/** The picked files of a drop or a folder chooser, and whether they came from the chooser (one folder). A drop's
 * entries are taken now, while its event lasts. */
async function picking(source: DataTransfer | FileList | File[] | Picked[]): Promise<{ picked: Picked[]; chosen: boolean }> {
  if (Array.isArray(source) && (source.length === 0 || "folder" in source[0]!)) return { picked: source as Picked[], chosen: false };
  if (source instanceof FileList || Array.isArray(source)) return { picked: fromInput(source as FileList | File[]), chosen: true };
  const entries = entriesOf(source.items);
  return entries.length ? { picked: await fromEntries(entries), chosen: false } : { picked: fromInput(source.files), chosen: true };
}

async function create(name: string): Promise<{ project?: Project; taken?: Project; line?: Text }> {
  const response = await send("/projects", "POST", { name: name.slice(0, 200) });
  if (response?.ok) return { project: (await response.json()) as Project };
  if (response?.status === 409) {
    const body = (await response.clone().json().catch(() => ({}))) as { project?: Project };
    if (body.project) return { taken: body.project };
  }
  return { line: await coreLine(response, texts.projectNotCreated) };
}

/** Old work: a project of its own, "(2)", "(3)"… after the name when it is taken. */
async function createOwn(name: string): Promise<{ project?: Project; line?: Text }> {
  for (let n = 1; n <= 20; n++) {
    const made = await create(n === 1 ? name : `${name.slice(0, 190)} (${n})`);
    if (!made.taken) return made;
  }
  return { line: texts.projectNotCreated };
}

/** The project of that name, opened, for a tender folder to go into. */
async function openTaken(project: Project): Promise<Project | undefined> {
  const response = await send(`/projects/${encodeURIComponent(project.id)}/open`, "POST");
  return response?.ok ? ((await response.json()) as Project) : undefined;
}

async function understand(projectId: string): Promise<Pick<Job, "understanding" | "understandingFix" | "briefId">> {
  const response = await send(`/projects/${encodeURIComponent(projectId)}/understand`, "POST");
  if (response?.status === 202 || response?.status === 409) {
    const body = (await response.json().catch(() => ({}))) as { brief_id?: string; error?: Text; fix?: unknown };
    if (body.brief_id) {
      briefStarted(projectId);
      return { understanding: "started", briefId: body.brief_id };
    }
    if (body.error) return { understanding: body.error, understandingFix: fixOf(body.fix) };
  }
  return { understanding: await coreLine(response, texts.importFailed) };
}

async function run(job: Job, picked: Picked[], { understandAfter }: { understandAfter: boolean }) {
  const id = job.projectId!;
  const report = await upload(id, picked, (done, total) => update(job.key, { done, total }));
  update(job.key, { report });
  if (job.old) {
    const archived = await send(`/projects/${encodeURIComponent(id)}/archive`, "POST");
    update(job.key, { archived: archived?.ok === true });
    void send(`/projects/${encodeURIComponent(id)}/close`, "POST"); // old work is not left open
  } else if (understandAfter) {
    update(job.key, await understand(id));
  }
}

/** A dropped or chosen tender folder (old: false), or old work (old: true), each folder its own project. */
export async function importFolders(source: DataTransfer | FileList | File[] | Picked[], { old }: { old: boolean }) {
  const { picked, chosen } = await picking(source);
  if (!picked.length) return;
  const open = currentProject();
  if (!old && open && !open.archived_at) return importInto(open.id, picked); // the tender open now takes it
  // a tender is one project, named after the (first) folder; old work is one project per folder dropped, or per
  // folder inside the one chosen
  const groups = !old ? [{ name: byTopFolder(picked)[0]!.name, picked }] : chosen ? oldProjects(picked) : byTopFolder(picked);
  for (const group of groups) {
    const job: Job = { key: next++, name: group.name, old, done: 0, total: group.picked.length };
    changed([...jobs, job]);
    const made: { project?: Project; taken?: Project; line?: Text } = old ? await createOwn(group.name) : await create(group.name);
    const taken = made.taken ? await openTaken(made.taken) : undefined;
    if (taken) {
      // a tender of that name is here already: its files go into it, never into a second one
      update(job.key, { projectId: taken.id, into: true });
      switchProject(taken);
      await run({ ...job, projectId: taken.id, into: true }, group.picked, { understandAfter: false });
      continue;
    }
    if (!made.project) {
      update(job.key, { failed: made.line });
      continue;
    }
    job.projectId = made.project.id;
    update(job.key, { projectId: made.project.id });
    if (!old) switchProject(made.project); // the engineer works in the tender now
    void askForBackupFolder();
    await run(job, group.picked, { understandAfter: !old });
  }
}

/** A folder dropped on the open project's canvas: its files, with their folders, into that project. */
export async function importInto(projectId: string, source: DataTransfer | Picked[]) {
  const { picked } = await picking(source);
  if (!picked.length) return;
  const name = byTopFolder(picked)[0]!.name;
  const job: Job = { key: next++, name, projectId, old: false, into: true, done: 0, total: picked.length };
  changed([...jobs, job]);
  await run(job, picked, { understandAfter: false });
}

/** Old work, understood after all: it is opened and unarchived first (an archived project takes no change), then the
 * Brief starts, with its Brief Budget as any Brief. */
export async function understandIt(key: number) {
  const job = jobs.find((one) => one.key === key);
  if (!job?.projectId) return;
  const id = encodeURIComponent(job.projectId);
  const opened = await api(`/projects/${id}/open`, { method: "POST" }).catch(() => undefined);
  if (!opened?.ok) return update(key, { understanding: await coreLine(opened, texts.projectNotOpened) });
  const project = (await opened.json()) as Project;
  const back = await send(`/projects/${id}/unarchive`, "POST");
  if (!back?.ok) return update(key, { understanding: await coreLine(back, texts.importFailed) });
  switchProject({ ...project, archived_at: null });
  update(key, { archived: false, old: false, ...(await understand(job.projectId)) });
}

/** For the tests: no import, no listener. */
export function resetImports() {
  changed([]);
  briefListeners.clear();
}
