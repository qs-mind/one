// The decision card (ai-elements Confirmation): what the Lead raised, its view and sources, and exactly two options,
// the first the dark button. One waits at a time; a second is one line until the first is answered. An option
// that spends money or cannot be taken back is a hold, never one click.
import { HoldButton } from "@/design/HoldButton";
import { MetaLine } from "@/design/MetaLine";
import { conversation } from "@/texts/conversation";
import { formatDate } from "@/texts/format";
import { textDir } from "@/texts/language";
import type { Lang } from "@/texts/types";
import { useText } from "@/texts/useText";
import {
  Confirmation,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationAnswered,
  ConfirmationRequest,
  ConfirmationTitle,
} from "./ai/confirmation";
import type { Finding, Source } from "./parts";
import { SourceLinks } from "./SourceLinks";

export type Choice = 0 | 1;

/** A question with two answers, in the screen's language: a Finding the Lead raised, or a two-option card. */
export type Decision = {
  id: string;
  title: string;
  text?: string | null;
  opinion?: string | null;
  sources?: readonly Source[];
  options: readonly [string, string];
  /** The options that spend money or cannot be taken back. */
  hold?: { why: "paid" | "irreversible"; options: readonly Choice[] } | null;
  state: "waiting" | "queued" | "settled";
  chosen?: Choice | null;
  /** How it was closed without a choice. */
  note?: string | null;
  settledAt?: string | null;
};

const STATE: Record<Finding["status"], Decision["state"] | null> = {
  open: null,
  raised: "waiting",
  queued: "queued",
  settled: "settled",
};

/** A Finding as a decision; null for one that asks nothing of the engineer (open, or without two options). */
export function fromFinding(finding: Finding, lang: Lang): Decision | null {
  const state = STATE[finding.status];
  if (!state || (!finding.options && state !== "settled")) return null;
  const [first, second] = finding.options ?? [finding.title, finding.title];
  return {
    id: finding.id,
    title: finding.title[lang],
    text: finding.text,
    opinion: finding.opinion,
    sources: finding.sources,
    options: [first[lang], second[lang]],
    state,
    chosen: finding.chosen,
    note: finding.note?.[lang] ?? null,
    settledAt: finding.settled_at,
  };
}

/** One waits at a time: the first that waits stays, every later one is queued behind it. */
export function oneAtATime(decisions: readonly Decision[]): Decision[] {
  let waiting = false;
  return decisions.map((decision) => {
    if (decision.state !== "waiting") return decision;
    if (waiting) return { ...decision, state: "queued" };
    waiting = true;
    return decision;
  });
}

const Prose = ({ children, className }: { children: string; className?: string }) => (
  <p dir={textDir(children)} className={className}>
    {children}
  </p>
);

type DecisionCardProps = {
  decision: Decision;
  /** Who asks, as the core names the member ("Lead QS"). */
  asker: string;
  onChoose: (choice: Choice) => void;
  onOpenSource?: (source: Source) => void;
};

export function DecisionCard({ decision, asker, onChoose, onOpenSource }: DecisionCardProps) {
  const t = useText();
  if (decision.state === "queued")
    return (
      <p className="text-xs text-muted-foreground" data-decision={decision.id}>
        {t(conversation.queued, { title: decision.title })}
      </p>
    );

  const answer =
    decision.chosen === 0 || decision.chosen === 1
      ? t(conversation.chose, { option: decision.options[decision.chosen] })
      : decision.note;
  const when = decision.settledAt ? formatDate(new Date(decision.settledAt), t.lang) : null;

  return (
    <Confirmation
      data-decision={decision.id}
      state={decision.state === "waiting" ? "requested" : "answered"}
      size="sm"
      variant={decision.state === "waiting" ? "outline" : "panel"}
    >
      <ConfirmationRequest>
        <p className="text-xs text-muted-foreground">
          {t(conversation.needsYou, { name: asker })}
        </p>
      </ConfirmationRequest>
      <ConfirmationTitle dir={textDir(decision.title)}>{decision.title}</ConfirmationTitle>
      <ConfirmationRequest>
        {decision.text && <Prose>{decision.text}</Prose>}
        {decision.opinion && (
          <div className="flex flex-col gap-1">
            <span className="text-xs text-muted-foreground">{t(conversation.opinion)}</span>
            <Prose>{decision.opinion}</Prose>
          </div>
        )}
        <SourceLinks sources={decision.sources ?? []} onOpen={onOpenSource} />
      </ConfirmationRequest>
      <ConfirmationAnswered>
        <MetaLine className="text-xs text-muted-foreground" items={[answer, when]} />
      </ConfirmationAnswered>
      <ConfirmationActions className="mt-1">
        {([0, 1] as const).map((choice) =>
          decision.hold?.options.includes(choice) ? (
            <HoldButton
              key={choice}
              wrap
              className="max-sm:w-full"
              hint={t(decision.hold.why === "paid" ? conversation.holdPaid : conversation.holdIrreversible)}
              onHold={() => onChoose(choice)}
            >
              {decision.options[choice]}
            </HoldButton>
          ) : (
            <ConfirmationAction
              key={choice}
              variant={choice === 0 ? "default" : "outline"}
              onClick={() => onChoose(choice)}
            >
              {decision.options[choice]}
            </ConfirmationAction>
          ),
        )}
      </ConfirmationActions>
    </Confirmation>
  );
}
