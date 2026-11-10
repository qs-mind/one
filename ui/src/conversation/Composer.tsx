// The message box (4.26) on ai-elements PromptInput: it takes dropped files and folders (and pasted files) as chips,
// sends on Enter, and while the Lead works it queues what is written and sends it, in order, when the work stops.
// While a card holds the work ("held") a message goes at once: the Lead reads it after the engineer's choice (3.2).
import { ArrowUpIcon, FileIcon, FolderIcon, XIcon } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/design/ui/button";
import { Label } from "@/design/ui/label";
import { common } from "@/texts/common";
import { conversation } from "@/texts/conversation";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import {
  PromptInput,
  type PromptInputAttachment,
  type PromptInputMessage,
  PromptInputSubmit,
  PromptInputTextarea,
  usePromptInputAttachments,
} from "./ai/prompt-input";

export type ComposerMessage = PromptInputMessage;
export type LeadActivity = "idle" | "working" | "held";

type ComposerProps = {
  onSend: (message: ComposerMessage) => void;
  /** What the Lead is doing: from the reply's data-status (running, or waiting for the engineer). */
  activity?: LeadActivity;
  disabled?: boolean;
  placeholder?: string;
};

function Chip({ item, onRemove }: { item: PromptInputAttachment; onRemove?: () => void }) {
  const t = useText();
  const name = item.kind === "folder" ? t(conversation.folder, { name: item.name }) : item.name;
  return (
    <span className="inline-flex h-11 max-w-full items-center gap-2 rounded-lg border border-line ps-3 text-xs">
      {item.kind === "folder" ? <FolderIcon aria-hidden className="size-4 shrink-0" /> : <FileIcon aria-hidden className="size-4 shrink-0" />}
      <bdi dir={textDir(name)} className="truncate">
        {name}
      </bdi>
      {onRemove && (
        <Button variant="ghost" size="icon" aria-label={t(conversation.remove, { name: item.name })} onClick={onRemove}>
          <XIcon aria-hidden />
        </Button>
      )}
    </span>
  );
}

/** The dropped items inside the box, each with its remove button. */
function Dropped() {
  const { attachments, remove } = usePromptInputAttachments();
  if (attachments.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2 pt-1">
      {attachments.map((item) => (
        <Chip key={item.id} item={item} onRemove={() => remove(item.id)} />
      ))}
    </div>
  );
}

type Queued = ComposerMessage & { id: string };

export function Composer({ onSend, activity = "idle", disabled, placeholder }: ComposerProps) {
  const t = useText();
  const id = useId();
  const [queue, setQueue] = useState<Queued[]>([]);
  const send = useRef(onSend);
  send.current = onSend;

  // The work stopped: what waited goes now, in the order it was written.
  useEffect(() => {
    if (activity !== "working" && queue.length > 0) {
      for (const { text, attachments } of queue) send.current({ text, attachments });
      setQueue([]);
    }
  }, [activity, queue]);

  const submit = (message: ComposerMessage) => {
    if (activity === "working") setQueue((prev) => [...prev, { ...message, id: crypto.randomUUID() }]);
    else onSend(message);
  };

  const hint = activity === "working" ? conversation.whileWorking : activity === "held" ? conversation.whileHeld : null;
  return (
    <div className="flex flex-col gap-2">
      {queue.length > 0 && (
        <section aria-label={t(conversation.queuedTitle)} className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{t(conversation.queuedTitle)}</p>
          {queue.map((message) => (
            <div key={message.id} className="flex items-start gap-2 self-end">
              <div className="flex max-w-[78%] flex-col gap-2 rounded-2xl border border-line px-5 py-3">
                {message.text && <p dir={textDir(message.text)}>{message.text}</p>}
                {message.attachments.map((item) => (
                  <Chip key={item.id} item={item} />
                ))}
              </div>
              <Button
                variant="ghost"
                size="icon"
                aria-label={t(conversation.removeQueued)}
                onClick={() => setQueue((prev) => prev.filter((it) => it.id !== message.id))}
              >
                <XIcon aria-hidden />
              </Button>
            </div>
          ))}
        </section>
      )}
      <PromptInput onSubmit={submit} header={<Dropped />}>
        <Label className="sr-only" htmlFor={id}>
          {t(conversation.messageLabel)}
        </Label>
        <PromptInputTextarea
          id={id}
          disabled={disabled}
          placeholder={placeholder ?? t(conversation.placeholder)}
          dropPlaceholder={t(common.dropHere)}
        />
        <PromptInputSubmit label={t(common.send)} disabled={disabled}>
          <ArrowUpIcon aria-hidden />
        </PromptInputSubmit>
      </PromptInput>
      {hint && <p className="text-xs text-muted-foreground">{t(hint)}</p>}
    </div>
  );
}
