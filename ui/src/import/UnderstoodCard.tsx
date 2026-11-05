// The "I understood this" card, in the project chat once the Lead QS has read a tender folder (a data-understood
// part, which carries only the project; the card reads GET /projects/{id}/facts). Each fact shows its source ("file,
// page 3"); the engineer changes any of them (saved at once, by the engineer, with today's date as its source) and
// approves. Approving is the only way on: until then nothing else starts. A count is One's, from code.
import { type FormEvent, useCallback, useEffect, useId, useState } from "react";
import { api } from "../api";
import { coreLine, send } from "../core";
import { field, primary, quiet } from "../firstlaunch/parts";
import { fill, language, pick, t, type Text, texts, useLanguage } from "../i18n";
import { FileName } from "../ui/FileName";

type Source =
  | { kind: "file"; file_id: string; file_name: string | null; locator: Record<string, string | number> | null }
  | { kind: "engineer"; date: string }
  | { kind: "count"; trace_id: string }
  | { kind: string };
type Fact = { value: string; source: Source; by: "engineer" | "lead_qs" };
type Facts = {
  facts: Partial<Record<FactName, Fact>>;
  missing: string[];
  files: { file_id: string; name: string; folder: string | null; label: string; why: string }[];
  approved: boolean;
};
type FactName = "client" | "submission_date" | "contract_type" | "items_count";

const NAMES: [FactName, keyof typeof texts][] = [
  ["client", "understoodClient"],
  ["submission_date", "understoodSubmissionDate"],
  ["contract_type", "understoodContractType"],
  ["items_count", "understoodItemsCount"],
];

function day(date: string): string {
  const [y, m, d] = date.split("-").map(Number);
  if (!y || !m || !d) return date;
  return new Intl.DateTimeFormat(language() === "ar" ? "ar-EG-u-nu-latn" : "en-GB", { dateStyle: "medium" }).format(
    new Date(y, m - 1, d),
  );
}

/** Where a fact comes from, in words: "BOQ.xlsx, BOQ, row 12", "Tender letter.pdf, page 3", "You, 5 Nov 2026". */
export function sourceText(source: Source): string {
  if (source.kind === "engineer" && "date" in source) return fill(t("factSourceEngineer"), { date: day(source.date) });
  if (source.kind === "count") return t("factSourceCount");
  if (source.kind === "file" && "locator" in source) {
    const file = source.file_name ? `\u2068${source.file_name}\u2069` : ""; // isolated: an Arabic name in an English line
    const at = source.locator ?? {};
    if (at.page !== undefined) return fill(t("factSourcePage"), { file, page: at.page });
    if (at.sheet !== undefined && at.row !== undefined) return fill(t("factSourceRow"), { file, sheet: at.sheet, row: at.row });
    return fill(t("factSourceFile"), { file });
  }
  return "";
}

