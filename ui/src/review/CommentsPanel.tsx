// The comments on one Deliverable: One's notes (an agent's remarks, never blocking) and Review comments (the
// engineer's and the Checking QS's, which may be Code C: must fix before Sign-off), each with a text label, its
// replies and its status. "Fix it" sends the core's own message to the Lead QS through the chat.
import { workspaceApi } from "../workspace/api";
import { useState } from "react";
import type { Anchor } from "../project/types";
import { deliverablesApi } from "../deliverables/api";
import type { CommentAnchor, Thread, View } from "../deliverables/types";
import { fill, language, pick, t, type Text } from "../i18n";
import { anchorPlace, authorName, when } from "./place";

type Filter = "open" | "blocking" | "all";

export type CommentsPanelProps = {
  projectId: string;
  view: View;
  comments: Thread[];
  /** What the engineer selected in the viewer, as the core's anchor; null puts the comment on the whole Deliverable. */
  selection: CommentAnchor | null;
  onChanged: () => void;
  /** Sends a message to the Lead QS, as the chat does. Without it there is no "Fix it". */
  onSend?: (text: string) => void;
  onLocate?: (anchor: Anchor) => void;
  announce?: (line: string) => void;
};

/** The viewer's anchor for a comment's place now. */
export function toAnchor(a: CommentAnchor): Anchor | null {
  if ("kind" in a && a.kind === "file_region") return { page: a.page, box: a.box };
  switch (a.type) {
    case "cell":
      return { row: a.row, column: a.column };
    case "range":
      return { row: a.from.row, column: a.from.column };
    case "row": {
      const row = a.row ?? a.block;
      return row ? { row } : null;
    }
    case "text":
      return a.moved ? { row: a.block } : { row: a.block, text: [a.start, a.end] };
    default:
      return null;
  }
}

const blocking = (c: Thread) => c.kind === "review" && c.code === "C" && c.status === "open";

function Badge({ thread }: { thread: Thread }) {
  // One's note: a Slate ring; a Review comment: Copper. Each with its text label, never colour alone.
  return thread.kind === "note" ? (
    <span className="rounded-full border border-dashed border-slate px-2 text-xs leading-5 text-slate">{t("reviewNote")}</span>
  ) : (
    <span className="rounded-full border border-copper px-2 text-xs leading-5 text-copper">{t("reviewComment")}</span>
  );
}

