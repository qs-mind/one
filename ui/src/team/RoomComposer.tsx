// The room's message box: the one message box of the interface (design 4.26), text only. Enter sends, Shift+Enter
// starts a new line. The message shows in the room once the core has stored it; a refusal says why under the box
// and keeps the words.
import { ArrowUpIcon } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useId, useState } from "react";
import { Button } from "@/design/ui/button";
import { Label } from "@/design/ui/label";
import { Textarea } from "@/design/ui/textarea";
import { common } from "@/texts/common";
import { team } from "@/texts/team";
import { useText } from "@/texts/useText";
import type { Sent } from "./useRoom";

type RoomComposerProps = { onSend: (text: string) => Promise<Sent> };

export function RoomComposer({ onSend }: RoomComposerProps) {
  const t = useText();
  const id = useId();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function send(event?: FormEvent) {
    event?.preventDefault();
    if (sending || text.trim() === "") return;
    setSending(true);
    const sent = await onSend(text);
    setSending(false);
    if (sent.ok) {
      setText("");
      setProblem(null);
    } else setProblem(sent.error ? t(sent.error) : t(team.notSent));
  }

  function keys(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    void send();
  }

  return (
    <form onSubmit={(event) => void send(event)} className="flex flex-col gap-2">
      <div className="focus-ring-within flex items-end gap-3 rounded-2xl border border-input bg-card py-2 ps-5 pe-2">
        <Label className="sr-only" htmlFor={id}>
          {t(team.messageLabel)}
        </Label>
        <Textarea
          id={id}
          variant="bare"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={keys}
          placeholder={t(team.placeholder)}
          aria-invalid={problem !== null || undefined}
          aria-describedby={problem ? `${id}-problem` : undefined}
        />
        <Button type="submit" size="icon" aria-label={t(common.send)} loading={sending}>
          <ArrowUpIcon aria-hidden />
        </Button>
      </div>
      <p id={`${id}-problem`} role="status" className="text-xs empty:hidden">
        {problem}
      </p>
    </form>
  );
}
