// Work that was cut off when ONE closed or crashed (WaitingItem kind "unfinished"): the engineer continues it from its
// last Checkpoint (POST /briefs/{id}/continue) or leaves it (/leave), and it is not offered again. Drawn at the end
// of the thread, since its reply may never have been stored.
import { cards } from "@/texts/cards";
import { useText } from "@/texts/useText";
import { Confirmation, ConfirmationAction, ConfirmationActions, ConfirmationTitle } from "./ai/confirmation";

type UnfinishedCardProps = {
  briefId: string;
  onContinue: (briefId: string) => void;
  onLeave: (briefId: string) => void;
  disabled?: boolean;
};

export function UnfinishedCard({ briefId, onContinue, onLeave, disabled = false }: UnfinishedCardProps) {
  const t = useText();
  return (
    <Confirmation data-unfinished={briefId} state="requested" size="sm" variant="outline">
      <ConfirmationTitle>{t(cards.unfinishedLine)}</ConfirmationTitle>
      <ConfirmationActions className="mt-1">
        <ConfirmationAction disabled={disabled} onClick={() => onContinue(briefId)}>
          {t(cards.continue)}
        </ConfirmationAction>
        <ConfirmationAction variant="outline" disabled={disabled} onClick={() => onLeave(briefId)}>
          {t(cards.leave)}
        </ConfirmationAction>
      </ConfirmationActions>
    </Confirmation>
  );
}
