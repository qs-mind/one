import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { DIRS, hasTarget44, renderIn, resetPage, stubBrowser } from "@/design/test/harness";
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
import { common } from "@/texts/common";
import { surfaces } from "@/texts/design/surfaces";
import { text } from "@/texts/useText";

beforeEach(stubBrowser);
afterEach(resetPage);

describe.each(DIRS)("Dialog (%s)", (dir) => {
  const lang = dir === "rtl" ? "ar" : "en";
  const t = (pair: { en: string; ar: string }) => text(pair, lang);

  function renderDialog() {
    return renderIn(
      dir,
      <Dialog>
        <DialogTrigger render={<Button variant="outline" />}>{t(surfaces.restoreOpen)}</DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t(surfaces.restoreTitle)}</DialogTitle>
            <DialogDescription>{t(surfaces.restoreBody)}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button>{t(surfaces.restore)}</Button>
            <DialogClose render={<Button variant="outline" />}>{t(surfaces.cancel)}</DialogClose>
          </DialogFooter>
        </DialogContent>
      </Dialog>,
    );
  }

  it("opens on the trigger, named by its title, with a close button named in the page language", async () => {
    renderDialog();
    await userEvent.click(screen.getByRole("button", { name: t(surfaces.restoreOpen) }));
    const dialog = await screen.findByRole("dialog", { name: t(surfaces.restoreTitle) });
    const close = screen.getByRole("button", { name: text(common.close, lang) });
    expect(dialog.contains(close)).toBe(true);
    expect(hasTarget44(close)).toBe(true);
    expect(close.className).toMatch(/\btop-3\b/);
    expect(close.className).toMatch(/\bend-3\b/);
    expect(dialog.className).toMatch(/rounded-2xl/);
    expect(dialog.className).toMatch(/border-line/);
    expect(dialog.className).not.toMatch(/ring-|shadow|duration-|outline-none/);
  });

  it("traps Tab inside, closes on Escape and gives focus back to the trigger", async () => {
    renderDialog();
    const trigger = screen.getByRole("button", { name: t(surfaces.restoreOpen) });
    await userEvent.click(trigger);
    const dialog = await screen.findByRole("dialog");
    // Base UI's focus guards hand focus back inside the popup; a guard may hold it for a tick.
    const visited = new Set<Element>();
    for (let i = 0; i < 6; i++) {
      await userEvent.tab();
      await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true));
      if (document.activeElement) visited.add(document.activeElement);
      expect(document.activeElement).not.toBe(trigger);
    }
    expect(visited.size).toBeGreaterThanOrEqual(3); // restore, cancel, close: it cycles inside
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(trigger));
  });

  it("the scrim is the scrim token, without blur", async () => {
    renderDialog();
    await userEvent.click(screen.getByRole("button", { name: t(surfaces.restoreOpen) }));
    await screen.findByRole("dialog");
    const overlay = document.querySelector('[data-slot="dialog-overlay"]');
    expect(overlay?.className).toMatch(/\bbg-scrim\b/);
    expect(overlay?.className).not.toMatch(/blur|bg-black/);
  });
});
