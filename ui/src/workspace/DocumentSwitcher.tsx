// The head of the open document: its title (the button that opens the list of every document of the project), then in
// Slate its state, Revision and, for sample data, «الأرقام عينة». The list: Deliverables newest first, the client BOQs,
// then Project files. Picking opens that document; a document ONE is working on has a Slate dot.
import { useState, type KeyboardEvent, type ReactNode } from "react";
import { rowParts } from "../deliverables/ProjectIndex";
import type { DeliverableInfo } from "../deliverables/types";
import { count, fill, t, useLanguage } from "../i18n";
import type { ClientBoqInfo, DocKey, FileInfo, Opened } from "../project/types";
import { FileName } from "../ui/FileName";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { workspaceApi } from "./api";

export type DocumentSwitcherProps = {
  deliverables: readonly DeliverableInfo[];
  clientBoqs: readonly ClientBoqInfo[];
  files: readonly FileInfo[];
  opened: Opened;
  working: ReadonlySet<DocKey>;
};

const newestFirst = (a: DeliverableInfo, b: DeliverableInfo) => b.updated_at.localeCompare(a.updated_at);

function statusWord(d: DeliverableInfo): string {
  return d.status === "signed_off" ? t("statusSignedOff") : d.status === "checked" ? fill(t("statusChecked"), { code: d.code ?? "" }) : t("statusDraft");
}

function Dot({ on }: { on: boolean }) {
  return on ? (
    <>
      <span data-working-dot aria-hidden className="size-2 shrink-0 rounded-full bg-slate" />
      <span className="sr-only">{t("docWorkingOn")}</span>
    </>
  ) : null;
}

export function DocumentSwitcher({ deliverables, clientBoqs, files, opened, working }: DocumentSwitcherProps) {
  useLanguage();
  const [open, setOpen] = useState(false);
  const sorted = [...deliverables].sort(newestFirst);

  const [kind, id] = [opened.key.slice(0, opened.key.indexOf(":")), opened.key.slice(opened.key.indexOf(":") + 1)];
  const current = kind === "deliverable" ? deliverables.find((d) => d.id === id) : undefined;
  const boq = kind === "clientboq" ? clientBoqs.find((b) => b.file_id === id) : undefined;
  const file = kind === "file" ? files.find((f) => f.id === id) : undefined;

  const title: ReactNode = current ? (
    <span dir="auto" lang={current.language}>
      {current.title}
    </span>
  ) : boq ? (
    <>
      {t("docClientBoq")} · <FileName name={boq.name} />
    </>
  ) : file ? (
    <FileName name={file.name} />
  ) : (
    t("projectFiles")
  );
  const state = current ? [statusWord(current), current.revision !== null ? fill(t("docRevision"), { n: current.revision }) : null] : [];
  const facts = [state.filter(Boolean).join(" · "), current?.sample ? t("sampleNumbers") : ""].filter(Boolean);

  const pick = (key: DocKey) => {
    workspaceApi.open(key);
    setOpen(false);
  };
  const move = (event: KeyboardEvent<HTMLElement>) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const items = [...event.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]')];
    const at = items.indexOf(document.activeElement as HTMLElement);
    const last = items.length - 1;
    const next =
      event.key === "Home" ? 0 : event.key === "End" ? last : at < 0 ? (event.key === "ArrowUp" ? last : 0) : (at + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };

  const item =
    "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-start hover:bg-stone focus-visible:bg-stone focus-visible:outline-2 focus-visible:outline-ink";
  const facts_ = "flex flex-wrap items-center gap-x-3 text-sm text-slate";

  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <Popover open={open} onOpenChange={setOpen}>
        <h1 className="text-xl font-semibold">
          <PopoverTrigger asChild>
            <button type="button" aria-haspopup="menu" className="inline-flex items-center gap-2 rounded-lg px-1 hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink">
              <Dot on={working.has(opened.key)} />
              {title}
              <span aria-hidden>▾</span>
            </button>
          </PopoverTrigger>
        </h1>
        <PopoverContent role="menu" aria-label={t("docSwitch")} className="flex max-h-[70vh] min-w-72 flex-col gap-1 overflow-y-auto p-2" onKeyDown={move}>
          {sorted.map((d) => {
            const key: DocKey = `deliverable:${d.id}`;
            const parts = rowParts(d);
            return (
              <button key={key} type="button" role="menuitem" className={`${item} flex-wrap`} onClick={() => pick(key)}>
                <Dot on={working.has(key)} />
                <span dir="auto" lang={d.language} className="font-semibold">
                  {d.title}
                </span>
                <span className={`${facts_} ms-auto`}>
                  <span>{parts.kind}</span>
                  <span>{d.revision !== null ? fill(t("docRevision"), { n: d.revision }) : "—"}</span>
                  {parts.status}
                  {(d.pending ?? 0) > 0 && <span>{count("sheetPending", d.pending ?? 0)}</span>}
                  {d.open_comments > 0 && <span className="text-copper">{count("openComments", d.open_comments)}</span>}
                </span>
              </button>
            );
          })}
          {clientBoqs.map((b) => {
            const key: DocKey = `clientboq:${b.file_id}`;
            return (
              <button key={key} type="button" role="menuitem" className={item} onClick={() => pick(key)}>
                <Dot on={working.has(key)} />
                <span>{t("docClientBoq")} ·</span>
                <FileName name={b.name} fit />
              </button>
            );
          })}
          <button type="button" role="menuitem" className={item} onClick={() => pick("files:all")}>
            <Dot on={working.has("files:all")} />
            {t("projectFiles")}
          </button>
        </PopoverContent>
      </Popover>
      {facts.length > 0 && (
        <p className="text-sm text-slate">
          {facts.map((f, i) => (
            <span key={f}>
              {i > 0 && <span> · </span>}
              <span>{f}</span>
            </span>
          ))}
        </p>
      )}
    </div>
  );
}
