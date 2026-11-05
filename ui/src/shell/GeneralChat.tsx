// The General chat, outside every project: the conversation centred (at most 42 rem) with the command bar under it.
// The top bar shows "General chat" in place of a project, with no status and no Project Records.
import { t, useLanguage } from "../i18n";
import { ChatBody, type ChatBodyProps } from "./ChatPanel";
import { CommandBar } from "./CommandBar";

export function GeneralChat(props: Omit<ChatBodyProps, "label" | "projectId" | "onOpenDeliverable">) {
  useLanguage();
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <div data-region="chat" tabIndex={-1} className="mx-auto flex min-h-0 w-full max-w-[42rem] flex-1 flex-col">
        <ChatBody {...props} label={t("generalChat")} />
      </div>
      {props.ai.connected !== false && <CommandBar chat={props.chat} />}
    </main>
  );
}
