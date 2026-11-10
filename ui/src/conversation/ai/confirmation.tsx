// ai-elements `confirmation`, made general: ONE asks the engineer about a Finding or a card, not about a tool call, so
// the state is "requested" or "answered" instead of the AI SDK's approval states. The Alert becomes U1's Card (4.25);
// the actions are decision buttons that wrap (3.4) and stack on a narrow screen.
import { type ComponentProps, createContext, type ReactNode, useContext } from "react";
import { cn } from "@/design/lib/utils";
import { Button } from "@/design/ui/button";
import { Card } from "@/design/ui/card";

export type ConfirmationState = "requested" | "answered";

const ConfirmationContext = createContext<ConfirmationState | null>(null);

const useConfirmation = () => {
  const state = useContext(ConfirmationContext);
  if (!state) throw new Error("Confirmation components must be used within Confirmation");
  return state;
};

export type ConfirmationProps = ComponentProps<typeof Card> & { state: ConfirmationState };

export const Confirmation = ({ className, state, ...props }: ConfirmationProps) => (
  <ConfirmationContext.Provider value={state}>
    <Card data-state={state} className={cn("px-(--card-px)", className)} {...props} />
  </ConfirmationContext.Provider>
);

export type ConfirmationTitleProps = ComponentProps<"div">;

export const ConfirmationTitle = ({ className, ...props }: ConfirmationTitleProps) => (
  <div className={cn("font-bold", className)} {...props} />
);

/** Shown only while the answer is asked. */
export const ConfirmationRequest = ({ children }: { children?: ReactNode }) =>
  useConfirmation() === "requested" ? children : null;

/** Shown only once it was answered. */
export const ConfirmationAnswered = ({ children }: { children?: ReactNode }) =>
  useConfirmation() === "answered" ? children : null;

export type ConfirmationActionsProps = ComponentProps<"div">;

export const ConfirmationActions = ({ className, ...props }: ConfirmationActionsProps) =>
  useConfirmation() === "requested" ? (
    <div className={cn("flex flex-wrap items-center gap-3 max-sm:flex-col max-sm:items-stretch", className)} {...props} />
  ) : null;

export type ConfirmationActionProps = ComponentProps<typeof Button>;

export const ConfirmationAction = ({ className, ...props }: ConfirmationActionProps) => (
  <Button className={cn("max-sm:w-full", className)} type="button" wrap {...props} />
);
