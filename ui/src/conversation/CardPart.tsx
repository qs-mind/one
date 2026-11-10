// A card a running Brief waits on (data-card, contract 3.2), in the decision card's frame: what it asks, its words,
// and its options, the first the dark button. An option the core marks as costing money or not to be taken back
// (`hold`) is a press-and-hold. Questions are answered in typed fields, a table, a Connector and a model's price in
// their own bodies (./cards), and "Raise the cap" opens the Spending caps in place. The answer goes to POST
// /cards/{id}; once the core took it the card is one line: the answer and when.
import { useState } from "react";
import { Link } from "react-router";
import { answerCard } from "@/api/existing";
import { paths } from "@/app/paths";
import { HoldButton } from "@/design/HoldButton";
import { MetaLine } from "@/design/MetaLine";
import { buttonVariants } from "@/design/ui/button";
import { cardOption as o, cards } from "@/texts/cards";
import { formatDate } from "@/texts/format";
import { home } from "@/texts/home";
import { textDir } from "@/texts/language";
import type { TextPair } from "@/texts/types";
import { useText } from "@/texts/useText";
import {
  Confirmation,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationAnswered,
  ConfirmationRequest,
  ConfirmationTitle,
} from "./ai/confirmation";
import { ConnectorBody } from "./cards/ConnectorBody";
import { PriceBody } from "./cards/PriceBody";
import { RaiseCaps } from "./cards/RaiseCaps";
import { RowsBody } from "./cards/RowsBody";
import type { CardAnswer, CardData, Source } from "./parts";
import { QuestionFields } from "./QuestionFields";

const allow = { yes: o.allowOnce, brief: o.allowBrief, no: o.dontAllow };
const OPTIONS: Record<CardData["kind"], Record<string, TextPair>> = {
  outside: allow,
  online: allow,
  cap: { continue: o.capContinue, raise: o.capRaise, report: o.capReport, yes: o.useIt, no: o.dontUseIt },
  price: { price: o.enterItsPrice, nocap: o.useWithoutPrice, no: o.dontUseIt },
  budget: { yes: o.start, no: o.dontStart },
  fallback: { yes: o.useIt, no: o.dontUseIt },
  desk: { yes: o.keepDesk, no: o.dontKeep },
  disagreement: { yes: o.keepAsIs, no: o.sendBack },
  question: { sent: o.send },
  keep: { yes: o.keepForAll, no: o.dontKeep },
  rows: { keep: o.keepTicked, no: o.keepNone },
  cost: { yes: o.goAhead, no: o.notNow },
  connector: { yes: o.addIt, no: o.dontAdd },
  keep_member: { yes: o.keepMember, no: o.dontKeepMember },
  setting: { yes: o.saveSetting, no: o.dontSaveSetting },
};
const PLAIN: Record<string, TextPair> = { yes: o.yes, no: o.no };

const FIX: Record<string, { section: string; words: TextPair }> = {
  ai: { section: "ai", words: home.openAi },
  consent: { section: "ai", words: home.openAi },
  search: { section: "ai", words: home.openAi },
  caps: { section: "caps", words: home.openCaps },
};

type Sent = { choice: string; at: string } & CardAnswer;

type CardPartProps = {
  id: string;
  card: CardData;
  /** The core took the answer: the next card that waits opens. */
  onAnswered?: (id: string) => void;
  /** Nothing can be pressed (an archived tender). */
  disabled?: boolean;
  /** A table row's number opens its source in ONE's viewer. */
  onOpenSource?: (source: Source) => void;
};

/** The kinds that draw a body of their own beside the card's words. */
const BODIES = new Set<CardData["kind"]>(["question", "rows", "connector", "price"]);

