// The sign-off block of a stage (data-stage, contract 3.1): what the stage made, what the engineer signs off (its
// gate), and the two buttons: "Sign off", always a press-and-hold since a sign-off cannot be undone (route 11, with
// the plan version on screen), and "I have notes", which turns to the message box. Drawn from the plan the screen
// holds: a stage signed off is one line, one whose work goes on again is one line, one no longer in the plan too.
import { HoldButton } from "@/design/HoldButton";
import { cards } from "@/texts/cards";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import {
  Confirmation,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRequest,
  ConfirmationTitle,
} from "./ai/confirmation";
import type { TenderPlan } from "./parts";

type StageCardProps = {
  stageId: string;
  plan: TenderPlan | null;
  onSignOff: (stageId: string, version: number) => void;
  onNotes: () => void;
  disabled?: boolean;
};

const Line = ({ id, children }: { id: string; children: string }) => (
  <p data-signoff={id} className="text-xs text-muted-foreground">
    {children}
  </p>
);

export function StageCard({ stageId, plan, onSignOff, onNotes, disabled = false }: StageCardProps) {
  const t = useText();
  const stage = plan?.stages.find((s) => s.id === stageId);
  if (!plan || !stage) return <Line id={stageId}>{t(cards.stageGone)}</Line>;
  const name = t(stage.title);
  if (stage.status === "approved") return <Line id={stageId}>{t(cards.signedOff, { stage: name })}</Line>;
  if (stage.status !== "waiting_engineer") return <Line id={stageId}>{t(cards.stageWorking, { stage: name })}</Line>;

  const result = stage.result ? t(stage.result) : null;
  const gate = t(stage.gate);
  return (
    <Confirmation data-signoff={stageId} state="requested" size="sm" variant="outline">
      <ConfirmationTitle dir={textDir(name)}>{t(cards.stageAsks, { stage: name })}</ConfirmationTitle>
      <ConfirmationRequest>
        {result && <p dir={textDir(result)}>{result}</p>}
        {stage.outputs.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{t(cards.outputs)}</span>
            <ul className="flex flex-col gap-1">
              {stage.outputs.map((output, at) => {
                const title = t(output.title);
                const pending = (output.kind === "deliverable" || output.kind === "file") && !output.id;
                return (
                  // outputs have no id of their own before they exist; their order is their identity
                  <li key={at} dir={textDir(title)}>
                    {title}
                    {pending && <span className="text-xs text-muted-foreground"> · {t(cards.notReady)}</span>}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        <div className="flex flex-col gap-1">
          <span className="text-xs text-muted-foreground">{t(cards.gate)}</span>
          <p dir={textDir(gate)}>{gate}</p>
        </div>
      </ConfirmationRequest>
      <ConfirmationActions className="mt-1">
        <HoldButton wrap disabled={disabled} className="max-sm:w-full" hint={t(cards.signOffHint)} onHold={() => onSignOff(stageId, plan.version)}>
          {t(cards.signOff)}
        </HoldButton>
        <ConfirmationAction variant="outline" disabled={disabled} onClick={onNotes}>
          {t(cards.notes)}
        </ConfirmationAction>
      </ConfirmationActions>
    </Confirmation>
  );
}
