// Backup, restoring: the folder to restore from (looked in when the engineer leaves the box, or chosen with the
// system's folder picker in the installed app), the tenders found in it, each asking only for what it needs: nothing,
// a sign-in (in My profile), or a recovery code. A typed code is sent once and cleared; after each restore the folder
// is read again, since the first code also brings the Backup key to this computer and the others then need nothing.
import { isTauri } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import { useState } from "react";
import { Link } from "react-router";
import { findBackups, type FoundTender, restoreTender } from "@/api/settingsKept";
import { Field } from "@/design/Field";
import { ListRow } from "@/design/ListRow";
import { Button } from "@/design/ui/button";
import { Input } from "@/design/ui/input";
import { formatDate } from "@/texts/format";
import { textDir } from "@/texts/language";
import { settings as texts } from "@/texts/settings";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";

function FoundRow({ path, tender, onRestored }: { path: string; tender: FoundTender; onRestored: (name: string) => void }) {
  const t = useText();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<TextPair>();
  const needsCode = tender.needs === "backup_code" || tender.needs === "project_code";

  async function restore() {
    setBusy(true);
    setProblem(undefined);
    const answer = await restoreTender(path, tender.id, needsCode ? code.trim() : undefined);
    setBusy(false);
    setCode(""); // the code has done its work, or must be typed again: it is not kept
    if (answer.data) onRestored(answer.data.name);
    else setProblem(answer.error ?? texts.notRestored);
  }

  const title = tender.name ? <bdi dir={textDir(tender.name)}>{tender.name}</bdi> : t(texts.restoreHiddenName);
  return (
    <li className="flex flex-col gap-3">
      <ListRow
        frame="boxed"
        title={title}
        meta={t(texts.lastRun, { when: formatDate(new Date(tender.last_backup), t.lang) })}
        trailing={
          tender.needs === null ? (
            <Button variant="outline" loading={busy} onClick={() => void restore()}>
              {t(texts.restoreIt)}
            </Button>
          ) : undefined
        }
        className="flex-wrap"
      />
      {tender.needs === "sign_in" ? (
        <p className="text-xs">
          <Link to="../me" relative="path" className="underline">
            {t(texts.restoreNeedsSignIn)}
          </Link>
        </p>
      ) : null}
      {needsCode ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            void restore();
          }}
        >
          <Field
            label={t(texts.restoreCode)}
            help={t(tender.needs === "project_code" ? texts.restoreNeedsProjectCode : texts.restoreNeedsBackupCode)}
            className="flex-[1_1_18rem]"
          >
            <Input dir="ltr" autoComplete="off" spellCheck={false} className="font-mono" value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} />
          </Field>
          <Button type="submit" loading={busy} disabled={code.trim() === ""}>
            {t(texts.restoreIt)}
          </Button>
        </form>
      ) : null}
      {problem ? (
        <p role="alert" className="text-xs font-bold">
          {t(problem)}
        </p>
      ) : null}
    </li>
  );
}

export function Restore({ onChanged }: { onChanged: () => void }) {
  const t = useText();
  const [typed, setTyped] = useState("");
  const [looked, setLooked] = useState<{ path: string; found: FoundTender[] }>();
  const [problem, setProblem] = useState<TextPair>();
  const [back, setBack] = useState<string[]>([]); // said once each, not listed again

  async function look(path: string) {
    if (path === "") return;
    setProblem(undefined);
    const answer = await findBackups(path);
    if (answer.data) setLooked({ path, found: answer.data.projects });
    else {
      setLooked(undefined);
      setProblem(answer.error ?? texts.notRestored);
    }
  }

  async function choose() {
    const picked = await open({ directory: true }).catch(() => null);
    if (typeof picked !== "string") return;
    setTyped(picked);
    await look(picked);
  }

  return (
    <section aria-labelledby="restore" className="flex flex-col gap-4">
      <h2 id="restore" className="text-lg font-bold">
        {t(texts.restore)}
      </h2>
      <Field label={t(texts.restoreFolder)} help={t(texts.restoreFolderHelp)} error={problem ? t(problem) : undefined}>
        <Input
          dir="ltr"
          autoComplete="off"
          spellCheck={false}
          value={typed}
          onChange={(event) => setTyped(event.target.value)}
          onBlur={() => typed.trim() !== looked?.path && void look(typed.trim())}
          onKeyDown={(event) => event.key === "Enter" && void look(typed.trim())}
        />
      </Field>
      {isTauri() ? (
        <Button variant="outline" className="self-start" onClick={() => void choose()}>
          {t(texts.chooseFolder)}
        </Button>
      ) : null}
      {back.map((name) => (
        <p key={name} role="status">
          {t(texts.restored, { name })}
        </p>
      ))}
      {looked && looked.found.length === 0 ? <p className="text-muted-foreground">{t(texts.restoreNone)}</p> : null}
      {looked && looked.found.length > 0 ? (
        <ul className="flex flex-col gap-4">
          {looked.found.map((tender) => (
            <FoundRow
              key={tender.id}
              path={looked.path}
              tender={tender}
              onRestored={(name) => {
                setBack((now) => [...now, name]);
                onChanged(); // a code brings the Backup key here: the key's state says so at once
                void look(looked.path);
              }}
            />
          ))}
        </ul>
      ) : null}
    </section>
  );
}
