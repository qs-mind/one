// "Raise the cap" on a cap card: the Spending caps as Settings draws them (each saves as it is changed, PATCH
// /settings/{key}), and the button that goes on with the new caps (the card's "raise").
import { SettingsSection } from "@/settings/Section";
import { useSettings } from "@/settings/useSettings";
import { cards } from "@/texts/cards";
import { useText } from "@/texts/useText";
import { ConfirmationAction } from "../ai/confirmation";

export function RaiseCaps({ busy, onGo }: { busy: boolean; onGo: () => void }) {
  const t = useText();
  const { loaded, change } = useSettings();
  if (loaded.state === "loading") return <div aria-busy="true" className="min-h-14" />;
  if (loaded.state === "failed") return <p className="text-xs font-bold">{t(cards.capsNotLoaded)}</p>;
  return (
    <div data-raise-caps className="flex flex-col gap-6">
      <SettingsSection section="caps" settings={loaded.settings} change={change} />
      <div>
        <ConfirmationAction disabled={busy} onClick={onGo}>
          {t(cards.raiseGo)}
        </ConfirmationAction>
      </div>
    </div>
  );
}