export function UnderstoodCard({ projectId }: { projectId: string }) {
  useLanguage();
  const id = encodeURIComponent(projectId);
  const [facts, setFacts] = useState<Facts>();
  const [editing, setEditing] = useState<FactName>();
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState<Text>();
  const [unfolded, setUnfolded] = useState(false);

  const load = useCallback(async () => {
    const response = await api(`/projects/${id}/facts`).catch(() => undefined);
    if (response?.ok) setFacts((await response.json()) as Facts);
  }, [id]);

  useEffect(() => {
    void load();
  }, [load]);

  async function put(body: { facts: Partial<Record<FactName, { value: string }>>; approve: boolean }): Promise<boolean> {
    setBusy(true);
    setFailed(undefined);
    const response = await send(`/projects/${id}/facts`, "PUT", body);
    setBusy(false);
    if (!response?.ok) {
      setFailed(await coreLine(response, texts.understoodNotSaved));
      return false;
    }
    setFacts((await response.json()) as Facts);
    return true;
  }

  if (!facts) return null;
  const approved = facts.approved;

  return (
    <section
      data-understood-card
      data-approved={approved || undefined}
      className={`flex min-w-0 flex-col rounded-[14px] ${approved ? "gap-3 bg-stone/70 px-4 py-2.5" : "gap-5 border border-copper bg-paper px-5 py-4"}`}
    >
      {approved ? (
        <h3 className="min-w-0">
          <button
            type="button"
            aria-expanded={unfolded}
            onClick={() => setUnfolded(!unfolded)}
            className="flex w-full min-w-0 items-baseline gap-2 text-start focus-visible:outline-2 focus-visible:outline-ink"
          >
            <span aria-hidden="true" className="shrink-0 text-slate">
              {unfolded ? "▾" : language() === "ar" ? "◂" : "▸"}
            </span>
            <span className="min-w-0 truncate font-semibold">{t("understoodTitle")}</span>
            <span className="shrink-0 text-slate">{t("understoodApproved")}</span>
          </button>
        </h3>
      ) : (
        <div className="flex flex-col gap-1">
          <h3 className="text-lg font-semibold">{t("understoodTitle")}</h3>
          <p className="text-slate">{t("understoodHelp")}</p>
        </div>
      )}

      <div hidden={approved && !unfolded} className="flex min-w-0 flex-col gap-5">
        <dl className="flex flex-col divide-y divide-ink/[0.06]">
          {NAMES.map(([name, label]) => (
            <FactRow
              key={name}
              name={name}
              label={t(label)}
              fact={facts.facts[name]}
              editing={editing === name}
              locked={approved || busy}
              onEdit={() => setEditing(name)}
              onCancel={() => setEditing(undefined)}
              onSave={async (value) => {
                if (await put({ facts: { [name]: { value } }, approve: false })) setEditing(undefined);
              }}
            />
          ))}
        </dl>

        {facts.missing.length > 0 && (
          <div className="flex flex-col gap-1">
            <h4 className="font-semibold">{t("understoodMissing")}</h4>
            <ul className="flex list-disc flex-col gap-0.5 ps-5">
              {facts.missing.map((doc, i) => (
                <li key={i} dir="auto">
                  {doc}
                </li>
              ))}
            </ul>
          </div>
        )}

        {facts.files.length > 0 && (
          <details className="group">
            <summary className="cursor-pointer font-semibold">
              {t("understoodFiles")} <span className="font-normal text-slate">({facts.files.length})</span>
            </summary>
            <ul className="mt-2 flex max-h-72 flex-col gap-2 overflow-y-auto">
              {facts.files.map((file) => (
                <li key={file.file_id} className="flex flex-col rounded-md bg-stone px-3 py-2">
                  <span className="flex flex-wrap items-baseline gap-x-2">
                    <span dir="auto" className="font-semibold">
                      {file.label}
                    </span>
                    <FileName name={file.name} className="min-w-0 truncate text-sm" />
                  </span>
                  {file.folder && (
                    <span dir="auto" className="truncate text-xs text-slate">
                      {file.folder}
                    </span>
                  )}
                  <span dir="auto" className="text-sm text-slate">
                    {file.why}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}

        {failed && (
          <p role="alert" className="text-copper">
            {pick(failed)}
          </p>
        )}
        {!approved && (
          <button
            type="button"
            disabled={busy || editing !== undefined}
            onClick={() => void put({ facts: {}, approve: true })}
            className={`${primary} self-start`}
          >
            {t("understoodApprove")}
          </button>
        )}
      </div>
    </section>
  );
}

function FactRow({
  name,
  label,
  fact,
  editing,
  locked,
  onEdit,
  onCancel,
  onSave,
}: {
  name: FactName;
  label: string;
  fact: Fact | undefined;
  editing: boolean;
  locked: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onSave: (value: string) => Promise<void>;
}) {
  const inputId = useId();
  const [value, setValue] = useState(fact?.value ?? "");
  useEffect(() => setValue(fact?.value ?? ""), [fact?.value, editing]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (value.trim()) void onSave(value.trim());
  }

  return (
    <div className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
      <dt className="text-sm text-slate">{editing ? <label htmlFor={inputId}>{label}</label> : label}</dt>
      <dd className="flex min-w-0 flex-col gap-1">
        {editing ? (
          <form onSubmit={submit} className="flex flex-wrap gap-2">
            <input
              id={inputId}
              dir="auto"
              type={name === "submission_date" ? "date" : "text"}
              inputMode={name === "items_count" ? "numeric" : undefined}
              maxLength={300}
              value={value}
              onChange={(event) => setValue(event.target.value)}
              className={`${field} min-w-0 flex-1`}
              autoFocus
            />
            <button type="submit" disabled={locked || !value.trim()} className={primary}>
              {t("save")}
            </button>
            <button type="button" onClick={onCancel} className={quiet}>
              {t("accountCancel")}
            </button>
          </form>
        ) : (
          <div className="flex min-w-0 items-start justify-between gap-3">
            <div className="flex min-w-0 flex-col">
              {fact ? (
                <span dir="auto" className="font-semibold break-words">
                  {name === "submission_date" ? day(fact.value) : fact.value}
                </span>
              ) : (
                <span className="text-slate">{t("understoodNotFound")}</span>
              )}
              {fact && <span className="text-sm text-slate">{sourceText(fact.source)}</span>}
            </div>
            {!locked && (
              <button type="button" onClick={onEdit} aria-label={`${t("understoodChange")}: ${label}`} className={`${quiet} -me-3 shrink-0`}>
                {t("understoodChange")}
              </button>
            )}
          </div>
        )}
      </dd>
    </div>
  );
}