export function CardPart({ id, card, onAnswered, disabled = false, onOpenSource }: CardPartProps) {
  const t = useText();
  const [sent, setSent] = useState<Sent | null>(null);
  const [sending, setSending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const [raising, setRaising] = useState(false);
  const label = (option: string) => {
    const words = OPTIONS[card.kind]?.[option] ?? PLAIN[option];
    return words ? t(words) : option;
  };

  const shown: CardData = sent
    ? { ...card, status: "settled", choice: sent.choice, answers: sent.answers, rows_ok: sent.rows_ok, settled_at: sent.at }
    : card;
  const open = shown.status !== "settled" && shown.status !== "withdrawn";
  const busy = sending || disabled;

  async function answer(choice: string, extra: CardAnswer = {}) {
    setSending(true);
    setFailed(null);
    const got = await answerCard(id, { choice, ...extra });
    setSending(false);
    if (got.error !== undefined) return setFailed(got.error ? t(got.error) : t(cards.notSent));
    setSent({ choice, ...extra, at: new Date().toISOString() });
    onAnswered?.(id);
  }

  const given =
    shown.kind === "question" && shown.answers
      ? Object.values(shown.answers).filter(Boolean).join(t.lang === "ar" ? "، " : ", ") || t(cards.noAnswers)
      : shown.choice
        ? label(shown.choice)
        : null;
  const outcome = shown.status === "withdrawn" ? t(cards.withdrawn) : given && t(cards.answered, { choice: given });
  const when = shown.settled_at ? formatDate(new Date(shown.settled_at), t.lang) : null;
  const title = t(card.title);
  const detail = t(card.detail);
  const fix = card.fix ? FIX[card.fix] : undefined;
  const plain = !BODIES.has(card.kind) || (card.kind !== "question" && !card.payload);
  const body = { card: shown, open, busy, label, onAnswer: (choice: string, extra?: CardAnswer) => void answer(choice, extra) };
  const hint = (why: "paid" | "irreversible") => t(why === "paid" ? cards.holdPaid : cards.holdIrreversible);

  return (
    <Confirmation data-card={id} state={open ? "requested" : "answered"} size="sm" variant={open ? "outline" : "panel"}>
      <ConfirmationTitle dir={textDir(title)}>{title}</ConfirmationTitle>
      <ConfirmationRequest>
        {detail && <p dir={textDir(detail)}>{detail}</p>}
        {fix && (
          <Link className={buttonVariants({ variant: "outline" })} to={paths.settings(fix.section)}>
            {t(fix.words)}
          </Link>
        )}
      </ConfirmationRequest>
      <ConfirmationAnswered>
        <MetaLine className="text-xs text-muted-foreground" items={[outcome, when]} />
      </ConfirmationAnswered>
      {card.kind === "question" && open && (
        <QuestionFields
          questions={card.payload?.questions ?? []}
          options={card.options}
          label={label}
          disabled={busy}
          onSend={(choice, answers) => void answer(choice, answers ? { answers } : {})}
        />
      )}
      {!plain && card.kind === "rows" && <RowsBody {...body} onOpenSource={onOpenSource} />}
      {!plain && card.kind === "connector" && <ConnectorBody {...body} />}
      {!plain && card.kind === "price" && open && <PriceBody {...body} />}
      {plain && (
        <ConfirmationActions className="mt-1">
          {card.options.map((option, at) =>
            card.hold?.options.includes(option) ? (
              <HoldButton key={option} wrap disabled={busy} className="max-sm:w-full" hint={hint(card.hold.why)} onHold={() => void answer(option)}>
                {label(option)}
              </HoldButton>
            ) : (
              <ConfirmationAction
                key={option}
                variant={at === 0 ? "default" : "outline"}
                disabled={busy}
                aria-expanded={option === "raise" ? raising : undefined}
                onClick={() => (option === "raise" ? setRaising(!raising) : void answer(option))}
              >
                {label(option)}
              </ConfirmationAction>
            ),
          )}
        </ConfirmationActions>
      )}
      {open && raising && <RaiseCaps busy={busy} onGo={() => void answer("raise")} />}
      {failed && (
        <p role="alert" className="text-xs font-bold">
          {failed}
        </p>
      )}
    </Confirmation>
  );
}
