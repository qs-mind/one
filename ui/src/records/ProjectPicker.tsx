// Pick the project to work in, or create one. The core lists every project on this computer, newest first;
// one it cannot read is listed with the reason, never hidden.
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { pick, t, type Text, texts, useLanguage } from "../i18n";
import { coreLine } from "../settings/Model";
import { type Project, switchProject, useProject } from "./project";

type Listed = (Project & { open: boolean }) | { id: string; error: Text };
type List = { state: "loading" } | { state: "ready"; projects: Listed[] } | { state: "failed"; line: Text };

export function ProjectPicker({ onClose }: { onClose: () => void }) {
  useLanguage();
  const title = useId();
  const current = useProject();
  const [list, setList] = useState<List>({ state: "loading" });
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const toFocus = useRef<HTMLButtonElement>(null);
  const nameField = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setList({ state: "loading" });
    const response = await fetch("/api/projects").catch(() => undefined);
    if (response?.ok)
      setList({ state: "ready", projects: ((await response.json()) as { projects: Listed[] }).projects });
    else setList({ state: "failed", line: await coreLine(response, texts.projectsFailed) });
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const projects =
    list.state === "ready" ? list.projects.filter((p): p is Project & { open: boolean } => "name" in p) : [];
  const focused = projects.some((p) => p.id === current?.id) ? current?.id : projects[0]?.id;

  useEffect(() => {
    // keyboard: the current project, or the first one, is one key press away; with none, the name field is
    if (list.state !== "ready") return;
    if (toFocus.current) toFocus.current.focus();
    else nameField.current?.focus();
  }, [list.state]);

  async function done(response: Response | undefined, fallback: Text) {
    setBusy(false);
    if (response?.ok) {
      switchProject((await response.json()) as Project);
      onClose();
    } else {
      setFailed(await coreLine(response, fallback));
    }
  }

  async function open(id: string) {
    setBusy(true);
    setFailed(undefined);
    await done(
      await fetch(`/api/projects/${id}/open`, { method: "POST" }).catch(() => undefined),
      texts.projectNotOpened,
    );
  }

  async function create(event: FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setFailed(undefined);
    const response = await fetch("/api/projects", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ name: trimmed }),
    }).catch(() => undefined);
    await done(response, texts.projectNotCreated);
  }

  return (
    <section aria-labelledby={title} className="border-b border-stone px-4 py-4">
      <div className="mx-auto flex max-w-2xl flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <h2 id={title} className="font-semibold">
            {t("projects")}
          </h2>
          <button type="button" onClick={onClose} className="text-slate hover:text-ink">
            {t("close")}
          </button>
        </div>
        {list.state === "loading" && <p className="text-slate">{t("projectsLoading")}</p>}
        {list.state === "failed" && (
          <div className="flex items-center gap-3">
            <p role="alert" className="text-copper">
              {pick(list.line)}
            </p>
            <button type="button" onClick={() => void load()} className="rounded-md border border-ink px-4 py-2">
              {t("retry")}
            </button>
          </div>
        )}
        {list.state === "ready" && list.projects.length === 0 && <p className="text-slate">{t("noProjects")}</p>}
        {list.state === "ready" && list.projects.length > 0 && (
          <ul className="flex max-h-[40dvh] flex-col gap-1 overflow-y-auto">
            {list.projects.map((item) =>
              "error" in item ? (
                <li key={item.id} className="flex flex-col px-3 py-2">
                  <span dir="ltr" className="text-slate">
                    {item.id}
                  </span>
                  <span className="text-copper">{pick(item.error)}</span>
                </li>
              ) : (
                <li key={item.id}>
                  <button
                    type="button"
                    ref={item.id === focused ? toFocus : undefined}
                    aria-current={item.id === current?.id || undefined}
                    disabled={busy}
                    onClick={() => void open(item.id)}
                    className={`flex w-full items-center justify-between gap-4 rounded-md px-3 py-2 text-start hover:bg-stone disabled:opacity-40 ${item.id === current?.id ? "bg-stone font-semibold" : ""}`}
                  >
                    <span dir="auto">{item.name}</span>
                    {item.id === current?.id && <span>{t("open")}</span>}
                  </button>
                </li>
              ),
            )}
          </ul>
        )}
        <form onSubmit={create} className="flex flex-col gap-2 border-t border-stone pt-3">
          <h3 className="font-semibold">{t("newProject")}</h3>
          <div className="flex items-end gap-2">
            <label className="flex flex-1 flex-col gap-1">
              <span>{t("projectName")}</span>
              <input
                ref={nameField}
                dir="auto"
                maxLength={200}
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="rounded-md border border-slate bg-paper px-3 py-2 outline-none focus:border-ink"
              />
            </label>
            <button
              type="submit"
              disabled={!name.trim() || busy}
              className="rounded-md bg-ink px-4 py-2 text-paper disabled:opacity-40"
            >
              {t("create")}
            </button>
          </div>
        </form>
        {failed && (
          <p role="alert" className="text-copper">
            {pick(failed)}
          </p>
        )}
      </div>
    </section>
  );
}
