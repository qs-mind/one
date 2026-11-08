// A sourced name edits in place. Writes are serialized so a slow answer cannot undo a newer edit.
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { subscribeActivity } from "../activity";
import { coreLine } from "../core";
import { fill, pick, t, texts, type Text } from "../i18n";
import { workspaceApi } from "../workspace/api";
import { beforeClose, currentProject, setCurrentProject, type Project } from "./project";

export function ProjectName({ project }: { project: Project }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(project.name);
  const [error, setError] = useState<Text>();
  const pending = useRef(Promise.resolve());
  const saved = useRef(project.name);
  const typed = useRef(false);
  const latest = useRef(value);
  latest.current = value;

  useEffect(() => {
    const refresh = async () => {
      const before = currentProject();
      const response = await api("/projects").catch(() => undefined);
      if (response?.ok) {
        const next = ((await response.json()) as { projects: Project[] }).projects.find(p => p.id === project.id);
        if (next && currentProject() === before && before?.id === project.id) setCurrentProject(next);
      }
    };
    return subscribeActivity(project.id, event => {
      if (event.type === "project-name") void refresh();
    }, () => void refresh());
  }, [project.id]);

  function persist(name = value, close = true) {
    name = name.trim();
    if (!name) return pending.current;
    pending.current = pending.current.then(async () => {
      if (saved.current !== name) {
        const response = await api(`/projects/${project.id}`, {
          method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ name }),
        }).catch(() => undefined);
        if (!response?.ok) {
          setError(await coreLine(response, texts.projectNameNotUpdated));
          return;
        }
        const next = await response.json() as Project;
        saved.current = name;
        if (currentProject()?.id === project.id) setCurrentProject(next);
      }
      if (close && latest.current.trim() === name) setEditing(false);
      setError(undefined);
    });
    return pending.current;
  }

  useEffect(() => {
    if (!editing || value.trim() === saved.current) return;
    const timer = setTimeout(() => void persist(value, false), 400);
    return () => clearTimeout(timer);
  }, [value, editing]);
  useEffect(() => beforeClose(() => editing ? persist(latest.current, false) : pending.current), [editing, project.id]);

  const source = project.name_source;
  const shown = project.name_pair ? pick(project.name_pair) : project.name;
  return (
    <div className="flex min-w-0 items-center gap-2 text-ink">
      {editing ? (
        <input autoFocus dir="auto" aria-label={t("projectName")} maxLength={200} value={value}
          onChange={event => {
            if (!typed.current) saved.current = "";
            typed.current = true;
            setValue(event.target.value);
          }} onBlur={() => void persist()}
          onKeyDown={event => {
            if (event.key === "Enter") void persist();
            if (event.key === "Escape") { void persist(); }
          }}
          className="min-w-0 rounded border border-ink/20 bg-paper px-2 py-1" />
      ) : (
        <button type="button" dir="auto" disabled={!!project.archived_at}
          className="truncate rounded px-1 font-semibold focus-visible:outline-2 focus-visible:outline-ink"
          onClick={() => { saved.current = shown; typed.current = false; setValue(shown); setEditing(true); }}>
          {shown}
        </button>
      )}
      {source && (
        <button type="button" className="text-xs text-slate" onClick={() => workspaceApi.open(`file:${source.file_id}`, { page: source.locator.page })}>
          {source.file} · {fill(t("page"), { page: source.locator.page })}
        </button>
      )}
      {error && <span role="alert" className="text-copper">{pick(error)}</span>}
    </div>
  );
}
