import { useEffect, useState } from "react";
import type { FileRegion, Thread } from "../../deliverables/types";
import { pick, t } from "../../i18n";
import { SourceError } from "../../project/sources";
import type { ProjectSources } from "../../project/types";
import { ThreadItem } from "../../review/CommentsPanel";

/** Uses the same thread UI and reply/close routes as Deliverable comments. */
export function FileRegionComments({ sources, projectId, fileId, selection, onAdded }: {
  sources: ProjectSources;
  projectId: string;
  fileId: string;
  selection: FileRegion | null;
  onAdded: () => void;
}) {
  const [threads, setThreads] = useState<Thread[]>([]);
  const [body, setBody] = useState("");
  const [failed, setFailed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    let live = true;
    void sources.fileComments?.(fileId).then(
      (got) => { if (live) setThreads(got); },
      () => { if (live) setFailed(t("documentFailed")); },
    );
    return () => { live = false; };
  }, [sources, fileId, revision]);

  async function add() {
    if (!selection || !body.trim() || !sources.addFileComment || busy) return;
    setBusy(true);
    setFailed(null);
    try {
      await sources.addFileComment(fileId, selection, body.trim());
      setBody("");
      setRevision((n) => n + 1);
      onAdded();
    } catch (error) {
      setFailed(error instanceof SourceError ? pick(error.line) : t("documentFailed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label={t("reviewComments")} className="flex flex-col gap-3 p-3">
      {selection && (
        <form className="flex flex-col gap-2" onSubmit={(event) => { event.preventDefault(); void add(); }}>
          <textarea
            autoFocus dir="auto" aria-label={t("reviewCommentText")}
            value={body} onChange={(event) => setBody(event.target.value)}
            className="rounded border border-slate bg-paper p-2"
          />
          <button disabled={busy || !body.trim()} className="self-start rounded bg-ink px-3 py-1 text-paper disabled:opacity-40">
            {t("reviewAddComment")}
          </button>
        </form>
      )}
      {failed && <p role="alert" className="text-copper">{failed}</p>}
      <ul className="flex flex-col gap-2">
        {threads.map((thread) => (
          <ThreadItem key={thread.id} projectId={projectId} view={null} thread={thread} onChanged={() => setRevision((n) => n + 1)} />
        ))}
      </ul>
    </section>
  );
}
