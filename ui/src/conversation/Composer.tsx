// The message box (4.26) on ai-elements PromptInput: it takes dropped files and folders (and pasted files) as chips,
// sends on Enter. While the Lead works, or a card holds its work, a message steers that work at once
// (POST /briefs/{id}/steer, contract S98, 3.2); it shows as waiting until /steer answers 202, then the thread
// draws it from the reply's data-steer part (S75).
import { ArrowUpIcon, FileIcon, FolderIcon, XIcon } from "lucide-react";
import { useId, useState } from "react";
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
  /** A new message (POST /chat). */
  onSend: (message: ComposerMessage) => void;
  /** A message to the running or held work (POST /briefs/{id}/steer); resolves on 202. */
  onSteer: (message: ComposerMessage) => Promise<unknown>;
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

type Steering = ComposerMessage & { id: string; failed: boolean };

export function Composer({ onSend, onSteer, activity = "idle", disabled, placeholder }: ComposerProps) {
  const t = useText();
  const id = useId();
  const [steering, setSteering] = useState<Steering[]>([]);

  const steer = (item: Steering) => {
    setSteering((prev) => [...prev.filter((it) => it.id !== item.id), { ...item, failed: false }]);
    onSteer({ text: item.text, attachments: item.attachments }).then(
      () => setSteering((prev) => prev.filter((it) => it.id !== item.id)),
      () => setSteering((prev) => prev.map((it) => (it.id === item.id ? { ...it, failed: true } : it))),
    );
  };

  const submit = (message: ComposerMessage) => {
    if (activity === "idle") onSend(message);
    else steer({ ...message, id: crypto.randomUUID(), failed: false });
  };

  const hint = activity === "working" ? conversation.whileWorking : activity === "held" ? conversation.whileHeld : null;
  return (
    <div className="flex flex-col gap-2">
      {steering.length > 0 && (
        <section aria-label={t(conversation.steeringTitle)} className="flex flex-col gap-2">
          <p className="text-xs text-muted-foreground">{t(conversation.steeringTitle)}</p>
          {steering.map((message) => (
            <div key={message.id} className="flex items-start gap-2 self-end">
              <div className="flex max-w-[78%] flex-col gap-2 rounded-2xl border border-line px-5 py-3">
                {message.text && <p dir={textDir(message.text)}>{message.text}</p>}
                {message.attachments.map((item) => (
                  <Chip key={item.id} item={item} />
                ))}
                {message.failed && <p className="text-xs text-muted-foreground">{t(conversation.steerFailed)}</p>}
              </div>
              {message.failed && (
                <>
                  <Button variant="ghost" onClick={() => steer(message)}>
                    {t(conversation.steerAgain)}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={t(conversation.dropSteer)}
                    onClick={() => setSteering((prev) => prev.filter((it) => it.id !== message.id))}
                  >
                    <XIcon aria-hidden />
                  </Button>
                </>
              )}
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
