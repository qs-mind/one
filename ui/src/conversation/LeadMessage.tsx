// A reply of the Lead (or of a member who speaks in the thread): its name, the first four lines of the reply, the
// rest under Details, then the sources it rests on (data-sources) and whatever the reply placed (plan, decision).
import { ChevronDownIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "@/design/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/design/ui/collapsible";
import { conversation } from "@/texts/conversation";
import { textDir } from "@/texts/language";
import { useText } from "@/texts/useText";
import { Message, MessageContent, MessageResponse } from "./ai/message";
import { fold } from "./fold";
import type { Source } from "./parts";
import { SourceLinks } from "./SourceLinks";

type LeadMessageProps = {
  /** Who speaks, as the core names the member ("Lead QS"); left out where the thread already says it. */
  name?: string;
  /** The reply's Markdown, as far as it has come. */
  text: string;
  streaming?: boolean;
  sources?: readonly Source[];
  onOpenSource?: (source: Source) => void;
  /** What the reply placed after its words: the plan card, a decision card. */
  children?: ReactNode;
};

export function LeadMessage({ name, text, streaming = false, sources = [], onOpenSource, children }: LeadMessageProps) {
  const t = useText();
  const { head, rest } = fold(text);
  const dir = textDir(text);
  return (
    <Message from="assistant">
      {name && (
        <span className="text-xs text-muted-foreground">
          <bdi dir={textDir(name)}>{name}</bdi>
        </span>
      )}
      <MessageContent className="w-full">
        {head && (
          <MessageResponse dir={dir} streaming={streaming && !rest}>
            {head}
          </MessageResponse>
        )}
        {rest && (
          <Collapsible>
            <CollapsibleTrigger
              className="group/details"
              render={<Button variant="ghost" className="justify-start gap-2 px-2" />}
            >
              <ChevronDownIcon aria-hidden className="size-4.5 group-data-panel-open/details:rotate-180" />
              {t(conversation.details)}
            </CollapsibleTrigger>
            <CollapsibleContent className="pt-2">
              <MessageResponse dir={dir} streaming={streaming}>
                {rest}
              </MessageResponse>
            </CollapsibleContent>
          </Collapsible>
        )}
        <SourceLinks sources={sources} onOpen={onOpenSource} />
      </MessageContent>
      {children}
    </Message>
  );
}
