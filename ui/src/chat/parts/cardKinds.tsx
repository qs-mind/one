// The renderer of each card kind that carries a payload (Plan 5): what the card shows beyond its words, and its own
// buttons. ApprovalCard keeps the frame (title, words, the answer once given, a refusal) and posts the answer. A kind
// with no renderer here gets the plain approval buttons. This plan fills question, rows and connector (Tasks 3, 10,
// 12); Plan 8 adds understood.
import type { JSX } from "react";
import { ConnectorCard } from "./ConnectorCard";
import { QuestionCard } from "./QuestionCard";
import type { CardData } from "./types";

/** What an answer carries beyond the choice: the answers by question id, and the rows ticked, by index. */
export type CardAnswer = { answers?: Record<string, string>; rows_ok?: number[] };

export type CardKindProps = {
  /** The card as it stands: settled with its answers as soon as the core took them. */
  card: CardData;
  onAnswer: (choice: string, answer?: CardAnswer) => void;
  /** An answer is on its way to the core. */
  sending: boolean;
  /** The words for one of the card's options. */
  label: (option: string) => string;
};

export const cardKinds: Partial<Record<string, (p: CardKindProps) => JSX.Element>> = {
  question: QuestionCard,
  connector: ConnectorCard,
};
