import { useContext, useEffect, useMemo, useRef, useState } from "react";
import { dir, fill, t, useLanguage } from "../../i18n";
import type { ProjectSources } from "../../project/types";
import { westernNumbers } from "../../ui/digits";
import { DocumentsContext } from "../documents";
import { workspaceApi } from "../api";
import { SourcePair } from "./CompareDoc";
import { FileDoc } from "./FileDoc";
import {
  anchorOf,
  type Fact,
  type FactSource,
  type Group,
  type Locator,
  mapApi,
  type MapFile,
  type MapLink,
  type MapPage,
} from "./mapApi";

const button =
  "rounded px-2 py-1 text-start hover:bg-stone focus-visible:outline-2 focus-visible:outline-ink";
export function ProjectMapDoc(
  { projectId, sources }: { projectId: string; sources: ProjectSources },
) {
  const lang = useLanguage();
  const documents = useContext(DocumentsContext);
  const api = useMemo(() => mapApi(projectId), [projectId]);
  const pagedFacts = useRef(false);
  const pagedLinks = useRef(false);
  const factPages = useRef(new Map<string, string | undefined>());
  const loadedParents = useRef(new Set<string>());
  const [pages, setPages] = useState<Record<string, MapPage>>({});
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [facts, setFacts] = useState<Fact[]>([]),
    [links, setLinks] = useState<MapLink[]>([]);
  const [factCursor, setFactCursor] = useState<string | null>(null),
    [linkCursor, setLinkCursor] = useState<string | null>(null);
  const [error, setError] = useState(false),
    [busy, setBusy] = useState(false),
    [scroll, setScroll] = useState(0);
  const [pair, setPair] = useState<MapLink | null>(null);
  useEffect(() => {
    let live = true;
    pagedFacts.current = false;
    pagedLinks.current = false;
    loadedParents.current.clear();
    factPages.current.clear();
    setPages({});
    setExpanded(new Set());
    setFacts([]);
    setLinks([]);
    setPair(null);
    setError(false);
    const mergePage = (old: MapPage | undefined, p: MapPage): MapPage =>
      !old ? p : {
        ...p,
        groups: [
          ...new Map([...old.groups, ...p.groups].map((g) => [g.path, g]))
            .values(),
        ],
        files: [
          ...new Map([...old.files, ...p.files].map((f) => [f.file_id, f]))
            .values(),
        ],
        next_cursor: old.next_cursor,
      };
    const refresh = async () => {
      try {
        const p = await api.page();
        if (!live) return;
        setPages((old) => ({ ...old, "": mergePage(old[""], p) }));
        const [f, l] = await Promise.all([api.facts(), api.links()]);
        if (!live) return;
        if (!pagedFacts.current) setFactCursor(f.next_cursor);
        if (!pagedLinks.current) setLinkCursor(l.next_cursor);
        f.facts.forEach((x) => factPages.current.set(x.id, undefined));
        setFacts(
          (old) => [
            ...new Map([...old, ...f.facts].map((x) => [x.id, x])).values(),
          ],
        );
        setLinks(
          (old) => [
            ...new Map([...old, ...l.links].map((x) => [x.id, x])).values(),
          ],
        );
        await Promise.all([...loadedParents.current].map(async (parent) => {
          const page = await api.page(parent);
          if (live) {
            setPages((old) => ({
              ...old,
              [parent]: mergePage(old[parent], page),
            }));
          }
        }));
      } catch {
        if (live) setError(true);
      }
    };
    void refresh();
    const timer = setInterval(() => void refresh(), 2000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [api]);
  async function load(parent: string, cursor?: string) {
    if (parent) loadedParents.current.add(parent);
    setBusy(true);
    try {
      const p = await api.page(parent || undefined, cursor);
      setPages((old) => ({
        ...old,
        [parent]: cursor && old[parent]
          ? {
            ...p,
            groups: [...old[parent].groups, ...p.groups],
            files: [...old[parent].files, ...p.files],
          }
          : p,
      }));
      setError(false);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  async function toggle(path: string) {
    setExpanded((old) => {
      const next = new Set(old);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
    if (expanded.has(path)) {
      for (const parent of loadedParents.current) {
        if (parent === path || parent.startsWith(path + "/")) {
          loadedParents.current.delete(parent);
        }
      }
    } else if (!pages[path]) await load(path);
    else loadedParents.current.add(path);
  }
  async function update(f: Fact, body: { confirm: true } | { value: string }) {
    setBusy(true);
    try {
      await api.update(f.id, body); // server acknowledgement, then re-read the authoritative fact page
      const p = await api.facts(factPages.current.get(f.id));
      if (!p.facts.some((x) => x.id === f.id)) throw new Error("missing fact");
      setFacts((old) =>
        old.map((item) => p.facts.find((x) => x.id === item.id) ?? item)
      );
      setError(false);
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  }
  const names = new Map(
    documents?.files.map((file) => [file.id, file.name]) ?? [],
  );
  Object.values(pages).forEach((page) =>
    page.files.forEach((file) => names.set(file.file_id, file.name))
  );
  const open = (fileId: string, l: Locator, box?: FactSource["box"]) =>
    workspaceApi.open(`file:${fileId}`, anchorOf(l, box));
  const chip = (
    fileId: string,
    l: Locator,
    label?: string,
    box?: FactSource["box"],
  ) => (
    <button
      type="button"
      className={`${button} shrink-0 border border-slate/20 text-xs text-copper`}
      onClick={() => open(fileId, l, box)}
    >
      {label ?? names.get(fileId) ?? fileId} {l.page
        ? fill(t("page"), { page: l.page })
        : l.sheet
        ? fill(t("sheetRow"), { sheet: l.sheet, row: l.row ?? "" })
        : fileId}
    </button>
  );
  type Row = { depth: number; group?: Group; file?: MapFile; more?: string };
  const rows: Row[] = [];
  function walk(parent: string, depth: number) {
    const p = pages[parent];
    if (!p) return;
    if (parent || p.status.total !== 1) {
      for (const group of p.groups) {
        rows.push({ depth, group });
        if (expanded.has(group.path)) walk(group.path, depth + 1);
      } // root API includes a flat file page as well as groups; avoid displaying duplicate files
    }
    if (parent || p.status.total === 1 || !p.groups.length) {
      for (const file of p.files) {
        rows.push({ depth, file });
      }
    }
    if (p.next_cursor) rows.push({ depth, more: parent });
  }
  walk("", 0);
  // Row positions are layout only; all project quantities come from the core.
  let height = 0;
  const positions = rows.map((row) => {
    const at = { top: height, height: row.file?.key_pages.length ? 56 : 32 };
    height += at.height;
    return at;
  });
  const visible = positions.findIndex((row) => row.top + row.height > scroll);
  const start = Math.min(
      Math.max(0, rows.length - 1),
      Math.max(0, (visible < 0 ? rows.length - 1 : visible) - 3),
    ),
    end = Math.min(rows.length, start + 25);
  const root = pages[""];
  return (
    <section
      role="region"
      aria-label={t("projectMap")}
      dir={dir()}
      className="flex h-full min-h-0 flex-col gap-2 bg-paper p-3 text-sm text-ink"
    >
      {error && (
        <p role="alert">
          {t("mapFailed")}{" "}
          <button className={button} onClick={() => void load("")}>
            {t("retry")}
          </button>
        </p>
      )}
      <p role="status" className="text-slate">
        {westernNumbers(root?.status.line[lang] ?? t("mapLoading"))}
      </p>
      {root?.status.total === 0 && <p>{t("mapEmpty")}</p>}
      <div
        className="min-h-48 flex-1 overflow-auto"
        data-map-scroll
        tabIndex={0}
        onScroll={(e) => setScroll(e.currentTarget.scrollTop)}
      >
        <div style={{ height, position: "relative" }}>
          {rows.slice(start, end).map((row, i) => (
            <div
              key={row.group?.path ?? row.file?.file_id ?? `more:${row.more}`}
              style={{
                position: "absolute",
                top: positions[start + i]!.top,
                height: positions[start + i]!.height,
                insetInlineStart: row.depth * 16,
                insetInlineEnd: 0,
              }}
              className="flex items-center gap-2 border-b border-slate/10"
            >
              {row.group && (
                <button
                  type="button"
                  aria-expanded={expanded.has(row.group.path)}
                  className={button}
                  onClick={() => void toggle(row.group!.path)}
                >
                  {expanded.has(row.group.path) ? "▾" : "▸"}{" "}
                  {row.group.label[lang]} · {row.group.count}
                </button>
              )}
              {row.file && (
                <div data-map-file className="min-w-0 w-full">
                  <div className="flex items-center gap-2">
                    <button
                      className={`${button} truncate`}
                      onClick={() => open(row.file!.file_id, {})}
                    >
                      <bdi>{row.file.name}</bdi>
                    </button>
                    <span className="shrink-0 text-xs text-slate">
                      {row.file.pages !== null &&
                        fill(t("mapPages"), { n: row.file.pages })} · {t(
                          row.file.read_how === "ocr"
                            ? "mapOcr"
                            : row.file.read_how === "mixed"
                            ? "mapMixed"
                            : row.file.read_how === "text"
                            ? "mapText"
                            : "mapStored",
                        )}
                    </span>
                    <span dir="auto" className="truncate text-slate">
                      {row.file.ai_title?.[lang]}
                    </span>
                  </div>
                  <div className="flex gap-1 overflow-x-auto">
                    {row.file.key_pages.map((k, j) => (
                      <span key={j}>
                        {chip(row.file!.file_id, k, k.label[lang])}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {row.more !== undefined && (
                <button
                  disabled={busy}
                  className={button}
                  onClick={() =>
                    void load(
                      row.more!,
                      pages[row.more!]?.next_cursor ?? undefined,
                    )}
                >
                  {t("mapMore")}
                </button>
              )}
            </div>
          ))}
        </div>
      </div>
      <div className="max-h-[45%] overflow-auto">
        {facts.length > 0 && (
          <h2 className="font-semibold">{t("mapSummary")}</h2>
        )}
        {facts.map((f) => (
          <div
            key={f.id}
            className="flex flex-wrap items-center gap-2 border-b border-slate/20 py-2"
          >
            <span>{f.name[lang]}</span>
            {f.corrected_value !== null && f.corrected_value !== undefined && (
              <del dir="auto" className="text-slate">{f.value}</del>
            )}
            <input
              key={`${f.id}:${f.corrected_value}`}
              aria-label={f.name[lang]}
              defaultValue={f.corrected_value ?? f.value ?? ""}
              className="min-w-16 w-36 bg-transparent"
              disabled={busy}
              onBlur={(e) => {
                if (
                  e.target.value !== (f.corrected_value ?? f.value ?? "")
                ) void update(f, { value: e.target.value });
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") e.currentTarget.blur();
              }}
            />
            <span>{f.unit} {f.currency}</span>
            {f.confirmed_at && (
              <time className="text-xs text-slate" dateTime={f.confirmed_at}>
                {f.confirmed_at}
              </time>
            )}
            {chip(f.file_id, f.locator, undefined, f.box)}
            <span className="text-xs text-slate">
              {t(
                f.confirmed_by || f.confirmed_at
                  ? "mapConfirmed"
                  : f.state === "blank"
                  ? "mapBlank"
                  : f.state === "conflict"
                  ? "mapConflict"
                  : "mapUnchecked",
              )}
            </span>
            {!f.confirmed_by && !f.confirmed_at && (
              <button
                disabled={busy}
                className={button}
                onClick={() => void update(f, { confirm: true })}
              >
                {t("mapConfirm")}
              </button>
            )}
            {!f.confirmed_by && !f.confirmed_at &&
              f.conflict_with.map((source, i) => {
                const other = typeof source === "string"
                  ? facts.find((x) => x.id === source)
                  : source;
                return other && (
                  <span key={i} className="flex items-center gap-2">
                    <bdi>{other.value}</bdi>
                    {chip(other.file_id, other.locator, undefined, other.box)}
                    <button
                      disabled={busy}
                      className={button}
                      onClick={() =>
                        void update(f, { value: other.value ?? "" })}
                    >
                      {t("mapChoose")}
                    </button>
                  </span>
                );
              })}
          </div>
        ))}
        {factCursor && (
          <button
            disabled={busy}
            className={button}
            onClick={() => {
              setBusy(true);
              pagedFacts.current = true;
              void api.facts(factCursor).then((p) => {
                p.facts.forEach((x) => factPages.current.set(x.id, factCursor));
                setFacts((old) => [...old, ...p.facts]);
                setFactCursor(p.next_cursor);
              }, () => setError(true)).finally(() => setBusy(false));
            }}
          >
            {t("mapMoreFacts")}
          </button>
        )}
        {links.length > 0 && (
          <h2 className="mt-2 font-semibold">{t("mapLinks")}</h2>
        )}
        {links.map((l) => (
          <div key={l.id} className="flex flex-wrap items-center gap-2 py-1">
            <button
              className={button}
              onClick={() =>
                setPair(l)}
            >
              {l.words[lang]}
            </button>
            {chip(l.from_file_id, l.from_locator)}
            {chip(l.to_file_id, l.to_locator)}
          </div>
        ))}
        {linkCursor && (
          <button
            disabled={busy}
            className={button}
            onClick={() => {
              setBusy(true);
              pagedLinks.current = true;
              void api.links(linkCursor).then((p) => {
                setLinks((old) => [...old, ...p.links]);
                setLinkCursor(p.next_cursor);
              }, () => setError(true)).finally(() => setBusy(false));
            }}
          >
            {t("mapMoreLinks")}
          </button>
        )}
      </div>
      {pair && (
        <div className="flex min-h-64 flex-1 flex-col">
          <button className={button} onClick={() => setPair(null)}>
            {t("close")}
          </button>
          <SourcePair>
            {[[pair.from_file_id, pair.from_locator], [
              pair.to_file_id,
              pair.to_locator,
            ]].map(([id, locator], i) => (
              <div key={`${pair.id}:${i}`} className="min-w-0 overflow-auto">
                <FileDoc
                  projectId={projectId}
                  sources={sources}
                  fileId={id as string}
                  opened={{
                    key: `file:${id as string}`,
                    anchor: anchorOf(locator as Locator),
                  }}
                />
              </div>
            ))}
          </SourcePair>
        </div>
      )}
    </section>
  );
}
