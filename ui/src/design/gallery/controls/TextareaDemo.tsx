import { Textarea } from "@/design/ui/textarea";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { useText } from "@/texts/useText";
import { Code, Demo, State } from "../parts";

const BOX = "flex w-80 flex-col gap-2";

export function TextareaDemo() {
  const t = useText();
  const name = t(controls.notes);
  return (
    <Demo id="textarea" title="Textarea">
      <State name={t(foundation.rest)} className={BOX}>
        <Textarea aria-label={name} placeholder={name} />
      </State>
      <State name={t(foundation.hover)} className={BOX}>
        <Textarea aria-label={name} placeholder={name} data-force="hover" />
      </State>
      <State name={t(foundation.focus)} className={BOX}>
        <Textarea aria-label={name} placeholder={name} data-force="focus" />
      </State>
      <State name={t(foundation.filled)} className={BOX}>
        <Textarea aria-label={name} defaultValue={t(controls.notesSample)} />
      </State>
      <State name={t(foundation.disabled)} className={BOX}>
        <Textarea aria-label={name} disabled defaultValue={t(controls.notesSample)} />
      </State>
      <State name={t(foundation.error)} className={BOX}>
        <Textarea aria-label={name} aria-invalid defaultValue={t(controls.notesSample)} />
      </State>
      <State name={<Code>variant=bare</Code>} className={BOX}>
        <div className="focus-ring-within rounded-2xl border border-input bg-card px-5">
          <Textarea aria-label={name} variant="bare" placeholder={name} />
        </div>
      </State>
    </Demo>
  );
}
