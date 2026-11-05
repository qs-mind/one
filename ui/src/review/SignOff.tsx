// Close-out and Sign-off: what still blocks Sign-off, in the core's plain words (a pending change, an open Code C
// comment, no check on this version), and the Sign-off button, enabled only when nothing does. After Sign-off it
// shows the Revision and offers the Review report. "Issue Revision" issues one without signing off.
import { useEffect, useState } from "react";
import { deliverablesApi } from "../deliverables/api";
import type { CloseOut, View } from "../deliverables/types";
import { fill, pick, t, type Text } from "../i18n";
import { saveAnswer } from "./save";

export type SignOffProps = {
  projectId: string;
  view: View;
  onChanged: () => void;
  announce?: (line: string) => void;
};

export function SignOff({ projectId, view, onChanged, announce }: SignOffProps) {
  const [closeout, setCloseout] = useState<CloseOut | null>(null);
  const [failed, setFailed] = useState<Text | string | null>(null);
  const [busy, setBusy] = useState(false);
  const signed = view.status === "signed_off" && view.revision?.signed_off ? view.revision.no : null;

  useEffect(() => {
    let live = true;
    void deliverablesApi.closeout(projectId, view.id).then((answer) => {
      if (!live) return;
      if (answer.ok) setCloseout(answer.data);
      else setFailed(answer.error);
    });
    return () => {
      live = false;
    };
  }, [projectId, view.id, view.version, view.pending, view.open_comments, view.status, view.code]);

  async function signOff() {
    setBusy(true);
    setFailed(null);
    const answer = await deliverablesApi.signOff(projectId, view.id);
    setBusy(false);
    if (!answer.ok) return setFailed(answer.error); // 409: the first blocking reason
    announce?.(fill(t("reviewSignedOff"), { n: answer.data.revision }));
    onChanged();
  }

  async function issue() {
    setBusy(true);
    setFailed(null);
    const answer = await deliverablesApi.issueRevision(projectId, view.id);
    setBusy(false);
    if (!answer.ok) return setFailed(answer.error);
    announce?.(fill(t("reviewRevisionIssued"), { n: answer.data.no }));
    onChanged();
  }

  async function report(revision: number) {
    const out = await saveAnswer(await deliverablesApi.reviewReport(projectId, view.id, revision));
    if (out.ok) announce?.(out.line);
    else setFailed(out.line);
  }

  const blocked = !closeout?.can_sign_off;
  return (
    <section aria-label={t("reviewCloseOut")} className="flex flex-col gap-2">
      {signed !== null ? (
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold">{fill(t("reviewSignedOff"), { n: signed })}</span>
          <button type="button" className="rounded border border-slate px-2 py-0.5 hover:bg-stone" onClick={() => void report(signed)}>
            {t("reviewReport")} <bdi>PDF</bdi>
          </button>
        </div>
      ) : (
        closeout && (
          <>
            {closeout.reasons.length > 0 ? (
              <div>
                <p>{t("reviewBlockedBecause")}</p>
                <ul id={`signoff-reasons-${view.id}`} className="list-disc ps-6">
                  {closeout.reasons.map((reason, i) => (
                    <li key={i}>{pick(reason)}</li>
                  ))}
                </ul>
              </div>
            ) : (
              <p>{t("reviewCanSignOff")}</p>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={blocked || busy}
                aria-describedby={blocked ? `signoff-reasons-${view.id}` : undefined}
                className="rounded bg-ink px-3 py-1 text-paper disabled:opacity-40"
                onClick={() => void signOff()}
              >
                {t("reviewSignOff")}
              </button>
              <button
                type="button"
                disabled={busy}
                className="rounded border border-slate px-3 py-1 hover:bg-stone disabled:opacity-40"
                onClick={() => void issue()}
              >
                {t("reviewIssueRevision")}
              </button>
            </div>
          </>
        )
      )}
      {failed && (
        <p role="alert" className="text-copper">
          {typeof failed === "string" ? failed : pick(failed)}
        </p>
      )}
    </section>
  );
}
