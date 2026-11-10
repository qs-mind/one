import { Button } from "@/design/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/design/ui/dialog";
import { surfaces } from "@/texts/design/surfaces";
import { useText } from "@/texts/useText";
import { Demo, State } from "../parts";

export function DialogDemo() {
  const t = useText();
  return (
    <Demo id="dialog" title="Dialog">
      <State name={t(surfaces.stateClosed)}>
        <Dialog>
          <DialogTrigger render={<Button variant="outline" />}>{t(surfaces.restoreOpen)}</DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{t(surfaces.restoreTitle)}</DialogTitle>
              <DialogDescription>{t(surfaces.restoreBody)}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button />}>{t(surfaces.restore)}</DialogClose>
              <DialogClose render={<Button variant="outline" />}>{t(surfaces.cancel)}</DialogClose>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </State>
    </Demo>
  );
}
