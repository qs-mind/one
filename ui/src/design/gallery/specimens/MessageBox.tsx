// Specimen 3: the message box (section 4.26), the same everywhere: at rest, with three lines, and as a drop target.
import { ArrowUpIcon } from "lucide-react";
import { useId, useState, type DragEvent } from "react";
import { Button } from "@/design/ui/button";
import { Label } from "@/design/ui/label";
import { Textarea } from "@/design/ui/textarea";
import { common } from "@/texts/common";
import { controls } from "@/texts/design/controls";
import { foundation } from "@/texts/design/foundation";
import { specimens } from "@/texts/design/specimens";
import { useText } from "@/texts/useText";
import { State } from "../parts";

type BoxProps = { defaultValue?: string; dropTarget?: boolean };

/** The composition of 4.26. While files are dragged over it, its edge is 2px and its placeholder says so. */
export function MessageBoxComposition({ defaultValue, dropTarget = false }: BoxProps) {
  const t = useText();
  const id = useId();
  const [dragging, setDragging] = useState(false);
  const showsDrop = dropTarget || dragging;
  const over = (event: DragEvent) => {
    if (!event.dataTransfer.types.includes("Files")) return;
    event.preventDefault();
    setDragging(true);
  };
  return (
    <div
      data-drop-target={showsDrop || undefined}
      onDragOver={over}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
      }}
      className="focus-ring-within flex items-end gap-3 rounded-2xl border border-input bg-card py-2 ps-5 pe-2 data-drop-target:border-2 data-drop-target:border-foreground data-drop-target:py-[calc(--spacing(2)-1px)] data-drop-target:ps-[calc(--spacing(5)-1px)] data-drop-target:pe-[calc(--spacing(2)-1px)]"
    >
      <Label className="sr-only" htmlFor={id}>
        {t(specimens.messageLabel)}
      </Label>
      <Textarea
        id={id}
        variant="bare"
        defaultValue={defaultValue}
        placeholder={showsDrop ? t(common.dropHere) : t(specimens.messagePlaceholder)}
      />
      <Button size="icon" aria-label={t(common.send)}>
        <ArrowUpIcon aria-hidden />
      </Button>
    </div>
  );
}

export function MessageBox() {
  const t = useText();
  return (
    <div className="flex w-full max-w-(--measure) flex-col gap-6">
      <State name={t(foundation.rest)}>
        <MessageBoxComposition />
      </State>
      <State name={t(specimens.threeLines)}>
        <MessageBoxComposition defaultValue={t(controls.notesSample)} />
      </State>
      <State name={t(specimens.dropTarget)}>
        <MessageBoxComposition dropTarget />
      </State>
    </div>
  );
}