export function ThreadItem(props: {
  projectId: string;
  view: View | null;
  thread: Thread;
  onChanged: () => void;
  onSend?: (text: string) => void;
  onLocate?: (anchor: Anchor) => void;
  announce?: (line: string) => void;
}) {
  const { projectId, view, thread, onChanged, onSend, onLocate, announce } = props;
  const [reply, setReply] = useState("");
  const [failed, setFailed] = useState<Text | null>(null);
  const open = thread.status === "open";

  async function run(call: () => Promise<{ ok: boolean; error?: Text }>, after?: () => void) {
    setFailed(null);
    const answer = await call();
    if (!answer.ok) return setFailed(answer.error ?? null);
    after?.();
    onChanged();
  }

  async function fix() {
    setFailed(null);
    const answer = await deliverablesApi.fixText(projectId, thread.id, language());
    if (!answer.ok) return setFailed(answer.error);
    onSend?.(answer.data.text);
    announce?.(t("reviewFixSent"));
  }

  const anchor = toAnchor(thread.anchor_now ?? thread.anchor);
  const small = "rounded-lg border border-ink/20 px-3 py-1 hover:bg-stone";
  return (
    <li
      className={`flex flex-col gap-2 rounded-xl border bg-paper px-4 py-3 ${
        thread.kind === "note" ? "border-dashed border-slate" : "border-s-4 border-stone border-s-copper"
      } ${open ? "" : "opacity-70"}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        <Badge thread={thread} />
        {thread.code === "C" && <span className="font-semibold text-copper">{t("reviewMustFix")}</span>}
        {thread.code === "B" && <span className="text-slate">B</span>}
        <span>{authorName(thread.author)}</span>
        <span className="text-xs text-slate">{when(thread.created_at)}</span>
        <span className="ms-auto text-slate">{open ? t("reviewOpen") : t("reviewClosed")}</span>
      </div>
      <button
        type="button"
        disabled={!anchor}
        className="self-start text-start text-sm text-slate underline decoration-slate/40 hover:text-copper disabled:no-underline"
        onClick={() => {
          const at = thread.anchor_now ?? thread.anchor;
          if ("kind" in at && at.kind === "file_region") workspaceApi.open(`file:${at.file_id}`, {page: at.page, box: at.box});
          else if (anchor) onLocate?.(anchor);
        }}
      >
        <bdi dir="auto">{fill(t("reviewCommentOn"), { place: anchorPlace(view, thread.anchor_now ?? thread.anchor) })}</bdi>
      </button>
      <p dir="auto" className="whitespace-pre-wrap">
        {thread.body}
      </p>
      {thread.replies.length > 0 && (
        <ol className="flex flex-col gap-2 border-s border-stone ps-4">
          {thread.replies.map((r) => (
            <li key={r.id}>
              <span className="text-sm text-slate">
                {authorName(r.author)} · {when(r.created_at)}
              </span>
              <p dir="auto" className="whitespace-pre-wrap">
                {r.body}
              </p>
            </li>
          ))}
        </ol>
      )}
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const body = reply.trim();
          if (body) void run(() => deliverablesApi.reply(projectId, thread.id, body), () => setReply(""));
        }}
      >
        <input
          dir="auto"
          aria-label={t("reviewReplyText")}
          placeholder={t("reviewReplyText")}
          value={reply}
          onChange={(e) => setReply(e.target.value)}
          className="min-w-0 flex-1 rounded-lg border border-slate bg-paper px-3 py-1.5"
        />
        <button type="submit" className={small} disabled={!reply.trim()}>
          {t("reviewReply")}
        </button>
      </form>
      <div className="flex flex-wrap gap-2">
        {open ? (
          <button type="button" className={small} onClick={() => void run(() => deliverablesApi.close(projectId, thread.id))}>
            {t("reviewClose")}
          </button>
        ) : (
          <button type="button" className={small} onClick={() => void run(() => deliverablesApi.reopen(projectId, thread.id))}>
            {t("reviewReopen")}
          </button>
        )}
        {open && onSend && (
          <button type="button" className={`${small} border-ink`} onClick={() => void fix()}>
            {t("reviewFixIt")}
          </button>
        )}
      </div>
      {failed && (
        <p role="alert" className="text-copper">
          {pick(failed)}
        </p>
      )}
    </li>
  );
}

export function CommentsPanel(props: CommentsPanelProps) {
  const { projectId, view, comments, selection, onChanged } = props;
  const [filter, setFilter] = useState<Filter>("open");
  const [body, setBody] = useState("");
  const [mustFix, setMustFix] = useState(false);
  const [failed, setFailed] = useState<Text | null>(null);
  const shown = comments.filter((c) => (filter === "all" ? true : filter === "open" ? c.status === "open" : blocking(c)));
  const where = selection ?? ({ type: "deliverable" } as const);

  async function add() {
    const text = body.trim();
    if (!text) return;
    setFailed(null);
    const answer = await deliverablesApi.comment(projectId, view.id, where, text, mustFix ? "C" : null);
    if (!answer.ok) return setFailed(answer.error);
    setBody("");
    setMustFix(false);
    onChanged();
  }

  const filters: [Filter, string][] = [
    ["open", t("reviewOpen")],
    ["blocking", t("reviewBlocking")],
    ["all", t("reviewAll")],
  ];
  return (
    <section aria-label={t("reviewComments")} className="flex flex-col gap-3">
      <form
        className="flex flex-col gap-2 rounded-xl border border-stone bg-paper px-4 py-3"
        onSubmit={(event) => {
          event.preventDefault();
          void add();
        }}
      >
        <span className="text-sm text-slate">
          <bdi dir="auto">{fill(t("reviewCommentOn"), { place: anchorPlace(view, where) })}</bdi>
        </span>
        <textarea
          dir="auto"
          rows={2}
          aria-label={t("reviewCommentText")}
          placeholder={t("reviewCommentText")}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          className="resize-y rounded-lg border border-slate bg-paper px-3 py-2"
        />
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={mustFix} onChange={(e) => setMustFix(e.target.checked)} />
            {t("reviewMustFix")}
          </label>
          <button type="submit" disabled={!body.trim()} className="ms-auto rounded bg-ink px-3 py-0.5 text-paper disabled:opacity-40">
            {t("reviewAddComment")}
          </button>
        </div>
        {failed && (
          <p role="alert" className="text-copper">
            {pick(failed)}
          </p>
        )}
      </form>
      <fieldset className="flex flex-wrap gap-3">
        <legend className="sr-only">{t("reviewFilter")}</legend>
        {filters.map(([key, label]) => (
          <label key={key} className="flex items-center gap-1">
            <input type="radio" name={`comments-${view.id}`} checked={filter === key} onChange={() => setFilter(key)} />
            {label}
          </label>
        ))}
      </fieldset>
      {shown.length === 0 && <p className="text-slate">{t("reviewNoComments")}</p>}
      <ol className="flex flex-col gap-3">
        {shown.map((thread) => (
          <ThreadItem
            key={thread.id}
            projectId={projectId}
            view={view}
            thread={thread}
            onChanged={onChanged}
            onSend={props.onSend}
            onLocate={props.onLocate}
            announce={props.announce}
          />
        ))}
      </ol>
    </section>
  );
}
