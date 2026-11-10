import { notify, notifyUndo } from "@/design/notify";
import { Button } from "@/design/ui/button";
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function ToastsDemo() {
  const t = useText();
  return (
    <Demo id="toasts" title="Toasts">
      <State name="notify" className="flex flex-col gap-2">
        <Button variant="outline" onClick={() => notify(t(surfaces.noteSaved))}>
          {t(surfaces.showNotice)}
        </Button>
      </State>
      <State name="notifyUndo" className="flex flex-col gap-2">
        <Button
          variant="outline"
          onClick={() => notifyUndo(t(surfaces.fileRemoved), t(common.undo), () => notify(t(surfaces.fileBack)))}
        >
          {t(surfaces.showUndo)}
        </Button>
      </State>
    </Demo>
  );
}
