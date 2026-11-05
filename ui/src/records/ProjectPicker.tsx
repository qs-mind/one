// Pick the chat to work in: the General chat outside every project, or a project; or create one. A narrow, calm list
// under the project button: each row with what its Briefs are doing (a mark and a word), a search field once there
// are more than six projects, and "New project" as one row that turns into a field (Enter creates, Escape cancels).
// No Close button: Escape or a click outside closes it (FloatingPanel). The arrow keys move between the rows (one
// tab stop), and one Stone block glides behind the row reached. The core lists every project on this computer, newest
// first; one it cannot read is listed with the reason, never hidden. Archived projects come last, each marked.
import { type KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { askForBackupFolder } from "../backup/ask";
import { coreLine } from "../core";
import { ActivityMark, activityWord } from "../shell/ActivityMark";
import { GENERAL, stateOf, useActivity } from "../shell/chatActivity";
import { Glide } from "../ui/Glide";
import { useScrollEdges } from "../ui/useScrollEdges";
import { unarchive } from "./Archived";
import { currentProject, type Project, setCurrentProject, switchProject, useProject } from "./project";

type Listed = (Project & { open: boolean }) | { id: string; error: Text };
type List = { state: "loading" } | { state: "ready"; projects: Listed[] } | { state: "failed"; line: Text };

/** More projects than this, and a search field shows above them. */
export const SEARCH_FROM = 6;
const NEW = "new";

/** Goes to the General chat: no project is current, and the one that was is closed in the core. */
export function leaveProject() {
  const before = currentProject();
  setCurrentProject(undefined);
  if (before) void api(`/projects/${before.id}/close`, { method: "POST" }).catch(() => undefined);
}

/** Opens the project in the core and makes it current; the core's plain reason when it does not open. */
export async function openProject(id: string): Promise<Text | undefined> {
  const response = await api(`/projects/${encodeURIComponent(id)}/open`, { method: "POST" }).catch(() => undefined);
  if (!response?.ok) return coreLine(response, texts.projectNotOpened);
  switchProject((await response.json()) as Project);
  return undefined;
}

/** Goes to a chat by its id ("general" or a project's). */
export async function openChat(chatId: string): Promise<Text | undefined> {
  if (chatId !== GENERAL) return openProject(chatId);
  leaveProject();
  return undefined;
}

const row =
  "flex w-full items-center gap-3 rounded-[10px] px-3 py-1.5 text-start outline-none focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ink disabled:opacity-40";

export function ProjectPicker({ onClose }: { onClose: () => void }) {
  useLanguage();
  const current = useProject();
  const activity = useActivity();
  const [list, setList] = useState<List>({ state: "loading" });
  const [query, setQuery] = useState("");
  const [naming, setNaming] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [stop, setStop] = useState<string>(); // the row that holds the list's one tab stop
  const rows = useRef<HTMLUListElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const newRow = useRef<HTMLButtonElement>(null);
  const nameField = useRef<HTMLInputElement>(null);
  const backToNew = useRef(false);
  useScrollEdges(rows);

  const load = useCallback(async () => {
    setList({ state: "loading" });
    const response = await api("/projects").catch(() => undefined);
    if (response?.ok)
      setList({ state: "ready", projects: ((await response.json()) as { projects: Listed[] }).projects });
    else setList({ state: "failed", line: await coreLine(response, texts.projectsFailed) });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const listed = list.state === "ready" ? list.projects : [];
  const projects = listed.filter((p): p is Project & { open: boolean } => "name" in p);
  const searchable = projects.length > SEARCH_FROM;
  const needle = searchable ? query.trim().toLocaleLowerCase() : "";
  const shows = (text: string) => !needle || text.toLocaleLowerCase().includes(needle);
  const shown = listed.filter((p) => ("name" in p ? shows(p.name) : !needle));
  const working = shown.filter((p) => !("name" in p && p.archived_at));
  const archived = shown.filter((p) => "name" in p && p.archived_at);
  const general = shows(t("generalChat"));
  const firstKey = current && projects.some((p) => p.id === current.id) ? current.id : (projects[0]?.id ?? NEW);
  const keys = [...(general ? [GENERAL] : []), ...[...working, ...archived].filter((p) => "name" in p).map((p) => p.id), NEW];
  const tabStop = [stop, firstKey].find((key) => key !== undefined && keys.includes(key)) ?? keys[0];

  useEffect(() => {
    // keyboard: with many projects, the search field; else the current project, or the first one, one key press away
    if (list.state !== "ready") return;
    if (searchable) search.current?.focus();
    else rows.current?.querySelector<HTMLElement>(`[data-row="${firstKey}"]`)?.focus();
  }, [list.state]);

  useEffect(() => {
    if (naming) nameField.current?.focus();
    else if (backToNew.current) newRow.current?.focus();
    backToNew.current = false;
  }, [naming]);

  async function open(id: string) {
    setBusy(true);
    setFailed(undefined);
    const line = await openProject(id);
    setBusy(false);
    if (line) setFailed(line);
    else onClose();
  }

  async function create() {
    const trimmed = name.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setFailed(undefined);
    const response = await api("/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: trimmed }),
    }).catch(() => undefined);
    setBusy(false);
    if (!response?.ok) return setFailed(await coreLine(response, texts.projectNotCreated));
    switchProject((await response.json()) as Project);
    onClose();
    void askForBackupFolder();
  }

  function cancelNaming() {
    backToNew.current = true;
    setName("");
    setNaming(false);
  }

  /** Up and Down (Home, End) move between the rows; Up from the first goes back to the search field. */
  function move(event: KeyboardEvent) {
    const all = [...(rows.current?.querySelectorAll<HTMLElement>("[data-row]:not(:disabled)") ?? [])];
    const at = all.indexOf(document.activeElement as HTMLElement);
    const inSearch = document.activeElement === search.current;
    const typing = document.activeElement instanceof HTMLInputElement; // Home and End stay the field's own
    let next: HTMLElement | undefined | null;
    if (event.key === "ArrowDown") next = inSearch ? all[0] : all[Math.min(at + 1, all.length - 1)];
    else if (event.key === "ArrowUp") next = at <= 0 ? (searchable ? search.current : all[0]) : all[at - 1];
    else if (event.key === "Home" && !typing) next = all[0];
    else if (event.key === "End" && !typing) next = all.at(-1);
    if (!next || (at < 0 && !inSearch)) return;
    event.preventDefault();
    next.focus();
  }

  const rowProps = (key: string) => ({
    "data-row": key,
    tabIndex: key === tabStop ? 0 : -1,
    onFocus: () => setStop(key),
  });

  /** One chat's row: its name, then a word in Slate (Open, what its Briefs do with their mark, or archived). */
  const chatRow = (chatId: string, name: string, onClick: () => void, archived?: boolean) => {
    const here = chatId === (current?.id ?? GENERAL);
    const state = here ? undefined : stateOf(activity, chatId);
    const word = here ? t("open") : state ? activityWord(state) : archived ? t("archivedReadOnly") : undefined;
    return (
      <button
        type="button"
        {...rowProps(chatId)}
        aria-current={here || undefined}
        aria-label={word && `${name} ${word}`}
        disabled={busy}
        onClick={onClick}
        className={`${row} ${here ? "font-semibold" : ""}`}
      >
        <span dir="auto" className="min-w-0 break-words">
          {name}
        </span>
        {word && (
          <span className="ms-auto flex shrink-0 items-center gap-1.5 text-sm font-normal text-slate">
            {state && <ActivityMark state={state} />}
            {word}
          </span>
        )}
      </button>
    );
  };

  const item = (p: Listed) =>
    "error" in p ? (
      <li key={p.id} className="flex flex-col px-3 py-1.5 text-sm">
        <span dir="ltr" className="truncate text-slate">
          {p.id}
        </span>
        <span className="text-copper">{pick(p.error)}</span>
      </li>
    ) : p.archived_at ? (
      // an archived project: open it to read, or Unarchive it right here
      <li key={p.id} className="flex items-center gap-1">
        <div className="min-w-0 flex-1">{chatRow(p.id, p.name, () => void open(p.id), true)}</div>
        <button
          type="button"
          disabled={busy}
          aria-label={`${t("unarchiveProject")}: ${p.name}`}
          onClick={async () => {
            setBusy(true);
            setFailed(undefined);
            const line = await unarchive(p.id);
            setBusy(false);
            if (line) setFailed(line);
            else void load();
          }}
          className="shrink-0 rounded-lg border border-ink/15 px-2.5 py-1 text-sm hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40"
        >
          {t("unarchiveProject")}
        </button>
      </li>
    ) : (
      <li key={p.id}>{chatRow(p.id, p.name, () => void open(p.id))}</li>
    );

  return (
    <section aria-label={t("projects")} className="flex flex-col gap-1 p-1.5" onKeyDown={move}>
      {searchable && (
        <input
          ref={search}
          type="search"
          dir="auto"
          aria-label={t("findProject")}
          placeholder={t("findProject")}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key !== "Escape" || !query) return;
            event.preventDefault(); // the first Escape clears the search; the next one closes
            setQuery("");
          }}
          className="mx-0.5 mb-1 rounded-lg border border-ink/10 bg-stone/60 px-3 py-1.5 outline-none placeholder:text-slate focus:border-ink/30"
        />
      )}
      <ul ref={rows} className="scroll-fade relative isolate flex max-h-[min(60dvh,28rem)] flex-col gap-0.5 overflow-y-auto">
        {general && (
          <li>
            {chatRow(GENERAL, t("generalChat"), () => {
              leaveProject();
              onClose();
            })}
          </li>
        )}
        {list.state === "loading" && <li className="px-3 py-1.5 text-sm text-slate">{t("projectsLoading")}</li>}
        {working.map(item)}
        {archived.length > 0 && (
          <li role="presentation" className="px-3 pt-2 pb-0.5 text-xs text-slate">
            {t("archivedGroup")}
          </li>
        )}
        {archived.map(item)}
        {needle && !general && working.length + archived.length === 0 && (
          <li className="px-3 py-1.5 text-sm text-slate">{t("noProjectMatch")}</li>
        )}
        <li className="mt-0.5 border-t border-ink/[0.06] pt-0.5">
          {naming ? (
            <div className="flex items-center gap-1 px-1 py-0.5">
              <input
                ref={nameField}
                data-row={NEW}
                dir="auto"
                maxLength={200}
                aria-label={t("projectName")}
                placeholder={t("projectName")}
                value={name}
                disabled={busy}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    void create();
                  } else if (event.key === "Escape") {
                    event.preventDefault(); // cancels the new project; the list stays open
                    cancelNaming();
                  }
                }}
                onBlur={(event) => {
                  if (!name.trim() && !event.currentTarget.parentElement?.contains(event.relatedTarget as Node)) setNaming(false);
                }}
                className="min-w-0 flex-1 rounded-lg border border-ink/20 bg-paper px-2 py-1 outline-none focus:border-ink"
              />
              <button
                type="button"
                disabled={!name.trim() || busy}
                onClick={() => void create()}
                className="shrink-0 rounded-lg px-2.5 py-1 text-sm text-ink hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink disabled:opacity-40"
              >
                {t("create")}
              </button>
            </div>
          ) : (
            <button ref={newRow} type="button" {...rowProps(NEW)} onClick={() => setNaming(true)} className={`${row} text-slate`}>
              <span aria-hidden="true">+</span>
              <span>{t("newProject")}</span>
            </button>
          )}
        </li>
        <Glide as="li" />
      </ul>
      {list.state === "failed" && (
        <div className="flex items-center gap-2 px-3 py-1">
          <p role="alert" className="flex-1 text-sm text-copper">
            {pick(list.line)}
          </p>
          <button type="button" onClick={() => void load()} className="rounded-lg px-2.5 py-1 text-sm hover:bg-stone">
            {t("retry")}
          </button>
        </div>
      )}
      {failed && (
        <p role="alert" className="px-3 py-1 text-sm text-copper">
          {pick(failed)}
        </p>
      )}
    </section>
  );
}
